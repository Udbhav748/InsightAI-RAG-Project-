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
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import AppError, ChatServiceError, WebSearchError
from app.models.document import RetrievedChunk, WebSearchResult
from app.models.schemas import ChatResponse, SourceReference
from app.services.llm_client import LLMClient
from app.services.prompt_builder import (
    FALLBACK_REPLY,
    PROMPT_VERSION,
    REFLECTION_INSTRUCTION,
    build_prompt,
    strip_sources_section,
)
from app.services.retrieval_service import retrieve
from app.services.summarization_service import summarize_document
from app.services.vector_store import VectorStore
from app.services.web_search_service import search_web

logger = logging.getLogger(__name__)

# Hard ceiling on generate() calls per /chat request (the initial answer,
# plus the corrective loop's reflection and web-fallback regenerations) —
# the loop-prevention/Loop Rate control. The corrective loop as written
# never needs more than 3 (see _correct), so this is a defensive backstop
# against a future change to the loop rather than something normal traffic
# is expected to hit; hitting it logs "loop_capped".
_MAX_LLM_CALLS = 3

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


def _source_references(chunks: list[RetrievedChunk]) -> list[SourceReference]:
    """One SourceReference per retrieved chunk — chunk-level, not deduped
    by document, so a citation always points at the specific passage the
    answer actually drew from."""
    return [
        SourceReference(document_id=chunk.document_id, chunk_id=chunk.chunk_id, excerpt=_excerpt(chunk.text))
        for chunk in chunks
    ]


def _web_source_references(results: list[WebSearchResult]) -> list[SourceReference]:
    """One SourceReference per web result, using the same shape as document
    citations: document_id='web' marks it as non-document, chunk_id is the
    URL itself (a web result has no chunk id, but the URL is a stable,
    unique-enough identifier), and url carries the link for the frontend to
    render out."""
    return [
        SourceReference(document_id="web", chunk_id=result.url, excerpt=_excerpt(result.snippet), url=result.url)
        for result in results
    ]


def _answer_source(chunks: list[RetrievedChunk], web_results: list[WebSearchResult]) -> str:
    """"documents" | "web" | "mixed", based on which context actually made
    it into the final prompt — not on what was attempted. A web search that
    was tried but returned nothing doesn't count as "web"."""
    if not web_results:
        return "documents"
    return "web" if not chunks else "mixed"


def _match_conversational_reply(query: str) -> str | None:
    """Return a canned reply if query is small talk, else None."""
    normalized = _normalize(query)
    for phrases, response in _CONVERSATIONAL_INTENTS:
        if normalized in phrases:
            return response
    return None


@dataclass
class PlanDecision:
    action: str  # "conversational" | "retrieve" | "summarize"
    document_id: str | None = None


class ChatService:
    def __init__(self, vector_store: VectorStore, llm_client: LLMClient):
        self._vector_store = vector_store
        self._llm_client = llm_client

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

    def _generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list[dict] | None,
        extra_instruction: str | None = None,
        web_results: list[WebSearchResult] | None = None,
    ) -> str:
        prompt = build_prompt(
            query, chunks, history=history, extra_instruction=extra_instruction, web_results=web_results
        )
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
        return grade

    def _search_web(self, query: str) -> list[WebSearchResult]:
        """Best-effort web search. A failure here degrades to an empty
        result list rather than failing the whole chat request — web
        search is an enhancement to the corrective loop, not a dependency
        the request can't survive without."""
        try:
            return search_web(query)
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
        if not self._is_ungrounded(answer, chunks, web_results):
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        if llm_calls >= _MAX_LLM_CALLS:
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "reflection"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info(
            "reflection_triggered",
            extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
        )
        answer = self._generate(
            query, chunks, history, extra_instruction=REFLECTION_INSTRUCTION, web_results=web_results
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
            logger.warning(
                "loop_capped", extra={"extra_fields": {"llm_calls": llm_calls, "stage": "web_fallback"}}
            )
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        web_results = self._search_web(query)
        web_search_attempted = True
        steps_taken += 1  # web search

        if not web_results:
            return answer, llm_calls, steps_taken, web_results, web_search_attempted

        logger.info("web_fallback_triggered", extra={"extra_fields": {"query_length": len(query)}})
        answer = self._generate(
            query, chunks, history, extra_instruction=REFLECTION_INSTRUCTION, web_results=web_results
        )
        llm_calls += 1
        steps_taken += 1  # regeneration with web context

        return answer, llm_calls, steps_taken, web_results, web_search_attempted

    def handle_query(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        history: list[dict] | None = None,
    ) -> ChatResponse:
        start = time.perf_counter()
        steps_taken = 1  # planning

        plan = self._plan(query, history)
        logger.info(
            "plan_decided",
            extra={"extra_fields": {"action": plan.action, "query_length": len(query)}},
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
            )

        recent_history = history[-_MAX_HISTORY_TURNS:] if history else None

        try:
            if plan.action == "summarize":
                steps_taken += 1  # fetch document chunks
                summary, chunks = summarize_document(
                    plan.document_id, self._vector_store, self._llm_client
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
                )

            # plan.action == "retrieve" — the corrective RAG loop.
            steps_taken += 1  # retrieval
            chunks = retrieve(query, self._vector_store, top_k=top_k, min_score=min_score)

            steps_taken += 1  # grading
            grade = self._grade_retrieval(query, chunks)

            # A weak/insufficient grade pulls in web results *before* the
            # first generation attempt, so the model has them alongside
            # whatever chunks did come back (this is the "corrective" part
            # of corrective RAG — augment instead of just hoping reflection
            # fixes it later).
            web_results: list[WebSearchResult] = []
            web_search_attempted = False
            if grade != "good" and settings.web_search_enabled:
                web_results = self._search_web(query)
                web_search_attempted = True
                steps_taken += 1  # web search

            answer = self._generate(query, chunks, recent_history, web_results=web_results)
            llm_calls = 1
            steps_taken += 1  # generation

            answer, llm_calls, steps_taken, web_results, web_search_attempted = self._correct(
                query, chunks, answer, recent_history, web_results, web_search_attempted, llm_calls, steps_taken
            )
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
        return self._respond(
            answer=answer,
            retrieved_chunks=chunks,
            query=query,
            query_type="document_query",
            tool_used=tool_used,
            steps_taken=steps_taken,
            start=start,
            web_results=web_results,
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
    ) -> ChatResponse:
        processing_duration = time.perf_counter() - start
        web_results = web_results or []
        sources = _source_references(retrieved_chunks) + _web_source_references(web_results)
        answer_source = _answer_source(retrieved_chunks, web_results)

        logger.info(
            "chat_query_handled",
            extra={
                "extra_fields": {
                    "query_length": len(query),
                    "query_type": query_type,
                    "tool_used": tool_used,
                    "steps_taken": steps_taken,
                    "retrieved_chunk_count": len(retrieved_chunks),
                    "web_result_count": len(web_results),
                    "answer_source": answer_source,
                    "processing_duration": round(processing_duration, 4),
                }
            },
        )

        return ChatResponse(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            sources=sources,
            processing_time=round(processing_duration, 4),
            tool_used=tool_used,
            steps_taken=steps_taken,
            answer_source=answer_source,
        )
