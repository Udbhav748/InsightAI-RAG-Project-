"""Orchestrates the RAG pipeline: retrieves relevant chunks and calls the
configured LLM for answers.

ChatService contains no AI, retrieval, or prompt logic itself — it only
coordinates RetrievalService, PromptBuilder, and LLMClient. It depends on
the VectorStore and LLMClient interfaces, never on a concrete
implementation (FAISSVectorStore, GeminiClient); those are constructed
elsewhere and handed in.
"""

import logging
import time

from app.core.exceptions import AppError, ChatServiceError
from app.models.schemas import ChatResponse
from app.services.llm_client import LLMClient
from app.services.prompt_builder import build_prompt, strip_sources_section
from app.services.retrieval_service import retrieve
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


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
        """Retrieve relevant chunks, build a prompt, and generate an answer."""
        start = time.perf_counter()

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

        processing_duration = time.perf_counter() - start
        sources = sorted({chunk.document_id for chunk in retrieved_chunks})

        logger.info(
            "chat_query_handled",
            extra={
                "extra_fields": {
                    "query_length": len(query),
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
