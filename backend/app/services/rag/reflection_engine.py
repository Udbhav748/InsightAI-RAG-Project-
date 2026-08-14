"""Corrective self-RAG reflection engine, LLM call capping, and grounding evaluation.

Implements the corrective RAG loop:
- Groundedness scoring and hallucination detection
- Citation verification against retrieved chunk passages
- LLM generation call capping (defensive loop prevention)
- Prompt capture auditing
- Reflection regeneration & Web search fallback escalation (both blocking and streamed)
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.exceptions import WebSearchError
from app.core.metrics import get_metrics
from app.models.schemas import SourceReference
from app.services.prompt_builder import (
    FALLBACK_REPLY,
    PROMPT_VERSION,
    REFLECTION_INSTRUCTION,
    build_prompt,
    build_structured_prompt,
    strip_sources_section,
)
from app.services.rag.stream_adapter import stream_filtering_sources, trace_event
from app.services.structured_output import parse_structured_answer
from app.services.web_search_service import search_web as default_search_web
from app.services.web_search_service import web_search_ready

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from app.models.document import RetrievedChunk, WebSearchResult
    from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Hard ceiling on generate() calls per /chat request (the initial answer,
# plus the corrective loop's reflection and web-fallback regenerations) —
# the loop-prevention/Loop Rate control. The corrective loop as written
# never needs more than 3 (see _correct), so this is a defensive backstop
# against a future change to the loop rather than something normal traffic
# is expected to hit; hitting it logs "loop_capped".
_MAX_LLM_CALLS = 3

# Length of the excerpt shown per cited chunk in ChatResponse.sources.
_EXCERPT_LENGTH = 200

# Small English stopword set for the lexical groundedness check.
_GROUNDEDNESS_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "when",
        "than",
        "that",
        "this",
        "these",
        "those",
        "of",
        "in",
        "on",
        "at",
        "to",
        "from",
        "for",
        "with",
        "without",
        "by",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "must",
        "not",
        "no",
        "yes",
        "it",
        "its",
        "he",
        "she",
        "they",
        "we",
        "you",
        "i",
        "my",
        "your",
        "our",
        "their",
        "about",
        "into",
        "between",
        "over",
        "under",
        "again",
        "also",
        "just",
        "very",
        "too",
        "same",
        "some",
        "such",
        "only",
        "other",
        "any",
        "all",
        "both",
        "each",
        "few",
        "more",
        "most",
        "much",
    }
)


def capture_prompt(prompt: str, *, variant: str) -> None:
    """Log the exact prompt when Settings.log_prompt_content is on."""
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


def excerpt(text: str) -> str:
    """First ~200 chars of a chunk's text, trimmed at a clean boundary."""
    stripped = text.strip()
    if len(stripped) <= _EXCERPT_LENGTH:
        return stripped
    return stripped[:_EXCERPT_LENGTH].rstrip() + "…"


def source_references(chunks: list[RetrievedChunk], start: int = 1) -> list[SourceReference]:
    """One SourceReference per retrieved chunk — chunk-level, not deduped
    by document, so a citation always points at the specific passage the
    answer actually drew from.
    """
    return [
        SourceReference(
            number=i,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            excerpt=excerpt(chunk.text),
            content_type=chunk.metadata.get("content_type", "text"),
            page_number=chunk.metadata.get("page_number"),
        )
        for i, chunk in enumerate(chunks, start=start)
    ]


def web_source_references(results: list[WebSearchResult], start: int = 1) -> list[SourceReference]:
    """One SourceReference per web result, using the same shape as document citations."""
    return [
        SourceReference(
            number=i,
            document_id="web",
            chunk_id=result.url,
            excerpt=excerpt(result.snippet),
            url=result.url,
        )
        for i, result in enumerate(results, start=start)
    ]


def answer_source(chunks: list[RetrievedChunk], web_results: list[WebSearchResult]) -> str:
    """'documents' | 'web' | 'mixed', based on which context actually made
    it into the final prompt — not on what was attempted."""
    if not web_results:
        return "documents"
    return "web" if not chunks else "mixed"


def content_tokens(text: str) -> set[str]:
    """Lowercased, stopword-stripped, alphanumeric content tokens."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _GROUNDEDNESS_STOPWORDS and len(token) > 1
    }


def grounding_score(
    answer: str, chunks: list[RetrievedChunk], web_results: list[WebSearchResult]
) -> float:
    """Fraction of the answer's content tokens that also appear in the
    retrieved context (chunk text + web snippets). 1.0 if the answer has
    no content tokens to compare."""
    answer_tokens = content_tokens(answer)
    if not answer_tokens:
        return 1.0
    context_tokens: set[str] = set()
    for chunk in chunks:
        context_tokens |= content_tokens(chunk.text)
    for result in web_results:
        context_tokens |= content_tokens(result.snippet)
    if not context_tokens:
        return 1.0
    overlap = len(answer_tokens & context_tokens)
    return overlap / len(answer_tokens)


def detect_hallucination(
    answer: str,
    chunks: list[RetrievedChunk],
    web_results: list[WebSearchResult],
) -> tuple[bool, float | None]:
    """Run the lexical groundedness check. Returns (detected, score)."""
    if not settings.hallucination_detection_enabled:
        return False, None
    if len(answer.strip()) < settings.hallucination_min_answer_chars:
        return False, None
    if not chunks and not web_results:
        return False, None
    score = grounding_score(answer, chunks, web_results)
    detected = score < settings.hallucination_grounding_threshold
    return detected, round(score, 4)


def is_ungrounded(
    answer: str, chunks: list[RetrievedChunk], web_results: list[WebSearchResult]
) -> bool:
    """True if the answer looks like it ignored context that was available."""
    if not chunks and not web_results:
        return False
    return not answer.strip() or answer.strip() == FALLBACK_REPLY


# Patterns for identifying chemical active ingredients and safety warnings
_CHEMICAL_INGREDIENT_PATTERN = re.compile(
    r"\b("
    r"chlorothalonil|mancozeb|azoxystrobin|copper hydroxide|copper sulfate|bordeaux mixture|"
    r"propiconazole|myclobutanil|captan|thiophanate-methyl|thiophanate|metalaxyl|mefenoxam|"
    r"boscalid|pyraclostrobin|tebuconazole|difenoconazole|fludioxonil|cyprodinil|iprodione|"
    r"trifloxystrobin|streptomycin|oxytetracycline|kasugamycin|fluxapyroxad|penthiopyrad|"
    r"cyflufenamid|quinoxyfen|fluopicolide|dimethomorph|mandipropamid|zoxamide|cymoxanil|"
    r"glyphosate|imidacloprid|malathion|permethrin|spirotetramat|abamectin|bifenthrin|"
    r"chemical fungicide|chemical bactericide|synthetic fungicide|synthetic bactericide|"
    r"chemical pesticide|chemical spray|fungicide spray|bactericide spray"
    r")\b",
    re.IGNORECASE,
)

_SAFETY_CAUTION_PATTERN = re.compile(
    r"\b("
    r"ppe|personal protective equipment|protective equipment|protective gear|protective clothing|"
    r"gloves|respirator|respirators|eye protection|goggles|safety glasses|face shield|"
    r"re-entry interval|rei|pre-harvest interval|phi|safety caution|safety warning|precaution|"
    r"precautions|safe handling|label instructions|follow the label|read the label|epa registration|"
    r"drift caution|toxicity|toxic to bees|waterway buffer|wear protective|caution:"
    r")\b",
    re.IGNORECASE,
)

CHEMICAL_SAFETY_INSTRUCTION = (
    "Chemical Safety Warning Missing: You recommended chemical active ingredients or pesticides "
    "without including required safety precautions. You must explicitly include chemical safety cautions "
    "(such as Personal Protective Equipment / PPE, Re-Entry Interval / REI, Pre-Harvest Interval / PHI, "
    "or following manufacturer/EPA label safety instructions) alongside your treatment recommendations."
)


def verify_chemical_safety(answer: str) -> bool:
    """Verify that if chemical active ingredients or synthetic treatments are mentioned,
    standard safety cautions (PPE, REI, PHI, label directions) are also present.
    Returns True if safe (either no chemicals mentioned, or cautions are present).
    Returns False if chemicals are mentioned without safety cautions.
    """
    if not answer or not answer.strip():
        return True

    has_chemicals = bool(_CHEMICAL_INGREDIENT_PATTERN.search(answer))
    if not has_chemicals:
        return True

    return bool(_SAFETY_CAUTION_PATTERN.search(answer))


def contextualize_query(
    llm_client: LLMClient, query: str, history: list[dict[str, str]] | None
) -> str:
    """Rewrite a follow-up question into a standalone one."""
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
        rewritten = llm_client.generate(prompt).strip()
        return rewritten if rewritten else query
    except Exception:
        return query


def verify_citations(llm_client: LLMClient, answer: str, chunks: list[RetrievedChunk]) -> bool:
    """True if every [N] citation in answer is supported by chunk text."""
    citation_numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    if not citation_numbers:
        return True
    chunk_by_number = {i + 1: chunk for i, chunk in enumerate(chunks)}
    cited_pairs = [(n, chunk_by_number[n].text) for n in citation_numbers if n in chunk_by_number]
    if not cited_pairs:
        return True
    prompt = (
        "Answer:\n"
        + answer
        + "\n\n"
        + "\n\n".join(f"Excerpt [{n}]:\n{text}" for n, text in cited_pairs)
        + "\n\nFor each excerpt number above, does the answer's claim "
        "attributed to it actually match what that excerpt says? "
        'Respond with ONLY a JSON object like {"1": true, "2": false}, '
        "one entry per excerpt number shown."
    )
    try:
        raw = llm_client.generate(prompt).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        return all(result.get(str(n), True) for n, _ in cited_pairs)
    except Exception:
        return True


def suggest_follow_ups(llm_client: LLMClient, query: str, answer: str) -> list[str]:
    """Suggest up to 3 short follow-up questions."""
    prompt = (
        f"Question: {query}\nAnswer: {answer}\n\n"
        "Suggest up to 3 short, natural follow-up questions the user "
        "might ask next. Return ONLY a JSON array of strings, e.g. "
        '["question one?", "question two?"]. Return an empty array [] '
        "if you can't think of good ones."
    )
    try:
        raw = llm_client.generate(prompt).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        return [str(q) for q in result][:3] if isinstance(result, list) else []
    except Exception:
        return []


def search_web_fallback(
    query: str,
    confirm_web_search: bool = False,
    search_fn: Callable[[str], list[WebSearchResult]] | None = None,
) -> list[WebSearchResult]:
    """Best-effort web search execution with human approval gating."""
    if settings.web_search_requires_approval and not confirm_web_search:
        logger.info(
            "web_search_skipped_pending_approval",
            extra={"extra_fields": {"query_length": len(query)}},
        )
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
        return []
    try:
        fn = search_fn if search_fn is not None else default_search_web
        results: list[WebSearchResult] = fn(query)
        if results:
            get_metrics().record_web_search_fallback(stage="retrieval")
        return results
    except WebSearchError as exc:
        logger.warning("web_search_failed", extra={"extra_fields": {"error": str(exc)}})
        return []


def generate_answer(
    llm_client: LLMClient,
    query: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None,
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
    capture_prompt(prompt, variant="reflection" if extra_instruction else "standard")
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
    return strip_sources_section(llm_client.generate(prompt))


def generate_answer_streamed(
    llm_client: LLMClient,
    query: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None,
    extra_instruction: str | None = None,
    web_results: list[WebSearchResult] | None = None,
    persona: str | None = None,
) -> Iterator[tuple[bool, str]]:
    prompt = build_prompt(
        query,
        chunks,
        history=history,
        extra_instruction=extra_instruction,
        web_results=web_results,
        persona=persona,
    )
    capture_prompt(prompt, variant="streamed")
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
        for piece in llm_client.generate_stream(prompt):
            raw_parts.append(piece)
            yield piece

    for filtered_piece in stream_filtering_sources(_raw_stream()):
        yield (False, filtered_piece)

    yield (True, strip_sources_section("".join(raw_parts)))


def generate_answer_structured(
    llm_client: LLMClient,
    query: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None,
    web_results: list[WebSearchResult] | None = None,
    persona: str | None = None,
) -> str:
    prompt = build_structured_prompt(
        query, chunks, history=history, web_results=web_results, persona=persona
    )
    capture_prompt(prompt, variant="structured")
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
    raw = llm_client.generate_structured(prompt)
    structured = parse_structured_answer(raw)
    if structured is None:
        logger.info(
            "structured_output_fallback",
            extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
        )
        return generate_answer(
            llm_client, query, chunks, history, web_results=web_results, persona=persona
        )
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


def correct_answer(
    llm_client: LLMClient,
    query: str,
    chunks: list[RetrievedChunk],
    answer: str,
    history: list[dict[str, str]] | None,
    web_results: list[WebSearchResult],
    web_search_attempted: bool,
    llm_calls: int,
    steps_taken: int,
    confirm_web_search: bool = False,
    persona: str | None = None,
    max_llm_calls: int = _MAX_LLM_CALLS,
    search_fn: Callable[[str, bool], list[WebSearchResult]] | None = None,
    generate_fn: Callable[..., str] | None = None,
) -> tuple[str, int, int, list[WebSearchResult], bool]:
    """Corrective RAG loop regeneration stage (blocking)."""
    chemical_safe = not getattr(
        settings, "chemical_safety_verification_enabled", True
    ) or verify_chemical_safety(answer)
    citation_safe = not settings.citation_verification_enabled or verify_citations(
        llm_client, answer, chunks
    )
    ungrounded = (
        is_ungrounded(answer, chunks, web_results) or not citation_safe or not chemical_safe
    )
    if not ungrounded:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if llm_calls >= max_llm_calls:
        get_metrics().inc_counter("loop_capped_total", {"stage": "reflection"})
        logger.warning(
            "loop_capped",
            extra={"extra_fields": {"llm_calls": llm_calls, "stage": "reflection"}},
        )
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    extra_instruction = CHEMICAL_SAFETY_INSTRUCTION if not chemical_safe else REFLECTION_INSTRUCTION
    logger.info(
        "reflection_triggered",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "chunk_count": len(chunks),
                "reason": "chemical_safety" if not chemical_safe else "ungrounded",
            }
        },
    )
    gen = generate_fn or (lambda q, c, h, **kw: generate_answer(llm_client, q, c, h, **kw))
    answer = gen(
        query,
        chunks,
        history,
        extra_instruction=extra_instruction,
        web_results=web_results,
        persona=persona,
    )
    llm_calls += 1
    steps_taken += 1  # regeneration

    chemical_safe_after = not getattr(
        settings, "chemical_safety_verification_enabled", True
    ) or verify_chemical_safety(answer)
    if not is_ungrounded(answer, chunks, web_results) and chemical_safe_after:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if web_search_attempted or not settings.web_search_enabled:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if llm_calls >= max_llm_calls:
        get_metrics().inc_counter("loop_capped_total", {"stage": "web_fallback"})
        logger.warning(
            "loop_capped",
            extra={"extra_fields": {"llm_calls": llm_calls, "stage": "web_fallback"}},
        )
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    search = search_fn or (lambda q, conf: search_web_fallback(q, confirm_web_search=conf))
    web_results = search(query, confirm_web_search)
    web_search_attempted = True
    steps_taken += 1  # web search

    if not web_results:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    logger.info("web_fallback_triggered", extra={"extra_fields": {"query_length": len(query)}})
    answer = gen(
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


def correct_answer_streamed(
    llm_client: LLMClient,
    query: str,
    chunks: list[RetrievedChunk],
    answer: str,
    history: list[dict[str, str]] | None,
    web_results: list[WebSearchResult],
    web_search_attempted: bool,
    llm_calls: int,
    steps_taken: int,
    confirm_web_search: bool = False,
    persona: str | None = None,
    max_llm_calls: int = _MAX_LLM_CALLS,
    search_fn: Callable[[str, bool], list[WebSearchResult]] | None = None,
    generate_streamed_fn: Callable[..., Iterator[tuple[bool, str]]] | None = None,
) -> Generator[dict[str, Any], None, tuple[str, int, int, list[WebSearchResult], bool]]:
    """Streamed counterpart to correct_answer."""
    chemical_safe = not getattr(
        settings, "chemical_safety_verification_enabled", True
    ) or verify_chemical_safety(answer)
    citation_safe = not settings.citation_verification_enabled or verify_citations(
        llm_client, answer, chunks
    )
    ungrounded = (
        is_ungrounded(answer, chunks, web_results) or not citation_safe or not chemical_safe
    )
    if not ungrounded:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if llm_calls >= max_llm_calls:
        get_metrics().inc_counter("loop_capped_total", {"stage": "reflection"})
        logger.warning(
            "loop_capped",
            extra={"extra_fields": {"llm_calls": llm_calls, "stage": "reflection"}},
        )
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    extra_instruction = CHEMICAL_SAFETY_INSTRUCTION if not chemical_safe else REFLECTION_INSTRUCTION
    logger.info(
        "reflection_triggered",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "chunk_count": len(chunks),
                "reason": "chemical_safety" if not chemical_safe else "ungrounded",
            }
        },
    )
    yield trace_event(
        "reflecting", {"reason": "chemical_safety" if not chemical_safe else "ungrounded_answer"}
    )
    gen_stream = generate_streamed_fn or (
        lambda q, c, h, **kw: generate_answer_streamed(llm_client, q, c, h, **kw)
    )
    answer = ""
    for is_final, value in gen_stream(
        query,
        chunks,
        history,
        extra_instruction=extra_instruction,
        web_results=web_results,
        persona=persona,
    ):
        if is_final:
            answer = value
        else:
            yield {"type": "answer_chunk", "text": value}
    llm_calls += 1
    steps_taken += 1  # regeneration

    chemical_safe_after = not getattr(
        settings, "chemical_safety_verification_enabled", True
    ) or verify_chemical_safety(answer)
    if not is_ungrounded(answer, chunks, web_results) and chemical_safe_after:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if web_search_attempted or not settings.web_search_enabled:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    if llm_calls >= max_llm_calls:
        get_metrics().inc_counter("loop_capped_total", {"stage": "web_fallback"})
        logger.warning(
            "loop_capped",
            extra={"extra_fields": {"llm_calls": llm_calls, "stage": "web_fallback"}},
        )
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    search = search_fn or (lambda q, conf: search_web_fallback(q, confirm_web_search=conf))
    web_results = search(query, confirm_web_search)
    web_search_attempted = True
    steps_taken += 1  # web search
    yield trace_event("web_search", {"result_count": len(web_results)})

    if not web_results:
        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    logger.info("web_fallback_triggered", extra={"extra_fields": {"query_length": len(query)}})
    yield trace_event("reflecting", {"reason": "web_fallback"})
    answer = ""
    for is_final, value in gen_stream(
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


class ReflectionEngine:
    """Orchestrates RAG generation, reflection, and corrective self-RAG."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict[str, str]] | None,
        extra_instruction: str | None = None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> str:
        return generate_answer(
            self._llm_client,
            query,
            chunks,
            history,
            extra_instruction=extra_instruction,
            web_results=web_results,
            persona=persona,
        )

    def generate_streamed(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict[str, str]] | None,
        extra_instruction: str | None = None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> Iterator[tuple[bool, str]]:
        return generate_answer_streamed(
            self._llm_client,
            query,
            chunks,
            history,
            extra_instruction=extra_instruction,
            web_results=web_results,
            persona=persona,
        )

    def generate_structured(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict[str, str]] | None,
        web_results: list[WebSearchResult] | None = None,
        persona: str | None = None,
    ) -> str:
        return generate_answer_structured(
            self._llm_client, query, chunks, history, web_results=web_results, persona=persona
        )

    def correct(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        answer: str,
        history: list[dict[str, str]] | None,
        web_results: list[WebSearchResult],
        web_search_attempted: bool,
        llm_calls: int,
        steps_taken: int,
        confirm_web_search: bool = False,
        persona: str | None = None,
        max_llm_calls: int = _MAX_LLM_CALLS,
        search_fn: Callable[[str, bool], list[WebSearchResult]] | None = None,
        generate_fn: Callable[..., str] | None = None,
    ) -> tuple[str, int, int, list[WebSearchResult], bool]:
        return correct_answer(
            self._llm_client,
            query,
            chunks,
            answer,
            history,
            web_results,
            web_search_attempted,
            llm_calls,
            steps_taken,
            confirm_web_search=confirm_web_search,
            persona=persona,
            max_llm_calls=max_llm_calls,
            search_fn=search_fn,
            generate_fn=generate_fn,
        )

    def correct_streamed(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        answer: str,
        history: list[dict[str, str]] | None,
        web_results: list[WebSearchResult],
        web_search_attempted: bool,
        llm_calls: int,
        steps_taken: int,
        confirm_web_search: bool = False,
        persona: str | None = None,
        max_llm_calls: int = _MAX_LLM_CALLS,
        search_fn: Callable[[str, bool], list[WebSearchResult]] | None = None,
        generate_streamed_fn: Callable[..., Iterator[tuple[bool, str]]] | None = None,
    ) -> Generator[dict[str, Any], None, tuple[str, int, int, list[WebSearchResult], bool]]:
        return (
            yield from correct_answer_streamed(
                self._llm_client,
                query,
                chunks,
                answer,
                history,
                web_results,
                web_search_attempted,
                llm_calls,
                steps_taken,
                confirm_web_search=confirm_web_search,
                persona=persona,
                max_llm_calls=max_llm_calls,
                search_fn=search_fn,
                generate_streamed_fn=generate_streamed_fn,
            )
        )

    def contextualize(self, query: str, history: list[dict[str, str]] | None) -> str:
        return contextualize_query(self._llm_client, query, history)

    def verify_citations(self, answer: str, chunks: list[RetrievedChunk]) -> bool:
        return verify_citations(self._llm_client, answer, chunks)

    def verify_chemical_safety(self, answer: str) -> bool:
        return verify_chemical_safety(answer)

    def suggest_follow_ups(self, query: str, answer: str) -> list[str]:
        return suggest_follow_ups(self._llm_client, query, answer)
