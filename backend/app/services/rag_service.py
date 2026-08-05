"""Orchestrates a small hand-rolled agent: plans which tool a query needs,
executes it, and reflects on the result to catch ungrounded answers.

Deliberately plain Python — no LangChain/LangGraph agent runtime. A
planner (_plan) picks one of three actions from a query (and, for
"summarize", which document_id it names); a tool executes it
(conversational canned reply, retrieval + generation, or document
summarization); and a reflection step (_reflect) catches the specific
failure mode of "chunks were retrieved but the model ignored them" and
retries generation once with a stronger instruction.

ChatService still contains no retrieval, prompt, or LLM logic itself — it
coordinates RetrievalService, PromptBuilder, SummarizationService, and
LLMClient. It depends on the VectorStore and LLMClient interfaces, never
on a concrete implementation (FAISSVectorStore, GeminiClient); those are
constructed elsewhere and handed in.
"""

import logging
import re
import time
from dataclasses import dataclass

from app.core.exceptions import AppError, ChatServiceError
from app.models.document import RetrievedChunk
from app.models.schemas import ChatResponse
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

logger = logging.getLogger(__name__)

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


def _normalize(query: str) -> str:
    stripped = _PUNCTUATION_RE.sub("", query.lower())
    return _WHITESPACE_RE.sub(" ", stripped).strip()


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
    ) -> str:
        prompt = build_prompt(query, chunks, history=history, extra_instruction=extra_instruction)
        logger.info(
            "generation_requested",
            extra={
                "extra_fields": {
                    "prompt_version": PROMPT_VERSION,
                    "chunk_count": len(chunks),
                    "is_reflection": extra_instruction is not None,
                }
            },
        )
        return strip_sources_section(self._llm_client.generate(prompt))

    def _reflect(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        answer: str,
        history: list[dict] | None,
    ) -> tuple[str, bool]:
        """Catch "chunks were retrieved but the answer didn't use them".

        If chunks is empty, the fallback answer is expected and correct —
        nothing to reflect on. Otherwise, an empty or fallback-phrase
        answer despite having context is treated as a miss: regenerate
        once with an explicit instruction to ground the answer in the
        provided context. Returns (answer, reflection_triggered).
        """
        if not chunks:
            return answer, False
        if answer.strip() and answer.strip() != FALLBACK_REPLY:
            return answer, False

        logger.info(
            "reflection_triggered",
            extra={"extra_fields": {"query_length": len(query), "chunk_count": len(chunks)}},
        )

        regenerated = self._generate(query, chunks, history, extra_instruction=REFLECTION_INSTRUCTION)
        return regenerated, True

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

            # plan.action == "retrieve"
            steps_taken += 1  # retrieval
            chunks = retrieve(query, self._vector_store, top_k=top_k, min_score=min_score)

            answer = self._generate(query, chunks, recent_history)
            steps_taken += 1  # generation

            answer, reflected = self._reflect(query, chunks, answer, recent_history)
            if reflected:
                steps_taken += 1
        except AppError:
            # Already a well-formed domain exception from retrieval, prompt
            # building, summarization, or the LLM client — propagate it
            # unchanged.
            raise
        except Exception as exc:
            raise ChatServiceError(f"Unexpected error while handling chat query: {exc}") from exc

        return self._respond(
            answer=answer,
            retrieved_chunks=chunks,
            query=query,
            query_type="document_query",
            tool_used="retrieval",
            steps_taken=steps_taken,
            start=start,
        )

    def _respond(
        self, *, answer, retrieved_chunks, query, query_type, tool_used, steps_taken, start
    ) -> ChatResponse:
        processing_duration = time.perf_counter() - start
        sources = sorted({chunk.document_id for chunk in retrieved_chunks})

        logger.info(
            "chat_query_handled",
            extra={
                "extra_fields": {
                    "query_length": len(query),
                    "query_type": query_type,
                    "tool_used": tool_used,
                    "steps_taken": steps_taken,
                    "retrieved_chunk_count": len(retrieved_chunks),
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
        )
