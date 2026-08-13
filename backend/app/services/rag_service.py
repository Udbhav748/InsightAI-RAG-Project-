"""Orchestrates a small hand-rolled agent: plans which tool a query needs,
executes it, and corrects the result when retrieval or generation comes up
short.

Deliberately plain Python — no LangChain/LangGraph agent runtime. A
planner (_plan) picks one of three actions from a query (and, for
"summarize", which document_id it names); a tool executes it
(conversational canned reply, retrieval + generation, or document
summarization). The `retrieve` action runs a small corrective RAG loop:
_grade_retrieval scores what came back, a weak/insufficient grade can pull
in web search results (services/web_search_service.py) alongside or
instead of document chunks, and _correct catches the specific failure mode
of "there was context but the model didn't use it," regenerating up to
_MAX_LLM_CALLS total generate() calls per request — escalating to web
search once, if not already tried, before giving up.

ChatService still contains no retrieval, prompt, or LLM logic itself — it
coordinates RetrievalService, PromptBuilder, SummarizationService,
WebSearchService, and LLMClient. It depends on the VectorStore and
LLMClient interfaces, never on a concrete implementation (FAISSVectorStore,
GeminiClient); those are constructed elsewhere and handed in.
"""

import logging
import re
import time
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import AppError, ChatServiceError, WebSearchError
from app.core.usage_tracking import current_usage, reset_usage
from app.core.metrics import get_metrics
from app.models.document import RetrievedChunk, VisionPrediction, WebSearchResult
from app.models.schemas import ChatResponse, DiagnosisInfo, SourceReference
from app.services.llm_client import LLMClient
from app.services.prompt_builder import (
    FALLBACK_REPLY,
    PROMPT_VERSION,
    REFLECTION_INSTRUCTION,
    build_prompt,
    build_structured_prompt,
    strip_sources_section,
)
from app.services.prompt_injection_service import detect_possible_injection
from app.services.retrieval_service import retrieve
from app.services.structured_output import parse_structured_answer
from app.services.summarization_service import summarize_document
from app.services.vector_store import VectorStore
from app.services.vision_client import diagnose_image
from app.services.vision_qa_service import try_vision_qa
from app.services.web_search_service import search_web, web_search_ready
from app.services.agent_events import log_agent_handoff
from app.services.research_agent import ResearchAgent, ResearchFindings
from app.services.router_agent import RouterAgent
from app.services.local_research_agent import LocalResearchAgent
from app.services.tools.base import ToolContext
from app.services.tools.factory import build_tool_registry

logger = logging.getLogger(__name__)

# Hard ceiling on generate() calls per /chat request (the initial answer,
# plus the corrective loop's reflection and web-fallback regenerations) —
# the loop-prevention/Loop Rate control. The corrective loop as written
# never needs more than 3 (see _correct), so this is a defensive backstop
# against a future change to the loop rather than something normal traffic
# is expected to hit; hitting it logs "loop_capped".
_MAX_LLM_CALLS = 3


def _capture_prompt(prompt: str, *, variant: str) -> None:
    """Log the exact prompt when Settings.log_prompt_content is on.

    Off by default — prompts embed retrieved document text, so capturing
    them is an explicit data-retention decision (Settings.log_prompt_max_chars
    caps what's logged; the capture is a truncated prefix with a marker,
    never silently cut). This is what closes the "prompt recorded but not
    captured" debugging gap in the checklist.
    """
    if not settings.log_prompt_content:
        return
    max_chars = settings.log_prompt_max_chars
    captured = prompt if len(prompt) <= max_chars else prompt[:max_chars] + "...[truncated]"
    logger.info(
        "prompt_captured",
        extra={
            "extra_fields": {
                "prompt_version": PROMPT_VERSION,
                "variant": variant,
                "prompt_length": len(prompt),
                "captured_length": len(captured),
                "prompt": captured,
            }
        },
    )

# Each entry is (normalized exact phrases, canned response). Checked in
# order; the query must match one of the phrases entirely (after
# normalization) — a real question that merely contains a word like
# "thanks" mid-sentence should still go to the RAG pipeline.
_CONVERSATIONAL_INTENTS = [
    (
        {"hi", "hey", "yo", "hiya"},
        "Hi! I'm InsightAI. How can I help you with your uploaded documents today?",
    ),
    (
        {"hello", "good morning", "good afternoon", "good evening"},
        "Hello! Upload a document or ask me a question about one you've already uploaded.",
    ),
    (
        {"thanks", "thank you", "thanks a lot", "thank you so much", "many thanks"},
        "You're welcome! Let me know if you need help understanding anything in your documents.",
    ),
    (
        {"bye", "goodbye", "see you", "see ya", "farewell"},
        "Goodbye! Come back anytime you have questions about your documents.",
    ),
    (
        {"who are you", "what are you"},
        "I'm InsightAI, an AI-powered document assistant. I can analyze your uploaded "
        "documents, answer questions, summarize content, and help you quickly find "
        "information.",
    ),
    (
        {"what can you do", "help", "how do you work", "what do you do"},
        "I can:\n"
        "- Answer questions from uploaded PDFs\n"
        "- Summarize documents\n"
        "- Explain concepts\n"
        "- Find important information\n"
        "- Help you study or review documents",
    ),
    # Meta/status remarks — the user is checking whether the bot is
    # working or venting about it, not asking a document question. Without
    # this, these fall through to retrieve and (depending on min_score)
    # can return an odd, technically-grounded-but-irrelevant answer built
    # from whatever chunk happened to score highest.
    (
        {
            "why not responding",
            "why are you not responding",
            "why aren't you responding",
            "why is this not responding",
            "why isn't this working",
            "why is this not working",
            "this is not working",
            "this isn't working",
            "not working",
            "are you there",
            "are you working",
            "is this working",
            "is this thing working",
            "hello are you there",
            "anyone there",
            "is anyone there",
            "did you get my message",
            "what happened",
            "what happend",
            "did that work",
        },
        "I'm here and working — I just didn't find anything relevant to that in "
        "your uploaded documents. Try asking a specific question about what's in "
        "them, like \"what does this document say about...\".",
    ),
]

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

# Matches "summarize"/"summarise"/"summary" anywhere in the query.
_SUMMARIZE_RE = re.compile(r"\bsummar(?:y|ize|ise)\b", re.IGNORECASE)

# A document_id is a uuid4 (see upload_service.save_uploaded_file) — this
# is how a "summarize" query names which document it means. Queries that
# mention "summarize" without one fall back to the normal retrieve action:
# there's no document-name index to resolve a title against.
_DOCUMENT_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

# How many of the most recent conversation turns get sent to the LLM.
_MAX_HISTORY_TURNS = 6

# Length of the excerpt shown per cited chunk in ChatResponse.sources.
_EXCERPT_LENGTH = 200


def _normalize(query: str) -> str:
    stripped = _PUNCTUATION_RE.sub("", query.lower())
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _excerpt(text: str) -> str:
    """First ~200 chars of a chunk's text, trimmed at a clean boundary."""
    stripped = text.strip()
    if len(stripped) <= _EXCERPT_LENGTH:
        return stripped
    return stripped[:_EXCERPT_LENGTH].rstrip() + "…"


def _source_references(chunks: list[RetrievedChunk], start: int = 1) -> list[SourceReference]:
    """One SourceReference per retrieved chunk — chunk-level, not deduped
    by document, so a citation always points at the specific passage the
    answer actually drew from.

    number starts at `start` and counts up in list order — this must
    match the [N] labels prompt_builder.build_prompt() puts on these same
    chunks (same order, same starting point), since that's what the
    model's inline citation markers refer back to.
    """
    return [
        SourceReference(
            number=i,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            excerpt=_excerpt(chunk.text),
            # Defaults ("text"/None) cover ordinary chunks untouched by
            # multi-modal RAG; image-caption/table chunks carry these in
            # their own metadata (see chunking_service.chunk_text) and
            # just pass through here — this file's ownership of the
            # RAG/citation surface, not multi-modal RAG's.
            content_type=chunk.metadata.get("content_type", "text"),
            page_number=chunk.metadata.get("page_number"),
        )
        for i, chunk in enumerate(chunks, start=start)
    ]


def _web_source_references(results: list[WebSearchResult], start: int = 1) -> list[SourceReference]:
    """One SourceReference per web result, using the same shape as document
    citations: document_id='web' marks it as non-document, chunk_id is the
    URL itself (a web result has no chunk id, but the URL is a stable,
    unique-enough identifier), and url carries the link for the frontend to
    render out.

    number continues from `start` (see _source_references) — web results
    are always numbered after document chunks, matching
    prompt_builder.build_prompt()'s context ordering (documents first).
    """
    return [
        SourceReference(
            number=i, document_id="web", chunk_id=result.url, excerpt=_excerpt(result.snippet), url=result.url
        )
        for i, result in enumerate(results, start=start)
    ]


def _answer_source(chunks: list[RetrievedChunk], web_results: list[WebSearchResult]) -> str:
    """"documents" | "web" | "mixed", based on which context actually made
    it into the final prompt — not on what was attempted. A web search that
    was tried but returned nothing doesn't count as "web"."""
    if not web_results:
        return "documents"
    return "web" if not chunks else "mixed"


# Small English stopword set for the lexical groundedness check (Feature
# #4). Deliberately hand-maintained rather than pulled from a library —
# the project's monitoring/eval philosophy is dependency-free stand-ins,
# and a 60-word set is more than enough to strip the colorless filler
# ("the", "and", "is") that would otherwise dominate a token-overlap
# ratio. Looser (case-insensitive, accent-naive) than the gold standard
# lists; fine for a signal that's a pointer to double-check, not a gate.
_GROUNDEDNESS_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "than", "that", "this", "these", "those", "of", "in", "on", "at",
        "to", "from", "for", "with", "without", "by", "as", "is", "are",
        "was", "were", "be", "been", "being", "do", "does", "did", "have",
        "has", "had", "will", "would", "can", "could", "should", "may",
        "might", "must", "not", "no", "yes", "it", "its", "he", "she",
        "they", "we", "you", "i", "my", "your", "our", "their", "the",
        "about", "into", "between", "over", "under", "again", "also",
        "just", "very", "too", "same", "some", "such", "only", "other",
        "any", "all", "both", "each", "few", "more", "most", "much",
    }
)


def _content_tokens(text: str) -> set[str]:
    """Lowercased, stopword-stripped, alphanumeric content tokens."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _GROUNDEDNESS_STOPWORDS and len(token) > 1
    }


def _grounding_score(answer: str, chunks: list[RetrievedChunk], web_results: list[WebSearchResult]) -> float:
    """Fraction of the answer's content tokens that also appear in the
    retrieved context (chunk text + web snippets). 1.0 if the answer has
    no content tokens to compare. A purely lexical proxy for groundedness —
    deliberately cheap and dependency-free; it can't catch a fluent
    fabrication that happens to reuse source vocabulary, but it reliably
    flags the more common failure of an answer produced from nothing.
    """
    answer_tokens = _content_tokens(answer)
    if not answer_tokens:
        return 1.0
    context_tokens = set()
    for chunk in chunks:
        context_tokens |= _content_tokens(chunk.text)
    for result in web_results:
        context_tokens |= _content_tokens(result.snippet)
    if not context_tokens:
        return 1.0
    overlap = len(answer_tokens & context_tokens)
    return overlap / len(answer_tokens)


def _detect_hallucination(
    answer: str,
    chunks: list[RetrievedChunk],
    web_results: list[WebSearchResult],
) -> tuple[bool, float]:
    """Run the Feature #4 lexical groundedness check.

    Returns (detected, score). Detected is True when the check has
    something to say (there was context, the answer is long enough to
    score) and the answer's content-token overlap with that context falls
    below Settings.hallucination_grounding_threshold. Never blocks — it's
    a signal surfaced to the user to double-check against the sources.
    """
    if not settings.hallucination_detection_enabled:
        return False, None
    if len(answer.strip()) < settings.hallucination_min_answer_chars:
        return False, None
    if not chunks and not web_results:
        return False, None
    score = _grounding_score(answer, chunks, web_results)
    detected = score < settings.hallucination_grounding_threshold
    return detected, round(score, 4)


# Matches prompt_builder._SOURCES_HEADING's own marker string (not the
# regex itself — this operates incrementally on a live token stream,
# where a full-string regex can't run until the heading has fully
# arrived). See _stream_filtering_sources.
_SOURCES_MARKER = "sources:"
_SOURCES_HOLD_BACK = len(_SOURCES_MARKER) + 4  # margin for surrounding newlines


def _stream_filtering_sources(chunks: Iterator[str]) -> Iterator[str]:
    """Forward pieces of a raw LLM token stream, holding back enough
    trailing text that the model's own "Sources:" heading (see
    prompt_builder.strip_sources_section — the non-streaming path strips
    this from the complete answer before it's ever shown) never partially
    reaches the client before it can be recognized and dropped. Once the
    heading is found, everything from there on is suppressed — matching
    strip_sources_section's behavior of removing "Sources:" through the
    end of the text — but the underlying iterator is still drained so the
    caller (which accumulates the full raw text separately) sees it all.
    """
    pending = ""
    sources_found = False
    for chunk in chunks:
        if sources_found:
            continue
        pending += chunk
        idx = pending.lower().find(_SOURCES_MARKER)
        if idx != -1:
            safe_prefix = pending[:idx].rstrip("\n")
            if safe_prefix:
                yield safe_prefix
            sources_found = True
            pending = ""
            continue
        if len(pending) > _SOURCES_HOLD_BACK:
            flush, pending = pending[:-_SOURCES_HOLD_BACK], pending[-_SOURCES_HOLD_BACK:]
            yield flush
    if not sources_found and pending:
        yield pending


def _trace_event(stage: str, detail: dict) -> dict:
    """Build an SSE trace event dict and log it server-side in the same
    call — the same pipeline progress already logged via plan_decided/
    retrieval_completed/retrieval_graded/etc. elsewhere in this file, this
    just adds one more named line marking exactly what was fanned out to
    the client, for correlating client-observed timing against the
    existing structured logs."""
    logger.info("trace_event_emitted", extra={"extra_fields": {"stage": stage, **detail}})
    return {"type": "trace", "stage": stage, "detail": detail}


def _match_conversational_reply(query: str) -> str | None:
    """Return a canned reply if query is small talk, else None."""
    normalized = _normalize(query)
    for phrases, response in _CONVERSATIONAL_INTENTS:
        if normalized in phrases:
            return response
    return None


def _build_diagnosis_query(prediction: VisionPrediction, user_query: str | None) -> str:
    """Turn a vision prediction into the query fed to the existing
    retrieval pipeline. Includes crop, not just disease name: several
    LeafSense classes share a disease name across crops (e.g.
    "Bacterial_spot" exists for both peach and tomato, with different
    corpus content), so crop alone disambiguates which document's chunks
    should actually match."""
    base = f"{prediction.disease} on {prediction.crop}" if prediction.disease != "healthy" else f"healthy {prediction.crop}"
    return f"{base}. {user_query}" if user_query else base


@dataclass
class PlanDecision:
    action: str  # "conversational" | "retrieve" | "summarize" | "diagnose"
    document_id: str | None = None


class ChatService:
    def __init__(
        self,
        vector_store: VectorStore,
        llm_client: LLMClient,
        image_vector_store=None,
        agent_memory=None,
    ):
        self._vector_store = vector_store
        self._llm_client = llm_client
        # Phase 4 cross-modal store: image vectors (CLIP space) belong to
        # their own index, injected from get_image_vector_store(). Optional
        # — None keeps retrieval text-only regardless of the config flag.
        self._image_vector_store = image_vector_store
        # Multi-agent layer (config-gated; construction is cheap — no LLM
        # calls happen until decide()/run() are actually invoked):
        #   - the router agent upgrades the keyword planner with LLM intent
        #     classification ("research" is an action the regex planner
        #     can't express);
        #   - the research agent owns the weak/insufficient-retrieval path
        #     with a plan→search→read→synthesize loop.
        # Both degrade to the existing deterministic paths when disabled or
        # when they fail, so enabling them is strictly additive.
        self._router_agent = RouterAgent(llm_client, fallback_planner=self._plan)
        self._research_agent = ResearchAgent(llm_client)
        self._local_research_agent = LocalResearchAgent(llm_client, vector_store)
        # Dynamic tool registry (services/tools/): the agent-facing
        # invocation surface. Where this service's inline paths call
        # retrieve()/search_web()/etc. directly (each @track_tool'd once),
        # a future Planner/Executor agent calls registry.execute(name, args)
        # instead. Construction is cheap — no I/O until execute() runs.
        self._tool_registry = build_tool_registry()
        self._tool_context = ToolContext(
            vector_store=vector_store,
            llm_client=llm_client,
            agent_memory=agent_memory,
        )
        # AgentExecutor (services/agent_executor.py): the opt-in
        # planner→ReAct-executor orchestration layer behind
        # Settings.agent_executor_enabled. When enabled, eligible queries
        # are handed to a PlanningAgent that produces an ExecutionPlan and
        # an AgentExecutor that runs it tool-by-tool over the registry
        # above, instead of this service's inline corrective loop. Built
        # lazily (construction is cheap — no LLM calls) and only invoked
        # when the flag is on, so the inline path is byte-for-byte
        # unchanged by default.
        self._agent_executor = None
        # Agent memory (services/agent_memory.py): a bounded per-session
        # working memory of turns + extracted facts, injected into later
        # prompts. Optional — None (the default) disables it entirely; the
        # route wires the shared singleton when Settings.agent_memory_enabled.
        # Every interaction is best-effort and never raises into the
        # pipeline: memory is a quality enhancement, not a new failure mode.
        self._agent_memory = agent_memory
        # Response cache: keyed by (normalized_query, session_id, doc_set_hash)
        # Only caches final responses after corrective loop completes.
        # Max 256 entries, LRU eviction.
        self._response_cache: dict[str, ChatResponse] = {}
        self._cache_keys: list[str] = []
        self._max_cache_size = 256

    def _make_cache_key(
        self,
        query: str,
        session_id: str | None,
        vector_store: VectorStore,
        tenant_id: int | None = None,
    ) -> str:
        """Create a cache key from normalized query, session_id, document set
        hash, and tenant_id.

        tenant_id must be part of the key: retrieve() now filters by tenant
        (see retrieval_service.py), so two tenants asking the same question
        can get different, correctly-scoped chunks — without tenant_id
        here, the second tenant could get served the first tenant's cached
        answer straight past that filter.
        """
        normalized = _normalize(query)
        doc_hash = str(vector_store.total_vectors())  # simple proxy for document set
        session = session_id or "no-session"
        tenant = str(tenant_id) if tenant_id is not None else "no-tenant"
        key_str = f"{normalized}|{session}|{doc_hash}|{tenant}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def _get_cached_response(self, cache_key: str) -> ChatResponse | None:
        """Get cached response if exists, move to front (LRU)."""
        if cache_key in self._response_cache:
            # Move to front (most recently used)
            self._cache_keys.remove(cache_key)
            self._cache_keys.insert(0, cache_key)
            return self._response_cache[cache_key]
        return None

    def _cache_response(self, cache_key: str, response: ChatResponse) -> None:
        """Cache response with LRU eviction."""
        if cache_key in self._response_cache:
            self._cache_keys.remove(cache_key)
        elif len(self._cache_keys) >= self._max_cache_size:
            # Evict LRU
            lru_key = self._cache_keys.pop()
            self._response_cache.pop(lru_key, None)
        self._cache_keys.insert(0, cache_key)
        self._response_cache[cache_key] = response

    def _plan(self, query: str, history: list[dict] | None = None) -> PlanDecision:
        """Decide which tool this query needs.

        Plain keyword/regex checks — no LLM call, no external planner.
        history is accepted for a future planner that considers context,
        but isn't used by these checks today.
        """
        if _match_conversational_reply(query) is not None:
            return PlanDecision(action="conversational")

        if _SUMMARIZE_RE.search(query):
            match = _DOCUMENT_ID_RE.search(query)
            if match:
                return PlanDecision(action="summarize", document_id=match.group(0))

        return PlanDecision(action="retrieve")

    def _agent_executor_instance(self):
        """Lazily construct the AgentExecutor (services/agent_executor.py)
        the first time it's needed. Cheap — no LLM calls until execute().
        Deliberately not built in __init__: the executor is only ever
        exercised when Settings.agent_executor_enabled, and constructing it
        unconditionally would force every /chat request (and the eval
        harness, which constructs ChatService directly) through its import
        chain even when disabled."""
        if self._agent_executor is None:
            from app.services.agent_executor import AgentExecutor
            from app.services.planning_agent import PlanningAgent

            self._agent_executor = AgentExecutor(
                llm_client=self._llm_client,
                tool_registry=self._tool_registry,
                planning_agent=PlanningAgent(self._llm_client, self._tool_registry),
                agent_memory=self._agent_memory,
            )
        return self._agent_executor

    def _handle_via_executor(
        self,
        query: str,
        history: list[dict] | None,
        session_id: str | None,
        tenant_id: int | None,
        top_k: int | None,
        min_score: float | None,
        confirm_web_search: bool,
        persona: str | None,
    ) -> ChatResponse:
        """Run a query through the AgentExecutor path and return a
        ChatResponse. The executor is async; handle_query is sync, so this
        bridges by driving the executor's coroutine on a short-lived event
        loop. Called only when Settings.agent_executor_enabled."""
        import asyncio

        executor = self._agent_executor_instance()
        context = ToolContext(
            vector_store=self._vector_store,
            llm_client=self._llm_client,
            tenant_id=tenant_id,
            session_id=session_id,
            agent_memory=self._agent_memory,
        )

        async def _run() -> ChatResponse:
            result = await executor.execute(
                query,
                context=context,
                session_id=session_id,
                history=history,
                top_k=top_k,
                min_score=min_score,
                confirm_web_search=confirm_web_search,
                persona=persona,
            )
            return ChatResponse(
                answer=result.answer,
                retrieved_chunks=result.retrieved_chunks,
                sources=result.sources,
                processing_time=round(result.processing_time, 4),
                tool_used=result.tool_used,
                steps_taken=result.steps_taken,
                answer_source=result.answer_source,
                hallucination_detected=result.hallucination_detected,
                hallucination_score=result.hallucination_score,
                follow_up_questions=result.follow_up_questions,
                session_id=session_id or "",
            )

        try:
            return asyncio.run(_run())
        except RuntimeError:
            # A running event loop (async test / async route) can't be
            # asyncio.run()'d over — drive the coroutine on the existing
            # loop instead.
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_run())

    def _inject_memory(self, history: list[dict] | None, session_id: str | None) -> list[dict] | None:
        """Append the session's remembered facts to the history passed to
        the router and generation prompts, as a synthetic system turn.

        No-op (returns history unchanged) when agent memory is disabled, no
        session is in play, or nothing is remembered yet — the injected
        block is the durable fact layer, while the live conversation turns
        already flow through history as normal user/assistant turns. A
        memory failure degrades to the un-augmented history, never raises.
        """
        if self._agent_memory is None or not settings.agent_memory_enabled or not session_id:
            return history
        try:
            block = self._agent_memory.build_context(session_id)
        except Exception as exc:
            logger.warning(
                "agent_memory_context_failed",
                extra={"extra_fields": {"session_id": session_id, "error": str(exc)}},
            )
            return history
        if not block:
            return history
        # Drop any earlier synthetic memory turn so a re-route (or a
        # retried request) doesn't stack stale fact blocks, then append the
        # fresh one last — trailing turns survive the history cap slicing.
        turns = [t for t in (history or []) if t.get("role") != "system"]
        return turns + [{"role": "system", "content": block}]

    def _extract_facts(self, query: str, answer: str) -> list[tuple[str, str, str]]:
        """Extract durable factual claims from a Q&A exchange via one
        JSON-mode LLM call. Returns a list of (key, value, confidence)
        tuples; [] on any parse failure or when the model found nothing
        worth remembering. Never raises — callers wrap this in _remember's
        exception guard."""
        prompt = (
            "Extract the durable factual claims from this question-answer "
            'exchange — the concrete facts a later question might want to '
            'refer back to (e.g. "project deadline", "team size"). Exclude '
            "conversational filler, opinions, and transient remarks.\n"
            'Return ONLY a single JSON object, no prose, matching exactly '
            '{"facts": [{"key": "<short lowercase label>", "value": "<the '
            'claim>", "confidence": "high" | "medium" | "low"}]}. '
            'Return {"facts": []} if there are no durable facts.\n\n'
            f"Question: {query}\nAnswer: {answer}"
        )
        raw = self._llm_client.generate(prompt).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        import json

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                payload = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return []
        facts = payload.get("facts") if isinstance(payload, dict) else None
        if not isinstance(facts, list):
            return []
        out: list[tuple[str, str, str]] = []
        for item in facts:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip().lower()
            value = str(item.get("value", "")).strip()
            if not key or not value:
                continue
            confidence = str(item.get("confidence", "medium")).strip().lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            out.append((key, value, confidence))
        return out

    def _remember(
        self,
        session_id: str | None,
        query: str,
        answer: str,
        chunks: list[RetrievedChunk],
        query_type: str,
    ) -> None:
        """Record this exchange into agent memory: the two turns always,
        and — when fact extraction is enabled — durable key/value facts
        extracted from the answer. Small talk is skipped for fact
        extraction (nothing worth remembering). Best-effort and fully
        swallowed on failure — memory is a quality enhancement, never a new
        failure mode."""
        if self._agent_memory is None or not settings.agent_memory_enabled or not session_id:
            return
        try:
            self._agent_memory.add_turn(session_id, "user", query)
            self._agent_memory.add_turn(session_id, "assistant", answer)
        except Exception as exc:
            logger.warning(
                "agent_memory_turn_failed",
                extra={"extra_fields": {"session_id": session_id, "error": str(exc)}},
            )
            return

        if not settings.agent_memory_fact_extraction_enabled or query_type == "conversational":
            return
        try:
            facts = self._extract_facts(query, answer)
        except Exception as exc:
            logger.warning(
                "agent_memory_extraction_failed",
                extra={"extra_fields": {"session_id": session_id, "error": str(exc)}},
            )
            return
        if not facts:
            return
        source_chunk_ids = [chunk.chunk_id for chunk in chunks]
        for key, value, confidence in facts:
            self._agent_memory.upsert_fact(
                session_id, key, value, confidence=confidence, source_chunk_ids=source_chunk_ids
            )
        logger.info(
            "agent_memory_facts_stored",
            extra={"extra_fields": {"session_id": session_id, "fact_count": len(facts)}},
        )

    def _route(self, query: str, history: list[dict] | None = None) -> PlanDecision:
        """Decide the query's action: the keyword planner, upgraded by the
        LLM router agent when Settings.agent_routing_enabled.

        The router can return "research" — the one action the regex
        planner can't express — and degrades to the planner's decision on
        any failure, so routing is additive, never a new failure mode.
        """
        injection_categories = detect_possible_injection(query)
        if injection_categories:
            logger.warning(
                "possible_injection_detected",
                extra={"extra_fields": {"source": "query", "categories": injection_categories}},
            )

        plan = self._plan(query, history)
        if not settings.agent_routing_enabled:
            return plan
        routed = self._router_agent.decide(query, history)
        if routed.action != plan.action or routed.document_id != plan.document_id:
            logger.info(
                "router_decision",
                extra={
                    "extra_fields": {
                        "planner_action": plan.action,
                        "routed_action": routed.action,
                        "document_id": routed.document_id,
                        "query_length": len(query),
                    }
                },
            )
        return PlanDecision(action=routed.action, document_id=routed.document_id)

    def _research_handoff(
        self, query: str, confirm_web_search: bool, *, reason: str
    ) -> ResearchFindings:
        """Hand the query to the Research agent (the handoff event is what
        the checklist's Agent Handoff Accuracy is computed from). reason is
        the trigger — "planned" (router chose research) or "weak_grade"
        (retrieval graded weak/insufficient)."""
        log_agent_handoff("router" if reason == "planned" else "retrieval_grader", "research", query, reason=reason)
        return self._research_agent.run(query, confirm_web_search=confirm_web_search)

    def _research_steps(self, findings: ResearchFindings) -> int:
        """How many of ChatResponse.steps_taken a research pass accounts
        for: the handoff plus one per sub-step the agent actually took."""
        return 1 + len(findings.steps)

    def _generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict] | None,
        extra_instruction: str | None = None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> str:
        prompt = build_prompt(
            query,
            chunks,
            history=history,
            extra_instruction=extra_instruction,
            web_results=web_results,
            persona=persona,
        )
        _capture_prompt(prompt, variant="reflection" if extra_instruction else "standard")
        logger.info(
            "generation_requested",
            extra={
                "extra_fields": {
                    "prompt_version": PROMPT_VERSION,
                    "chunk_count": len(chunks),
                    "web_result_count": len(web_results) if web_results else 0,
                    "is_reflection": extra_instruction is not None,
                }
            },
        )
        return strip_sources_section(self._llm_client.generate(prompt))

    def _generate_streamed(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict] | None,
        extra_instruction: str | None = None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> Iterator[tuple[bool, str]]:
        """Streamed counterpart to _generate: same prompt-building and
        logging, but yields (False, piece) for each safe-to-show chunk of
        raw model output as it arrives, then exactly one final
        (True, final_answer) once the stream ends — final_answer is
        strip_sources_section()-cleaned the same way _generate()'s return
        value is, computed from the complete raw text so it's identical
        regardless of how the provider happened to chunk it.
        """
        prompt = build_prompt(
            query,
            chunks,
            history=history,
            extra_instruction=extra_instruction,
            web_results=web_results,
            persona=persona,
        )
        _capture_prompt(prompt, variant="streamed")
        logger.info(
            "generation_requested",
            extra={
                "extra_fields": {
                    "prompt_version": PROMPT_VERSION,
                    "chunk_count": len(chunks),
                    "web_result_count": len(web_results) if web_results else 0,
                    "is_reflection": extra_instruction is not None,
                    "streamed": True,
                }
            },
        )

        raw_parts: list[str] = []

        def _raw_stream() -> Iterator[str]:
            for piece in self._llm_client.generate_stream(prompt):
                raw_parts.append(piece)
                yield piece

        for filtered_piece in _stream_filtering_sources(_raw_stream()):
            yield (False, filtered_piece)

        yield (True, strip_sources_section("".join(raw_parts)))

    def _generate_structured(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict] | None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> str:
        """Structured-output counterpart to _generate: same context assembly
        via build_structured_prompt, but the provider is asked for a JSON
        object (response_mime_type / response_format) which is parsed and
        validated against StructuredAnswer. The validated `answer` field is
        returned; on any parse failure the request degrades to the plain
        free-text path (parse_structured_answer never raises) — structured
        output is a win-when-it-works enhancement, never a new failure mode.
        """
        prompt = build_structured_prompt(query, chunks, history=history, web_results=web_results, persona=persona)
        _capture_prompt(prompt, variant="structured")
        logger.info(
            "generation_requested",
            extra={
                "extra_fields": {
                    "prompt_version": PROMPT_VERSION,
                    "chunk_count": len(chunks),
                    "web_result_count": len(web_results) if web_results else 0,
                    "structured": True,
                }
            },
        )
        raw = self._llm_client.generate_structured(prompt)
        structured = parse_structured_answer(raw)
        if structured is None:
            logger.info(
                "structured_output_fallback",
                extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
            )
            return self._generate(query, chunks, history, web_results=web_results, persona=persona)
        logger.info(
            "structured_output_success",
            extra={
                "extra_fields": {
                    "query_length": len(query),
                    "source_count": len(structured.sources),
                }
            },
        )
        return structured.answer

    def _grade_retrieval(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Cheap heuristic grade of retrieval quality — no LLM call, a
        function of chunk count and top score alone. query is accepted for
        a future semantic grader but isn't used by this heuristic today
        (same pattern as _plan's history parameter).

        - "insufficient": nothing survived retrieval_service's min_score
          floor.
        - "weak": chunks survived that floor, but the top score is still
          below Settings.retrieval_grade_threshold — technically on-topic,
          not confidently so.
        - "good": top score clears the threshold.

        A "weak"/"insufficient" grade is what makes the web search fallback
        eligible to fire (see handle_query), if Settings.web_search_enabled.
        """
        if not chunks:
            grade, top_score = "insufficient", None
        else:
            top_score = max(chunk.score for chunk in chunks)
            grade = "good" if top_score >= settings.retrieval_grade_threshold else "weak"

        logger.info(
            "retrieval_graded",
            extra={"extra_fields": {"grade": grade, "top_score": top_score, "chunk_count": len(chunks)}},
        )
        get_metrics().record_retrieval_grade(grade)
        return grade

    def _contextualize_query(self, query: str, history: list[dict] | None) -> str:
        """Rewrite a follow-up question into a standalone one, using
        conversation history, before it's used for retrieval. Only called
        when history is non-empty. Degrades to the raw query on any LLM
        failure — this is a retrieval-quality enhancement, never a
        dependency the request can fail on.
        """
        if not history:
            return query
        prompt = (
            "Conversation history:\n"
            + "\n".join(f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in history)
            + f"\n\nFollow-up question: {query}\n\n"
            "Rewrite the follow-up question as a standalone question that "
            "makes sense without the conversation history. Return ONLY the "
            "rewritten question, nothing else."
        )
        try:
            rewritten = self._llm_client.generate(prompt).strip()
            return rewritten if rewritten else query
        except Exception:
            return query

    def _verify_citations(self, answer: str, chunks: list[RetrievedChunk]) -> bool:
        """True if every [N] citation in `answer` is actually supported by
        its cited chunk's text. True (pass) if there are no citations to
        check, or on any LLM/parse failure — this is a stricter check
        layered on top of _is_ungrounded, never a stricter gate that can
        make an otherwise-fine answer fail closed.
        """
        citation_numbers = sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", answer)))
        if not citation_numbers:
            return True
        chunk_by_number = {i + 1: chunk for i, chunk in enumerate(chunks)}
        cited_pairs = [
            (n, chunk_by_number[n].text) for n in citation_numbers if n in chunk_by_number
        ]
        if not cited_pairs:
            return True
        prompt = (
            "Answer:\n" + answer + "\n\n"
            + "\n\n".join(f"Excerpt [{n}]:\n{text}" for n, text in cited_pairs)
            + "\n\nFor each excerpt number above, does the answer's claim "
            "attributed to it actually match what that excerpt says? "
            'Respond with ONLY a JSON object like {"1": true, "2": false}, '
            "one entry per excerpt number shown."
        )
        try:
            import json

            raw = self._llm_client.generate(prompt).strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(raw)
            return all(result.get(str(n), True) for n, _ in cited_pairs)
        except Exception:
            return True

    def _suggest_follow_ups(self, query: str, answer: str) -> list[str]:
        """Suggest up to 3 short follow-up questions. Degrades to an
        empty list on any LLM/parse failure — never blocks or fails the
        main answer."""
        prompt = (
            f"Question: {query}\nAnswer: {answer}\n\n"
            "Suggest up to 3 short, natural follow-up questions the user "
            'might ask next. Return ONLY a JSON array of strings, e.g. '
            '["question one?", "question two?"]. Return an empty array [] '
            "if you can't think of good ones."
        )
        try:
            import json

            raw = self._llm_client.generate(prompt).strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(raw)
            return [str(q) for q in result][:3] if isinstance(result, list) else []
        except Exception:
            return []

    def _search_web(self, query: str, confirm_web_search: bool = False) -> list[WebSearchResult]:
        """Best-effort web search. A failure here degrades to an empty
        result list rather than failing the whole chat request — web
        search is an enhancement to the corrective loop, not a dependency
        the request can't survive without.

        The human-approval gate: when Settings.web_search_requires_approval
        is on, web search is skipped unless the client explicitly sent
        confirm_web_search=true (see ChatRequest). A skipped-but-requested
        search is logged distinctly from a failed one, so the two are
        distinguishable in monitoring.
        """
        if settings.web_search_requires_approval and not confirm_web_search:
            logger.info(
                "web_search_skipped_pending_approval",
                extra={"extra_fields": {"query_length": len(query)}},
            )
            # Feature #5 — surface the skipped action as a pending approval
            # so an operator can grant/reject it via the approval queue
            # (GET /approvals, POST /approvals/{id}/resolve) instead of it
            # vanishing into a log line.
            from app.core.request_context import get_client_name
            from app.services.approval_service import get_approval_store

            approval = get_approval_store().register(
                action="web_search",
                requested_by=get_client_name(),
                payload={"query": query},
            )
            logger.info(
                "approval_created_for_skipped_web_search",
                extra={
                    "extra_fields": {
                        "approval_id": approval.approval_id,
                        "query_length": len(query),
                    }
                },
            )
            return []
        if not web_search_ready():
            # Feature #7 — force-disable without key: a provider that
            # isn't usable is treated as disabled (degrade to []) rather
            # than as a real search that merely found nothing. The
            # distinct "web_search_unavailable" event is logged inside
            # web_search_ready(). Callers should retry after fixing config.
            return []
        try:
            results = search_web(query)
            if results:
                get_metrics().record_web_search_fallback(stage="retrieval")
            return results
        except WebSearchError as exc:
            logger.warning("web_search_failed", extra={"extra_fields": {"error": str(exc)}})
            return []

    def _is_ungrounded(
        self, answer: str, chunks: list[RetrievedChunk], web_results: list[WebSearchResult]
    ) -> bool:
        """True if the answer looks like it ignored context that was
        actually available: empty, or exactly the fixed fallback line,
        while there was at least one chunk or web result it could have
        drawn from. If there's no context at all, the fallback line is the
        correct, expected answer — not a failure to correct."""
        if not chunks and not web_results:
            return False
        return not answer.strip() or answer.strip() == FALLBACK_REPLY

    def _correct(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        answer: str,
        history: list[dict] | None,
        web_results: list[WebSearchResult],
        web_search_attempted: bool,
        llm_calls: int,
        steps_taken: int,
        confirm_web_search: bool = False,
        persona: str | None = None,
    ) -> tuple[str, int, int, list[WebSearchResult], bool]:
        """Generalizes the old single-shot _reflect into the corrective
        RAG loop's regeneration stage.

        If the answer fails the groundedness check (empty, or the fixed
        fallback line) despite having context, regenerate once. If it's
        still ungrounded and web search is enabled but wasn't already
        pulled in for this request, fetch web results and make one final
        attempt with them added to the context. Capped at _MAX_LLM_CALLS
        total generate() calls (checked before each additional call) —
        hitting the cap logs "loop_capped" and returns whatever answer
        exists rather than looping further.

        Returns (answer, llm_calls, steps_taken, web_results,
        web_search_attempted) — web_results/web_search_attempted come back
        out since this method may fetch them partway through, and the
        caller needs the final values to build sources/answer_source.
        """
        ungrounded = self._is_ungrounded(answer, chunks, web_results) or (
            settings.citation_verification_enabled and not self._verify_citations(answer, chunks)
        )
        if not ungrounded:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if llm_calls >= _MAX_LLM_CALLS:
            get_metrics().inc_counter("loop_capped_total", {"stage": "reflection"})
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "reflection"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info(
            "reflection_triggered",
            extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
        )
        answer = self._generate(
            query,
            chunks,
            history,
            extra_instruction=REFLECTION_INSTRUCTION,
            web_results=web_results,
            persona=persona,
        )
        llm_calls += 1
        steps_taken += 1  # regeneration

        if not self._is_ungrounded(answer, chunks, web_results):
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if web_search_attempted or not settings.web_search_enabled:
            # Either web context was already in play for this request and
            # didn't help, or the fallback isn't enabled — no further
            # corrective option, return the best answer we have.
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if llm_calls >= _MAX_LLM_CALLS:
            get_metrics().inc_counter("loop_capped_total", {"stage": "web_fallback"})
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "web_fallback"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        web_results = self._search_web(query, confirm_web_search=confirm_web_search)
        web_search_attempted = True
        steps_taken += 1  # web search

        if not web_results:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info("web_fallback_triggered", extra={"extra_fields": {"query_length": len(query)}})
        answer = self._generate(
            query,
            chunks,
            history,
            extra_instruction=REFLECTION_INSTRUCTION,
            web_results=web_results,
            persona=persona,
        )
        llm_calls += 1
        steps_taken += 1  # regeneration with web context

        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    def _correct_streamed(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        answer: str,
        history: list[dict] | None,
        web_results: list[WebSearchResult],
        web_search_attempted: bool,
        llm_calls: int,
        steps_taken: int,
        confirm_web_search: bool = False,
        persona: str | None = None,
    ) -> Iterator[dict]:
        """Streamed counterpart to _correct — mirrors its exact branches,
        conditions, and log lines (the two must be kept in sync; a
        divergence here is a real behavioral difference between /chat and
        /chat/stream, not just a cosmetic one) but yields a "reflecting"
        trace event plus streamed answer_chunk pieces for each
        regeneration instead of blocking on generate(). Ends with `return
        (answer, llm_calls, steps_taken, web_results, web_search_attempted)`
        — the value of `yield from self._correct_streamed(...)` in the
        caller, per normal generator-return semantics.

        A "reflecting" trace event means the answer streamed so far
        belongs to a discarded attempt: a fresh one is about to start from
        scratch, not continue it. See README's /chat/stream section for
        the exact client-side contract.
        """
        ungrounded = self._is_ungrounded(answer, chunks, web_results) or (
            settings.citation_verification_enabled and not self._verify_citations(answer, chunks)
        )
        if not ungrounded:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if llm_calls >= _MAX_LLM_CALLS:
            get_metrics().inc_counter("loop_capped_total", {"stage": "reflection"})
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "reflection"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info(
            "reflection_triggered",
            extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
        )
        yield _trace_event("reflecting", {"reason": "ungrounded_answer"})
        answer = ""
        for is_final, value in self._generate_streamed(
            query,
            chunks,
            history,
            extra_instruction=REFLECTION_INSTRUCTION,
            web_results=web_results,
            persona=persona,
        ):
            if is_final:
                answer = value
            else:
                yield {"type": "answer_chunk", "text": value}
        llm_calls += 1
        steps_taken += 1  # regeneration

        if not self._is_ungrounded(answer, chunks, web_results):
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if web_search_attempted or not settings.web_search_enabled:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if llm_calls >= _MAX_LLM_CALLS:
            get_metrics().inc_counter("loop_capped_total", {"stage": "web_fallback"})
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "web_fallback"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        web_results = self._search_web(query, confirm_web_search=confirm_web_search)
        web_search_attempted = True
        steps_taken += 1  # web search
        yield _trace_event("web_search", {"result_count": len(web_results)})

        if not web_results:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info("web_fallback_triggered", extra={"extra_fields": {"query_length": len(query)}})
        yield _trace_event("reflecting", {"reason": "web_fallback"})
        answer = ""
        for is_final, value in self._generate_streamed(
            query,
            chunks,
            history,
            extra_instruction=REFLECTION_INSTRUCTION,
            web_results=web_results,
            persona=persona,
        ):
            if is_final:
                answer = value
            else:
                yield {"type": "answer_chunk", "text": value}
        llm_calls += 1
        steps_taken += 1  # regeneration with web context

        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    def handle_query(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        confirm_web_search: bool = False,
        structured_response: bool = False,
        tenant_id: int | None = None,
        persona: str | None = None,
        document_ids: list[str] | None = None,
    ) -> ChatResponse:
        start = time.perf_counter()
        steps_taken = 1  # planning
        reset_usage()  # per-request LLM token/cost rollup

        # Agent memory: append the session's remembered facts to the
        # history before routing/generation, so the router and the model
        # can draw on what was established earlier in the conversation.
        history = self._inject_memory(history, session_id)

        plan = self._route(query, history)
        logger.info(
            "plan_decided",
            extra={"extra_fields": {"action": plan.action, "query_length": len(query)}},
        )

        if settings.agent_executor_enabled and plan.action in ("retrieve", "research"):
            # AgentExecutor orchestration (Feature: planner → ReAct
            # executor over the dynamic tool registry). Only for the
            # retrieval/research paths — small talk and summarization stay
            # on the cheap inline paths (conversational needs no tools at
            # all, and summarize is a single tool call that the executor
            # would add planning overhead to for no benefit).
            return self._handle_via_executor(
                query,
                history=history,
                session_id=session_id,
                tenant_id=tenant_id,
                top_k=top_k,
                min_score=min_score,
                confirm_web_search=confirm_web_search,
                persona=persona,
            )

        if plan.action == "conversational":
            return self._respond(
                answer=_match_conversational_reply(query),
                retrieved_chunks=[],
                query=query,
                query_type="conversational",
                tool_used="none",
                steps_taken=steps_taken,
                start=start,
                session_id=session_id,
            )

        recent_history = history[-_MAX_HISTORY_TURNS:] if history else None

        try:
            if plan.action == "summarize":
                steps_taken += 1  # fetch document chunks
                summary, chunks = summarize_document(
                    plan.document_id, self._vector_store, self._llm_client, tenant_id=tenant_id
                )
                steps_taken += 1  # generation
                return self._respond(
                    answer=summary,
                    retrieved_chunks=chunks,
                    query=query,
                    query_type="summarize",
                    tool_used="summarization",
                    steps_taken=steps_taken,
                    start=start,
                    session_id=session_id,
                )

            # plan.action in ("retrieve", "research") — the corrective RAG
            # loop. Check cache first (only cache final responses after
            # corrective loop, and only for plain retrieve — a research
            # answer depends on live web state, so it's never cached).
            cache_key = self._make_cache_key(query, session_id, self._vector_store, tenant_id=tenant_id)
            cached = self._get_cached_response(cache_key)
            if cached is not None:
                logger.info("cache_hit", extra={"extra_fields": {"session_id": session_id or "none"}})
                return cached

            steps_taken += 1  # retrieval
            # A follow-up question retrieves blind to conversation context
            # unless it's first rewritten into a standalone question (see
            # Settings.query_contextualization_enabled) — the raw follow-up
            # text alone ("what about the other one?") is a poor query.
            # Only the value passed into retrieve() changes; every other use
            # of `query` (generation, citations, caching, logging) stays the
            # original user text.
            retrieval_query = query
            if settings.query_contextualization_enabled and recent_history:
                retrieval_query = self._contextualize_query(query, recent_history)
            retrieve_kwargs: dict = {
                "top_k": top_k,
                "min_score": min_score,
                "tenant_id": tenant_id,
                "image_vector_store": self._image_vector_store,
            }
            if document_ids is not None:
                retrieve_kwargs["document_ids"] = document_ids
            chunks = retrieve(retrieval_query, self._vector_store, **retrieve_kwargs)

            steps_taken += 1  # grading
            grade = self._grade_retrieval(retrieval_query, chunks)

            # Vision-grounded QA (Phase 3 of multi-modal RAG): when
            # retrieval came back weak/insufficient, the low-text pages of
            # the most relevant document may contain the answer as an image
            # even though their text layer (and thus retrieval) is thin —
            # send those page rasters straight to a vision-capable LLM. Off
            # by default (a paid vision call per attempt); degrades to None
            # and falls through to the web-search path below when the
            # document has no page rasters or the provider can't see images.
            if settings.vision_qa_enabled and grade != "good":
                vision_answer = try_vision_qa(query, chunks, self._llm_client)
                if vision_answer:
                    steps_taken += 1  # vision QA
                    return self._respond(
                        answer=vision_answer,
                        retrieved_chunks=chunks,
                        query=query,
                        query_type="document_query",
                        tool_used="vision_qa",
                        steps_taken=steps_taken,
                        start=start,
                        session_id=session_id,
                    )

            # A weak/insufficient grade pulls in web context *before* the
            # first generation attempt, so the model has it alongside
            # whatever chunks did come back (the "corrective" part of
            # corrective RAG). With the research agent enabled, that web
            # pass is a full plan→search→read→synthesize agent handoff
            # instead of a single search_web() call; if the research agent
            # comes back empty (or is disabled), fall back to the plain
            # web-search fallback as before.
            #
            # plan.action == "research" forces this block even when the
            # grade came back "good": the router only assigns "research"
            # when it judged the query outside the corpus entirely, and
            # gating that purely on the retrieval-score heuristic would let
            # a coincidentally-high-scoring but wrong chunk silently
            # override the router's explicit decision.
            web_results: list[WebSearchResult] = []
            web_search_attempted = False
            research_attempted = False
            # Local Document Research Agent (Agent 2.3): when retrieval came
            # back weak/insufficient, hand the query to a plan-decompose-
            # search-synthesize loop pointed at this app's OWN document
            # retrieval instead of the web — useful for questions that need
            # combining content from different parts of a document. Checked
            # before the web research handoff: local documents are the
            # primary source of truth. Off by default.
            if settings.local_research_agent_enabled and grade != "good":
                local_findings = self._local_research_agent.run(retrieval_query, tenant_id=tenant_id)
                if local_findings.answer:
                    steps_taken += 1  # local research pass
                    return self._respond(
                        answer=local_findings.answer,
                        retrieved_chunks=local_findings.chunks,
                        query=query,
                        query_type="document_query",
                        tool_used="local_research",
                        steps_taken=steps_taken,
                        start=start,
                        session_id=session_id,
                        retrieval_confidence=grade,
                    )
            if grade != "good" or plan.action == "research":
                if settings.research_agent_enabled and settings.web_search_enabled:
                    research_attempted = True
                    findings = self._research_handoff(
                        query, confirm_web_search, reason="planned" if plan.action == "research" else "weak_grade"
                    )
                    if findings.answer:
                        steps_taken += self._research_steps(findings)
                        return self._respond(
                            answer=findings.answer,
                            retrieved_chunks=chunks,
                            query=query,
                            query_type="document_query",
                            tool_used="research_agent",
                            steps_taken=steps_taken,
                            start=start,
                            web_results=findings.results,
                            session_id=session_id,
                        )
                if settings.web_search_enabled and not research_attempted:
                    web_results = self._search_web(query, confirm_web_search=confirm_web_search)
                    web_search_attempted = True
                    steps_taken += 1  # web search

            if settings.structured_output_enabled and structured_response:
                answer = self._generate_structured(
                    query, chunks, recent_history, web_results=web_results, persona=persona
                )
            else:
                answer = self._generate(
                    query, chunks, recent_history, web_results=web_results, persona=persona
                )
            llm_calls = 1
            steps_taken += 1  # generation

            answer, llm_calls, steps_taken, web_results, web_search_attempted = self._correct(
                query,
                chunks,
                answer,
                recent_history,
                web_results,
                web_search_attempted,
                llm_calls,
                steps_taken,
                confirm_web_search=confirm_web_search,
                persona=persona,
            )

            # Agent 1.4 — Ask-instead-of-guess: retrieval graded
            # "insufficient", the corrective loop still couldn't produce a
            # grounded answer (we're sitting on the literal fallback line),
            # and the flag is on — so ask one short clarifying question
            # instead of shipping the canned "couldn't find that" reply. A
            # better outcome when the real problem is an ambiguous question,
            # not missing content. Degrades to today's exact fallback on any
            # LLM failure (except clause leaves answer untouched).
            is_clarifying_question = False
            if (
                settings.clarifying_question_enabled
                and grade == "insufficient"
                and answer.strip() == FALLBACK_REPLY
            ):
                try:
                    clarifying_prompt = (
                        f"The user asked: {query}\n\n"
                        "No relevant information was found in their documents, and "
                        "the question may be ambiguous or missing detail. Suggest "
                        "ONE short clarifying question to ask them. Return ONLY the "
                        "question, nothing else."
                    )
                    clarification = self._llm_client.generate(clarifying_prompt).strip()
                    if clarification:
                        answer = clarification
                        is_clarifying_question = True
                except Exception:
                    pass  # falls through, answer stays FALLBACK_REPLY exactly as today

            # Agent 2.2 — After the main answer, suggest up to 3 natural
            # follow-up questions (the "related questions" pattern). Parsed
            # defensively; any failure degrades to an empty list.
            follow_up_questions = []
            if settings.follow_up_questions_enabled:
                follow_up_questions = self._suggest_follow_ups(query, answer)
        except AppError:
            # Already a well-formed domain exception from retrieval, prompt
            # building, summarization, or the LLM client — propagate it
            # unchanged.
            raise
        except Exception as exc:
            raise ChatServiceError(f"Unexpected error while handling chat query: {exc}") from exc

        # web_results is only non-empty once it's actually been folded into
        # a generation call (see _correct) — a search that was attempted
        # but came back empty leaves this "retrieval", not "web_search".
        tool_used = "web_search" if web_results else "retrieval"
        response = self._respond(
            answer=answer,
            retrieved_chunks=chunks,
            query=query,
            query_type="document_query",
            tool_used=tool_used,
            steps_taken=steps_taken,
            start=start,
            web_results=web_results,
            session_id=session_id,
            retrieval_confidence=grade,
            is_clarifying_question=is_clarifying_question,
            follow_up_questions=follow_up_questions,
        )
        # Cache the final response (retrieve action only — a "research"
        # answer returns early, before this point, since live web state
        # must never be cached).
        if plan.action == "retrieve":
            self._cache_response(cache_key, response)
        return response

    def stream_query(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        confirm_web_search: bool = False,
        structured_response: bool = False,
        tenant_id: int | None = None,
        persona: str | None = None,
        document_ids: list[str] | None = None,
    ) -> Iterator[dict]:
        """Streamed counterpart to handle_query, for POST /chat/stream.

        Same planner and pipeline (conversational / summarize / retrieve
        with its corrective loop) as handle_query, but yields progress as
        it happens instead of returning one ChatResponse at the end. Each
        yielded dict is one of:

        - {"type": "trace", "stage": ..., "detail": {...}} before/after a
          pipeline step. A "reflecting" stage means any answer_chunk text
          streamed before it belongs to a discarded attempt — a fresh one
          is starting over, not continuing it.
        - {"type": "answer_chunk", "text": "..."} — a piece of generated
          text, in order, already filtered so a "Sources:" heading never
          reaches the client (see _stream_filtering_sources).
        - {"type": "error", "detail": {"error_type", "message",
          "status_code"}} — emitted in place of "done" if the pipeline
          fails. SSE responses commit to a 200 status as soon as the
          stream starts, so a mid-stream AppError can't become an HTTP
          error status the way it would on POST /chat; this is how it's
          surfaced instead.
        - exactly one final {"type": "done", "payload": ChatResponse} (on
          success) — the same response shape POST /chat returns.

        routes/query.py's /chat/stream serializes these directly as SSE
        `data:` lines.
        """
        start = time.perf_counter()
        steps_taken = 1  # planning
        reset_usage()  # per-request LLM token/cost rollup

        history = self._inject_memory(history, session_id)

        plan = self._route(query, history)
        logger.info(
            "plan_decided",
            extra={"extra_fields": {"action": plan.action, "query_length": len(query)}},
        )
        yield _trace_event("planning", {"action": plan.action})

        if plan.action == "conversational":
            answer = _match_conversational_reply(query)
            yield {"type": "answer_chunk", "text": answer}
            response = self._respond(
                answer=answer,
                retrieved_chunks=[],
                query=query,
                query_type="conversational",
                tool_used="none",
                steps_taken=steps_taken,
                start=start,
                session_id=session_id,
            )
            yield {"type": "done", "payload": response}
            return

        recent_history = history[-_MAX_HISTORY_TURNS:] if history else None

        try:
            if plan.action == "summarize":
                steps_taken += 1  # fetch document chunks
                yield _trace_event("retrieval", {"document_id": plan.document_id})
                summary, chunks = summarize_document(
                    plan.document_id, self._vector_store, self._llm_client, tenant_id=tenant_id
                )
                steps_taken += 1  # generation
                yield _trace_event("generating", {})
                # summarize_document() calls the LLM's blocking generate(),
                # not generate_stream() — summarization isn't part of this
                # task's streaming scope, so the whole summary is emitted
                # as one chunk rather than faked as a token stream.
                yield {"type": "answer_chunk", "text": summary}
                response = self._respond(
                    answer=summary,
                    retrieved_chunks=chunks,
                    query=query,
                    query_type="summarize",
                    tool_used="summarization",
                    steps_taken=steps_taken,
                    start=start,
                    session_id=session_id,
                )
                yield {"type": "done", "payload": response}
                return

            # plan.action == "retrieve" — the corrective RAG loop, streamed.
            # Check cache first (only cache final responses after corrective loop)
            cache_key = self._make_cache_key(query, session_id, self._vector_store, tenant_id=tenant_id)
            cached = self._get_cached_response(cache_key)
            if cached is not None:
                logger.info("cache_hit", extra={"extra_fields": {"session_id": session_id or "none"}})
                yield {"type": "done", "payload": cached}
                return

            steps_taken += 1  # retrieval
            retrieval_query = query
            if settings.query_contextualization_enabled and recent_history:
                retrieval_query = self._contextualize_query(query, recent_history)
            retrieve_kwargs: dict = {
                "top_k": top_k,
                "min_score": min_score,
                "tenant_id": tenant_id,
                "image_vector_store": self._image_vector_store,
            }
            if document_ids is not None:
                retrieve_kwargs["document_ids"] = document_ids
            chunks = retrieve(retrieval_query, self._vector_store, **retrieve_kwargs)
            yield _trace_event("retrieval", {"chunk_count": len(chunks)})

            steps_taken += 1  # grading
            grade = self._grade_retrieval(retrieval_query, chunks)
            yield _trace_event("grading", {"grade": grade})

            # See handle_query for why plan.action == "research" forces
            # this block regardless of grade.
            web_results: list[WebSearchResult] = []
            web_search_attempted = False
            research_attempted = False
            # Local Document Research Agent (Agent 2.3) — same reasoning and
            # ordering as handle_query: weak/insufficient retrieval gets a
            # plan-decompose-search-synthesize pass over the app's OWN
            # documents before the web research handoff.
            if settings.local_research_agent_enabled and grade != "good":
                yield _trace_event("local_research", {"query": retrieval_query})
                local_findings = self._local_research_agent.run(retrieval_query, tenant_id=tenant_id)
                if local_findings.answer:
                    steps_taken += 1  # local research pass
                    yield {"type": "answer_chunk", "text": local_findings.answer}
                    response = self._respond(
                        answer=local_findings.answer,
                        retrieved_chunks=local_findings.chunks,
                        query=query,
                        query_type="document_query",
                        tool_used="local_research",
                        steps_taken=steps_taken,
                        start=start,
                        session_id=session_id,
                        retrieval_confidence=grade,
                    )
                    yield {"type": "done", "payload": response}
                    return
            if grade != "good" or plan.action == "research":
                if settings.research_agent_enabled and settings.web_search_enabled:
                    research_attempted = True
                    yield _trace_event(
                        "research_handoff",
                        {"reason": "planned" if plan.action == "research" else "weak_grade"},
                    )
                    findings = self._research_handoff(
                        query, confirm_web_search, reason="planned" if plan.action == "research" else "weak_grade"
                    )
                    for step in findings.steps:
                        yield _trace_event(f"research_{step['stage']}", step)
                    if findings.answer:
                        steps_taken += self._research_steps(findings)
                        yield {"type": "answer_chunk", "text": findings.answer}
                        response = self._respond(
                            answer=findings.answer,
                            retrieved_chunks=chunks,
                            query=query,
                            query_type="document_query",
                            tool_used="research_agent",
                            steps_taken=steps_taken,
                            start=start,
                            web_results=findings.results,
                            session_id=session_id,
                        )
                        yield {"type": "done", "payload": response}
                        return
                if settings.web_search_enabled and not research_attempted:
                    web_results = self._search_web(query, confirm_web_search=confirm_web_search)
                    web_search_attempted = True
                    steps_taken += 1  # web search
                    yield _trace_event("web_search", {"result_count": len(web_results)})

            yield _trace_event("generating", {})
            answer = ""
            for is_final, value in self._generate_streamed(
                query, chunks, recent_history, web_results=web_results, persona=persona
            ):
                if is_final:
                    answer = value
                else:
                    yield {"type": "answer_chunk", "text": value}
            llm_calls = 1
            steps_taken += 1  # generation

            answer, llm_calls, steps_taken, web_results, web_search_attempted = yield from self._correct_streamed(
                query,
                chunks,
                answer,
                recent_history,
                web_results,
                web_search_attempted,
                llm_calls,
                steps_taken,
                confirm_web_search=confirm_web_search,
                persona=persona,
            )

            # Same Agent 1.4 ask-instead-of-guess + Agent 2.2 follow-up
            # logic as handle_query. The chunks streamed above are
            # provisional — the done payload's answer is authoritative and
            # the UI renders it.
            is_clarifying_question = False
            if (
                settings.clarifying_question_enabled
                and grade == "insufficient"
                and answer.strip() == FALLBACK_REPLY
            ):
                try:
                    clarifying_prompt = (
                        f"The user asked: {query}\n\n"
                        "No relevant information was found in their documents, and "
                        "the question may be ambiguous or missing detail. Suggest "
                        "ONE short clarifying question to ask them. Return ONLY the "
                        "question, nothing else."
                    )
                    clarification = self._llm_client.generate(clarifying_prompt).strip()
                    if clarification:
                        answer = clarification
                        is_clarifying_question = True
                except Exception:
                    pass  # falls through, answer stays FALLBACK_REPLY exactly as today

            follow_up_questions = []
            if settings.follow_up_questions_enabled:
                follow_up_questions = self._suggest_follow_ups(query, answer)
        except AppError as exc:
            logger.info(
                "chat_stream_error",
                extra={"extra_fields": {"error_type": type(exc).__name__, "status_code": exc.status_code}},
            )
            yield {
                "type": "error",
                "detail": {"error_type": type(exc).__name__, "message": exc.detail, "status_code": exc.status_code},
            }
            return
        except Exception as exc:
            chat_error = ChatServiceError(f"Unexpected error while handling chat query: {exc}")
            logger.info(
                "chat_stream_error",
                extra={"extra_fields": {"error_type": type(chat_error).__name__, "status_code": chat_error.status_code}},
            )
            yield {
                "type": "error",
                "detail": {
                    "error_type": type(chat_error).__name__,
                    "message": chat_error.detail,
                    "status_code": chat_error.status_code,
                },
            }
            return

        tool_used = "web_search" if web_results else "retrieval"
        response = self._respond(
            answer=answer,
            retrieved_chunks=chunks,
            query=query,
            query_type="document_query",
            tool_used=tool_used,
            steps_taken=steps_taken,
            start=start,
            web_results=web_results,
            session_id=session_id,
            retrieval_confidence=grade,
            is_clarifying_question=is_clarifying_question,
            follow_up_questions=follow_up_questions,
        )
        # Cache the final response (retrieve action only — a "research"
        # answer returns early, above, since live web state is never cached).
        if plan.action == "retrieve":
            self._cache_response(cache_key, response)
        yield {"type": "done", "payload": response}

    def handle_diagnose(
        self,
        image_bytes: bytes,
        filename: str,
        content_type: str,
        query: str | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        confirm_web_search: bool = False,
        tenant_id: int | None = None,
    ) -> ChatResponse:
        """Diagnose a plant photo via LeafSense, then run the predicted
        disease through the same corrective RAG loop handle_query uses —
        the diagnose action doesn't get its own retrieval/grounding logic,
        it just supplies a different query to the existing one.

        Image presence is treated as an unambiguous routing signal (unlike
        _plan's text classification, there's no ambiguity to resolve), so
        this bypasses _plan() entirely rather than trying to teach it about
        images; PlanDecision(action="diagnose") is still logged the same
        way _plan's decisions are, for observability parity.

        If the corpus has no content for the diagnosed crop, this falls
        through to the same "couldn't find that in the uploaded documents"
        fallback a normal text query would get for an off-topic question —
        no special-casing, since it's the same retrieval-then-generate path.
        """
        start = time.perf_counter()
        steps_taken = 1  # planning

        plan = PlanDecision(action="diagnose")
        reset_usage()  # per-request LLM token/cost rollup
        logger.info(
            "plan_decided",
            extra={"extra_fields": {"action": plan.action, "query_length": len(query) if query else 0}},
        )

        history = self._inject_memory(history, session_id)

        recent_history = history[-_MAX_HISTORY_TURNS:] if history else None

        try:
            steps_taken += 1  # vision inference
            prediction = diagnose_image(image_bytes, filename, content_type)

            diagnosis_query = _build_diagnosis_query(prediction, query)

            steps_taken += 1  # retrieval
            chunks = retrieve(
                diagnosis_query, self._vector_store, tenant_id=tenant_id, image_vector_store=self._image_vector_store
            )

            steps_taken += 1  # grading
            grade = self._grade_retrieval(diagnosis_query, chunks)

            web_results: list[WebSearchResult] = []
            web_search_attempted = False
            research_attempted = False
            if grade != "good":
                if settings.research_agent_enabled and settings.web_search_enabled:
                    research_attempted = True
                    findings = self._research_handoff(diagnosis_query, confirm_web_search, reason="diagnose_weak_grade")
                    if findings.answer:
                        steps_taken += self._research_steps(findings)
                        return self._respond(
                            answer=findings.answer,
                            retrieved_chunks=chunks,
                            query=diagnosis_query,
                            query_type="diagnose",
                            tool_used="research_agent",
                            steps_taken=steps_taken,
                            start=start,
                            web_results=findings.results,
                            diagnosis=DiagnosisInfo(
                                raw_class=prediction.raw_class,
                                crop=prediction.crop,
                                disease=prediction.disease,
                                confidence=prediction.confidence,
                                low_confidence=prediction.low_confidence,
                            ),
                            session_id=session_id,
                        )
                if settings.web_search_enabled and not research_attempted:
                    web_results = self._search_web(diagnosis_query, confirm_web_search=confirm_web_search)
                    web_search_attempted = True
                    steps_taken += 1  # web search

            answer = self._generate(diagnosis_query, chunks, recent_history, web_results=web_results)
            llm_calls = 1
            steps_taken += 1  # generation

            answer, llm_calls, steps_taken, web_results, web_search_attempted = self._correct(
                diagnosis_query,
                chunks,
                answer,
                recent_history,
                web_results,
                web_search_attempted,
                llm_calls,
                steps_taken,
                confirm_web_search=confirm_web_search,
            )
        except AppError:
            # Includes VisionServiceError from diagnose_image, alongside the
            # same retrieval/prompt/LLM exceptions handle_query can raise.
            raise
        except Exception as exc:
            raise ChatServiceError(f"Unexpected error while handling image diagnosis: {exc}") from exc

        tool_used = "web_search" if web_results else "diagnose"
        return self._respond(
            answer=answer,
            retrieved_chunks=chunks,
            query=diagnosis_query,
            query_type="diagnose",
            tool_used=tool_used,
            steps_taken=steps_taken,
            start=start,
            web_results=web_results,
            diagnosis=DiagnosisInfo(
                raw_class=prediction.raw_class,
                crop=prediction.crop,
                disease=prediction.disease,
                confidence=prediction.confidence,
                low_confidence=prediction.low_confidence,
            ),
            session_id=session_id,
        )

    def _respond(
        self,
        *,
        answer,
        retrieved_chunks,
        query,
        query_type,
        tool_used,
        steps_taken,
        start,
        web_results: list[WebSearchResult] | None = None,
        diagnosis: DiagnosisInfo | None = None,
        session_id: str | None = None,
        retrieval_confidence: str = "good",
        is_clarifying_question: bool = False,
        follow_up_questions: list[str] | None = None,
    ) -> ChatResponse:
        processing_duration = time.perf_counter() - start
        web_results = web_results or []
        chunk_sources = _source_references(retrieved_chunks)
        web_sources = _web_source_references(web_results, start=len(chunk_sources) + 1)
        sources = chunk_sources + web_sources
        answer_source = _answer_source(retrieved_chunks, web_results)

        # Per-request LLM usage rollup (accumulated via usage_tracking
        # ContextVar by the clients on each generate/generate_stream call).
        usage = current_usage()

        # Feature #4 — lexical groundedness check. Signal-only: the answer
        # is delivered unchanged; a low score just sets the
        # hallucination_detected flag and logs/metrics it for the operator
        # to inspect (and the user to double-check against the sources).
        hallucination_detected, grounding_score = _detect_hallucination(
            answer, retrieved_chunks, web_results
        )
        if hallucination_detected:
            get_metrics().inc_counter(
                "hallucinations_detected_total", {"answer_source": answer_source}
            )
            logger.warning(
                "hallucination_detected",
                extra={
                    "extra_fields": {
                        "grounding_score": grounding_score,
                        "answer_source": answer_source,
                        "answer_length": len(answer),
                    }
                },
            )

        log_fields = {
            "query_length": len(query),
            "query_type": query_type,
            "tool_used": tool_used,
            "steps_taken": steps_taken,
            "retrieved_chunk_count": len(retrieved_chunks),
            "web_result_count": len(web_results),
            "answer_source": answer_source,
            "processing_duration": round(processing_duration, 4),
            "llm_calls": usage["llm_calls"],
            "total_tokens": usage["total_tokens"],
            "estimated_cost_usd": usage["estimated_cost_usd"],
            "grounding_score": grounding_score,
            "hallucination_detected": hallucination_detected,
        }
        if diagnosis is not None:
            log_fields.update(
                {
                    "diagnosis_crop": diagnosis.crop,
                    "diagnosis_disease": diagnosis.disease,
                    "diagnosis_confidence": diagnosis.confidence,
                    "diagnosis_low_confidence": diagnosis.low_confidence,
                }
            )
        logger.info("chat_query_handled", extra={"extra_fields": log_fields})

        # Agent memory: record this exchange (turns, and — when fact
        # extraction is enabled — durable facts) so later questions in the
        # session can draw on it. Best-effort; never affects the response.
        self._remember(session_id, query, answer, retrieved_chunks, query_type)

        return ChatResponse(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            sources=sources,
            processing_time=round(processing_duration, 4),
            tool_used=tool_used,
            steps_taken=steps_taken,
            answer_source=answer_source,
            diagnosis=diagnosis,
            session_id=session_id or "",
            retrieval_confidence=retrieval_confidence,
            is_clarifying_question=is_clarifying_question,
            follow_up_questions=follow_up_questions or [],
            hallucination_detected=hallucination_detected,
            grounding_score=grounding_score,
        )
