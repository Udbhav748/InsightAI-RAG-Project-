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
from app.services.session_store import get_session_store
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
    session_store = get_session_store()

    # Resolve session_id: use provided, or create new if none/not found
    session_id = session_store.get_or_create_session(request.session_id)

    # Get server-side history (takes precedence over client-sent history)
    history = session_store.get_history(session_id)
    if history is None:
        # Fallback to client-provided history if session not found
        history = request.history

    logger.info(
        "chat_request_received",
        extra={
            "extra_fields": {
                "query_length": len(request.query),
                "top_k": request.top_k,
                "min_score": request.min_score,
                "client": getattr(request.state, "client_name", "unknown"),
                "session_id": session_id,
                "history_turns": len(history) if history else 0,
            }
        },
    )

    response = chat_service.handle_query(
        request.query,
        top_k=request.top_k,
        min_score=request.min_score,
        history=history,
        session_id=session_id,
    )

    # Append this turn to server-side history
    session_store.append_turn(session_id, "user", request.query)
    session_store.append_turn(session_id, "assistant", response.answer)

    logger.info(
        "chat_response_sent",
        extra={
            "extra_fields": {
                "answer_length": len(response.answer),
                "retrieved_chunk_count": len(response.retrieved_chunks),
                "processing_time": response.processing_time,
                "client": getattr(request.state, "client_name", "unknown"),
                "session_id": session_id,
            }
        },
    )

    # Attach session_id to response (Pydantic model allows extra fields via model_dump)
    response_data = response.model_dump()
    response_data["session_id"] = session_id
    return ChatResponse(**response_data)


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
    session_store = get_session_store()

    # Resolve session_id: use provided, or create new if none/not found
    session_id = session_store.get_or_create_session(request.session_id)

    # Get server-side history (takes precedence over client-sent history)
    history = session_store.get_history(session_id)
    if history is None:
        history = request.history

    logger.info(
        "chat_stream_request_received",
        extra={
            "extra_fields": {
                "query_length": len(request.query),
                "top_k": request.top_k,
                "min_score": request.min_score,
                "client": getattr(request.state, "client_name", "unknown"),
                "session_id": session_id,
                "history_turns": len(history) if history else 0,
            }
        },
    )

    def event_source() -> Iterator[str]:
        full_answer_parts: list[str] = []

        for event in chat_service.stream_query(
            request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            history=history,
            session_id=session_id,
        ):
            # Capture answer chunks to append to history after stream completes
            if event.get("type") == "answer_chunk":
                full_answer_parts.append(event["text"])
            elif event.get("type") == "done":
                # Stream completed — append this turn to server-side history
                full_answer = "".join(full_answer_parts)
                session_store.append_turn(session_id, "user", request.query)
                session_store.append_turn(session_id, "assistant", full_answer)

                # Inject session_id into the done payload
                payload = event["payload"]
                if hasattr(payload, "model_dump"):
                    payload_data = payload.model_dump(mode="json")
                else:
                    payload_data = payload
                payload_data["session_id"] = session_id
                event = {**event, "payload": payload_data}

            yield _sse_line(event)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/chat/diagnose", response_model=ChatResponse)
async def diagnose(
    image: UploadFile = File(...),
    query: str | None = Form(None),
    session_id: str | None = Form(None),
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
        session_id=session_id,
    )

    logger.info(
        "diagnose_response_sent",
        extra={
            "extra_fields": {
                "answer_length": len(response.answer),
                "retrieved_chunk_count": len(response.retrieved_chunks),
                "processing_time": response.processing_time,
                "client": getattr(request.state, "client_name", "unknown"),
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
                "client": getattr(request.state, "client_name", "unknown"),
            }
        },
    )

    return FeedbackResponse(status="recorded")


@router.delete("/chat/session")
def delete_chat_session(request: Request) -> dict:
    """Delete the current chat session (server-side history).
    
    Called when user clicks "New chat" to clear server-side session.
    Session ID is read from request body (JSON) or header.
    """
    session_store = get_session_store()
    
    # Try to get session_id from request body (JSON) or header
    import json
    session_id = None
    try:
        body = request.headers.get("X-Session-ID")
        if body:
            session_id = body
    except Exception:
        pass
    
    if session_id:
        deleted = session_store.delete_session(session_id)
        if deleted:
            logger.info(
                "audit_event",
                extra={
                    "extra_fields": {
                        "event": "session_deleted",
                        "path": request.url.path,
                        "session_id": session_id,
                        "client": getattr(request.state, "client_name", "unknown"),
                    }
                },
            )
            return {"status": "deleted", "session_id": session_id}
    
    return {"status": "not_found", "session_id": session_id}
