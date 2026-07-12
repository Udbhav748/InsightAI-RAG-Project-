"""Orchestrates the RAG pipeline: retrieves relevant chunks and calls the
configured LLM for answers.

ChatService contains no AI, retrieval, or prompt logic itself — it only
coordinates RetrievalService, PromptBuilder, and LLMClient. It depends on
the VectorStore and LLMClient interfaces, never on a concrete
implementation (FAISSVectorStore, GeminiClient); those are constructed
elsewhere and handed in.

It also runs a lightweight conversational router before any of that: a
plain keyword/phrase match (no NLP library) that answers small talk
directly, so "hi" doesn't trigger embeddings, vector search, and a Gemini
call just to get told nothing relevant was found.
"""

import logging
import re
import time

from app.core.exceptions import AppError, ChatServiceError
from app.models.schemas import ChatResponse
from app.services.llm_client import LLMClient
from app.services.prompt_builder import build_prompt, strip_sources_section
from app.services.retrieval_service import retrieve
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


class ChatService:
    def __init__(self, vector_store: VectorStore, llm_client: LLMClient):
        self._vector_store = vector_store
        self._llm_client = llm_client

    def handle_query(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> ChatResponse:
        """Route small talk directly; otherwise retrieve, build a prompt, and generate an answer."""
        start = time.perf_counter()

        conversational_reply = _match_conversational_reply(query)

        if conversational_reply is not None:
            return self._respond(
                answer=conversational_reply,
                retrieved_chunks=[],
                query=query,
                query_type="conversational",
                start=start,
            )

        try:
            retrieved_chunks = retrieve(
                query, self._vector_store, top_k=top_k, min_score=min_score
            )
            prompt = build_prompt(query, retrieved_chunks)
            answer = strip_sources_section(self._llm_client.generate(prompt))
        except AppError:
            # Already a well-formed domain exception from retrieval, prompt
            # building, or the LLM client — propagate it unchanged.
            raise
        except Exception as exc:
            raise ChatServiceError(f"Unexpected error while handling chat query: {exc}") from exc

        return self._respond(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            query=query,
            query_type="document_query",
            start=start,
        )

    def _respond(self, *, answer, retrieved_chunks, query, query_type, start) -> ChatResponse:
        processing_duration = time.perf_counter() - start
        sources = sorted({chunk.document_id for chunk in retrieved_chunks})

        logger.info(
            "chat_query_handled",
            extra={
                "extra_fields": {
                    "query_length": len(query),
                    "query_type": query_type,
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
        )
