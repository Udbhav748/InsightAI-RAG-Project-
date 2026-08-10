"""The Research agent: a second, cooperating agent that owns the
weak/insufficient-retrieval path with a multi-step loop:
plan → search → read → synthesize.

Where the corrective RAG loop's web fallback is a single search_web() call
whose snippets are bolted onto the normal generation prompt, the Research
agent runs its own loop autonomously:

1. plan      — the LLM breaks the user's query into 1..N search queries.
2. search    — each sub-query runs through the web-search tool.
3. read      — the top pages are fetched and their text pulled into
               context (bounded: research_read_limit pages,
               research_page_max_chars chars each, per-page timeout).
4. synthesize— the agent builds its own grounded answer from what it
               collected and returns it to the orchestrator.

This is the multi-agent design the checklist asks for: the router agent
hands off to a specialist that does real work and reports back, rather
than the orchestrator calling a tool inline. Handoffs and agent lifecycle
are logged via agent_events.py so Handoff Accuracy / Agent Idle Time are
measurable.

Failure-safe by construction, like every enhancement in this codebase:
- No web search enabled? Returns empty findings; the orchestrator falls
  through to the normal retrieve path.
- Human-approval gate (web_search_requires_approval) applies: skipped
  unless confirm_web_search is true, exactly like the tool-level gate.
- A search that errors, a page that fails to fetch, or a synthesis that
  comes back empty all degrade to "no research available" — never a new
  request-level failure mode.
"""

from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import WebSearchError
from app.models.document import WebSearchResult
from app.services.agent_events import log_agent_completed, log_agent_started
from app.services.llm_client import LLMClient
from app.services.prompt_builder import build_prompt, strip_sources_section
from app.services.web_search_service import search_web

logger = logging.getLogger(__name__)

# JSON shapes the LLM is asked for in the plan step; kept in sync with
# _parse_plan and _build_plan_prompt.
_QUERY_PLAN_SCHEMA = '{"queries": ["<search query 1>", "<search query 2>", ...]}'

_PLAN_PROMPT = (
    "You are the planning step of a web research agent. Break the user's "
    "question into concrete search-engine queries that would find the "
    "information to answer it. Respond with ONLY a single JSON object, no "
    "prose, matching exactly:\n"
    f"{_QUERY_PLAN_SCHEMA}\n\n"
    "Rules:\n"
    "- 1 to {max} queries, most promising first.\n"
    "- Prefer specific, keyword-dense queries over long natural sentences.\n"
    "- Cover distinct angles of the question if it has several.\n\n"
    "Question: {query}"
)


class _TextExtractor(HTMLParser):
    """Minimal HTML → text: drops scripts/styles/tags, collapses runs of
    whitespace. Good enough to turn a fetched page into bounded prompt
    context without pulling in an HTML-cleaning dependency."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(self._parts).strip()


@dataclass
class ResearchFindings:
    """Everything the Research agent hands back to the orchestrator.

    answer is the synthesized, grounded answer ("" = no research was
    possible — caller falls through to the normal path). results is what
    actually made it into the synthesis prompt, for sources.
    """

    results: list[WebSearchResult] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    pages_read: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""


class ResearchAgent:
    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client

    def run(self, query: str, confirm_web_search: bool = False) -> ResearchFindings:
        start = time.perf_counter()
        log_agent_started("research", query)

        if not settings.web_search_enabled:
            logger.info(
                "research_degraded_web_disabled",
                extra={"extra_fields": {"query_length": len(query)}},
            )
            return ResearchFindings(answer="")

        if settings.web_search_requires_approval and not confirm_web_search:
            logger.info(
                "research_skipped_pending_approval",
                extra={"extra_fields": {"query_length": len(query)}},
            )
            return ResearchFindings(answer="")

        findings = ResearchFindings()

        findings.queries = self._plan_queries(query)
        findings.steps.append({"stage": "plan", "query_count": len(findings.queries)})

        search_results = self._search(findings.queries)
        findings.steps.append({"stage": "search", "result_count": len(search_results)})
        if not search_results:
            log_agent_completed("research", query, start, outcome="no_results")
            return findings

        page_results, pages_read = self._read(search_results)
        findings.pages_read = pages_read
        findings.steps.append({"stage": "read", "pages_read": pages_read})

        # Page text replaces the snippet for pages we actually read; the
        # rest stay as snippets.
        read_urls = {r.url for r in page_results}
        findings.results = page_results + [r for r in search_results if r.url not in read_urls]

        findings.answer = self._synthesize(query, findings.results)
        if not findings.answer:
            log_agent_completed("research", query, start, outcome="synthesis_failed")
            return findings

        log_agent_completed(
            "research",
            query,
            start,
            outcome="success",
            result_count=len(findings.results),
            pages_read=pages_read,
        )
        return findings

    def _plan_queries(self, query: str) -> list[str]:
        """Step 1 — ask the LLM for 1..N search queries (JSON mode). Any
        failure defaults to the original query as the single sub-query."""
        max_queries = max(1, settings.research_max_subqueries)
        # .replace, not str.format: _PLAN_PROMPT embeds _QUERY_PLAN_SCHEMA,
        # whose literal braces would be parsed as format placeholders.
        prompt = _PLAN_PROMPT.replace("{max}", str(max_queries)).replace("{query}", query.strip())
        try:
            raw = self._llm_client.generate_structured(prompt)
        except Exception as exc:
            logger.warning("research_plan_failed", extra={"extra_fields": {"error": str(exc)}})
            return [query]

        payload = _parse_plan(raw)
        if not payload:
            logger.info(
                "research_plan_parse_failed", extra={"extra_fields": {"query_length": len(query)}}
            )
            return [query]

        queries = [str(q).strip() for q in payload if str(q).strip()]
        return queries[:max_queries] if queries else [query]

    def _search(self, queries: list[str]) -> list[WebSearchResult]:
        """Step 2 — run each sub-query through the web-search tool.
        Best-effort: an individual search failing is logged and skipped."""
        seen: set[str] = set()
        results: list[WebSearchResult] = []
        for query in queries:
            try:
                for result in search_web(query):
                    if result.url not in seen:
                        seen.add(result.url)
                        results.append(result)
            except WebSearchError as exc:
                logger.warning(
                    "research_search_failed",
                    extra={"extra_fields": {"query": query, "error": str(exc)}},
                )
        return results

    def _read(self, results: list[WebSearchResult]) -> tuple[list[WebSearchResult], int]:
        """Step 3 — fetch the top pages and pull bounded plain text into
        context. A page that fails to fetch is skipped, not fatal."""
        read: list[WebSearchResult] = []
        limit = max(0, settings.research_read_limit)
        for result in results[:limit]:
            text = _fetch_page_text(result.url)
            if not text:
                continue
            read.append(
                WebSearchResult(title=result.title, url=result.url, snippet=text)
            )
        return read, len(read)

    def _synthesize(self, query: str, results: list[WebSearchResult]) -> str:
        """Step 4 — build a grounded answer from the collected context
        using the same prompt machinery (trust boundaries, sources
        stripping) as the main pipeline. Returns "" if nothing usable came
        back."""
        if not results:
            return ""
        prompt = build_prompt(query, [], web_results=results)
        return strip_sources_section(self._llm_client.generate(prompt)).strip()


def _parse_plan(raw: str) -> list[Any] | None:
    """Defensive parse of the plan step's JSON output. Never raises."""
    if not raw or not raw.strip():
        return None
    import json

    try:
        payload = json.loads(raw.strip())
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    queries = payload.get("queries")
    return queries if isinstance(queries, list) else None


def _fetch_page_text(url: str, max_chars: int | None = None) -> str:
    """Fetch `url` and return its text, capped and bounded.

    Only http(s) URLs are fetched (search results are untrusted data);
    anything else, any transport/parse failure, or a non-200 response
    returns "" — the Research agent treats that as "page unavailable" and
    moves on, never as an error to propagate.
    """
    if not url.lower().startswith(("http://", "https://")):
        return ""
    cap = max_chars if max_chars is not None else settings.research_page_max_chars
    try:
        response = httpx.get(
            url,
            timeout=settings.research_page_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "InsightAI-RAG-research-agent/0.1"},
        )
        response.raise_for_status()
    except Exception as exc:
        logger.info(
            "research_page_fetch_failed",
            extra={"extra_fields": {"url": url, "error": str(exc)[:120]}},
        )
        return ""

    parser = _TextExtractor()
    try:
        parser.feed(response.text[: max(0, cap * 4)])
    except Exception:
        return ""

    text = html.unescape(parser.text())
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0] + "…"
    return text
