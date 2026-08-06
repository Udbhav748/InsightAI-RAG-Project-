"""Routes for natural language question-answering against uploaded documents."""

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, Request

from app.core.auth import require_api_key
from app.core.exceptions import VectorStoreNotFoundError
from app.models.schemas import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.feedback_service import record_feedback
from app.services.llm_client import LLMClient
from app.services.llm_provider import build_llm_client
from app.services.rag_service import ChatService
from app.services.vector_store import VectorStore

router = APIRouter(tags=["Chat"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Load the persisted FAISS index once and reuse it on every request.

    Shared with the upload route (see documents.py) so both hit the same
    in-memory index — a document processed via /upload is immediately
    visible to /chat without a reload. If no index has been persisted yet,
    this returns an empty, uninitialized store rather than raising:
    DocumentProcessingService creates it on the first embedding batch, and
    VectorStore.search() already raises VectorStoreNotFoundError on an
    uninitialized store, so /chat still 404s correctly until then.
    """
    store = FAISSVectorStore()
    try:
        store.load()
    except VectorStoreNotFoundError:
        pass
    return store


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Build the configured LLM client (see Settings.llm_provider /
    fallback_llm_provider) once and reuse it on every request."""
    return build_llm_client()


def get_chat_service() -> ChatService:
    return ChatService(get_vector_store(), get_llm_client())


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # Constructed here rather than via Depends(): a Depends() dependency
    # runs before FastAPI validates the request body, so a missing vector
    # store would raise (404) before an invalid body could return its 422.
    # Calling it here, after `request` is already validated, preserves 422s.
    chat_service = get_chat_service()

    logger.info(
        "chat_request_received",
        extra={
            "extra_fields": {
                "query_length": len(request.query),
                "top_k": request.top_k,
                "min_score": request.min_score,
            }
        },
    )

    response = chat_service.handle_query(
        request.query,
        top_k=request.top_k,
        min_score=request.min_score,
        history=request.history,
    )

    logger.info(
        "chat_response_sent",
        extra={
            "extra_fields": {
                "answer_length": len(response.answer),
                "retrieved_chunk_count": len(response.retrieved_chunks),
                "processing_time": response.processing_time,
            }
        },
    )

    return response


@router.post("/chat/feedback", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackRequest, request: Request) -> FeedbackResponse:
    record_feedback(feedback.message_id, feedback.rating, feedback.comment)

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "feedback_submitted",
                "path": request.url.path,
                "message_id": feedback.message_id,
                "rating": feedback.rating,
            }
        },
    )

    return FeedbackResponse(status="recorded")
