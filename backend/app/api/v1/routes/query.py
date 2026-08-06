"""Routes for natural language question-answering against uploaded documents."""

import json
import logging
from collections.abc import Iterator
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.auth import require_api_key
from app.core.exceptions import VectorStoreNotFoundError
from app.models.schemas import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.feedback_service import record_feedback
from app.services.llm_client import LLMClient
from app.services.llm_provider import build_llm_client
from app.services.rag_service import ChatService
from app.services.validation_service import validate_image_upload
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


def _sse_line(event: dict) -> str:
    """Serialize one stream_query() event as an SSE `data:` line.

    The "done" event's payload is a ChatResponse (a Pydantic model, not
    plain JSON yet) — every other event type is already a plain dict.
    model_dump(mode="json") matches exactly what response_model=ChatResponse
    would have serialized on POST /chat, so a client parsing "done" gets
    the identical shape either endpoint would give it.
    """
    if event.get("type") == "done":
        event = {**event, "payload": event["payload"].model_dump(mode="json")}
    return f"data: {json.dumps(event)}\n\n"


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    # Same auth (router-level Depends(require_api_key)) and request body
    # as POST /chat — this is the same pipeline, just fanning out its
    # progress as Server-Sent Events instead of returning one response at
    # the end. POST /chat itself is untouched; this is an additive route.
    chat_service = get_chat_service()

    logger.info(
        "chat_stream_request_received",
        extra={
            "extra_fields": {
                "query_length": len(request.query),
                "top_k": request.top_k,
                "min_score": request.min_score,
            }
        },
    )

    def event_source() -> Iterator[str]:
        for event in chat_service.stream_query(
            request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            history=request.history,
        ):
            yield _sse_line(event)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/chat/diagnose", response_model=ChatResponse)
async def diagnose(
    image: UploadFile = File(...),
    query: str | None = Form(None),
) -> ChatResponse:
    # A separate multipart endpoint rather than an optional file param on
    # /chat: FastAPI resolves a whole request as either a JSON body or
    # multipart/form-data per the endpoint's declared parameters, not per
    # request, so /chat's existing ChatRequest JSON body and a File() param
    # can't coexist on one route without breaking every current JSON caller.
    chat_service = get_chat_service()

    contents = await image.read()
    await image.seek(0)
    validate_image_upload(image, contents)

    logger.info(
        "diagnose_request_received",
        extra={
            "extra_fields": {
                "filename": image.filename,
                "content_type": image.content_type,
                "has_accompanying_query": query is not None,
            }
        },
    )

    response = chat_service.handle_diagnose(
        contents,
        image.filename or "upload",
        image.content_type or "application/octet-stream",
        query=query,
    )

    logger.info(
        "diagnose_response_sent",
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
