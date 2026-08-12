"""Routes for natural language question-answering against uploaded documents."""

import json
import logging
from collections.abc import Iterator
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.core.auth import require_auth
from app.core.exceptions import SessionNotFoundError, VectorStoreNotFoundError
from app.models.schemas import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.feedback_service import record_feedback
from app.services.llm_client import LLMClient
from app.services.llm_provider import build_llm_client
from app.services.rag_service import ChatService
from app.services.session_repository import get_session_owner, list_sessions, set_session_title_if_unset
from app.services.session_store import get_session_store
from app.services.validation_service import validate_image_upload
from app.services.vector_store import VectorStore

router = APIRouter(tags=["Chat"], dependencies=[Depends(require_auth)])
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
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    # Constructed here rather than via Depends(): a Depends() dependency
    # runs before FastAPI validates the request body, so a missing vector
    # store would raise (404) before an invalid body could return its 422.
    # Calling it here, after `payload` is already validated, preserves 422s.
    chat_service = get_chat_service()
    session_store = get_session_store()
    tenant_id = getattr(request.state, "tenant_id", None)

    # Resolve session_id: use provided, or create new if none/not found
    session_id = session_store.get_or_create_session(payload.session_id, tenant_id=tenant_id)
    # Best-effort, no-op after the first call for a given session — see
    # session_repository.py. Gives the history-list UI (GET
    # /chat/sessions) something to show besides a raw UUID.
    set_session_title_if_unset(session_id, payload.query)

    # Get server-side history (takes precedence over client-sent history)
    history = session_store.get_history(session_id)
    if history is None:
        # Fallback to client-provided history if session not found
        history = payload.history

    logger.info(
        "chat_request_received",
        extra={
            "extra_fields": {
                "query_length": len(payload.query),
                "top_k": payload.top_k,
                "min_score": payload.min_score,
                "client": getattr(request.state, "client_name", "unknown"),
                "session_id": session_id,
                "history_turns": len(history) if history else 0,
            }
        },
    )

    response = chat_service.handle_query(
        payload.query,
        top_k=payload.top_k,
        min_score=payload.min_score,
        history=history,
        session_id=session_id,
        confirm_web_search=payload.confirm_web_search,
        structured_response=payload.structured_response,
        tenant_id=tenant_id,
        persona=payload.persona,
        document_ids=payload.document_ids,
    )

    # Append this turn to server-side history
    session_store.append_turn(session_id, "user", payload.query)
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
    the identical shape either endpoint would give it. If the caller has
    already converted it to a dict (chat_stream injects session_id into the
    done payload before this is called), leave it as-is.
    """
    if event.get("type") == "done":
        payload = event["payload"]
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        event = {**event, "payload": payload}
    return f"data: {json.dumps(event)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    # Same auth (router-level Depends(require_auth)) and request body
    # as POST /chat — this is the same pipeline, just fanning out its
    # progress as Server-Sent Events instead of returning one response at
    # the end. POST /chat itself is untouched; this is an additive route.
    chat_service = get_chat_service()
    session_store = get_session_store()
    tenant_id = getattr(request.state, "tenant_id", None)

    # Resolve session_id: use provided, or create new if none/not found
    session_id = session_store.get_or_create_session(payload.session_id, tenant_id=tenant_id)
    set_session_title_if_unset(session_id, payload.query)

    # Get server-side history (takes precedence over client-sent history)
    history = session_store.get_history(session_id)
    if history is None:
        history = payload.history

    logger.info(
        "chat_stream_request_received",
        extra={
            "extra_fields": {
                "query_length": len(payload.query),
                "top_k": payload.top_k,
                "min_score": payload.min_score,
                "client": getattr(request.state, "client_name", "unknown"),
                "session_id": session_id,
                "history_turns": len(history) if history else 0,
            }
        },
    )

    def event_source() -> Iterator[str]:
        full_answer_parts: list[str] = []

        for event in chat_service.stream_query(
            payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            history=history,
            session_id=session_id,
            confirm_web_search=payload.confirm_web_search,
            tenant_id=tenant_id,
            persona=payload.persona,
            document_ids=payload.document_ids,
        ):
            # Capture answer chunks to append to history after stream completes
            if event.get("type") == "answer_chunk":
                full_answer_parts.append(event["text"])
            elif event.get("type") == "done":
                # Stream completed — append this turn to server-side history
                full_answer = "".join(full_answer_parts)
                session_store.append_turn(session_id, "user", payload.query)
                session_store.append_turn(session_id, "assistant", full_answer)

                # Inject session_id into the done payload
                done_payload = event["payload"]
                if hasattr(done_payload, "model_dump"):
                    payload_data = done_payload.model_dump(mode="json")
                else:
                    payload_data = done_payload
                payload_data["session_id"] = session_id
                event = {**event, "payload": payload_data}

            yield _sse_line(event)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/chat/diagnose", response_model=ChatResponse)
async def diagnose(
    request: Request,
    image: UploadFile = File(...),
    query: str | None = Form(None),
    session_id: str | None = Form(None),
    confirm_web_search: bool = Form(False),
) -> ChatResponse:
    # A separate multipart endpoint rather than an optional file param on
    # /chat: FastAPI resolves a whole request as either a JSON body or
    # multipart/form-data per the endpoint's declared parameters, not per
    # request, so /chat's existing ChatRequest JSON body and a File() param
    # can't coexist on one route without breaking every current JSON caller.
    chat_service = get_chat_service()
    session_store = get_session_store()
    tenant_id = getattr(request.state, "tenant_id", None)

    contents = await image.read()
    await image.seek(0)
    validate_image_upload(image, contents)

    # Same session_store dance /chat and /chat/stream already do (see
    # `chat()` above) — previously missing here entirely, so a diagnosis
    # was never actually written to session history: the session_id in the
    # response was just echoed back from whatever the client sent (or "" if
    # nothing was sent), never created, read, or appended to. That meant a
    # frontend "continue chatting in this session" flow would resume into
    # an empty conversation with no memory of the diagnosis at all.
    session_id = session_store.get_or_create_session(session_id, tenant_id=tenant_id)
    set_session_title_if_unset(session_id, query or "Leaf diagnosis")
    history = session_store.get_history(session_id)

    logger.info(
        "diagnose_request_received",
        extra={
            "extra_fields": {
                "filename": image.filename,
                "content_type": image.content_type,
                "has_accompanying_query": query is not None,
                "session_id": session_id,
                "history_turns": len(history) if history else 0,
            }
        },
    )

    # handle_diagnose is fully synchronous (vision inference, retrieval,
    # LLM generation, and — with the research agent enabled — blocking
    # HTTP page fetches). Unlike /chat and /chat/stream, this route is
    # `async def` (required for the multipart file read above), so without
    # run_in_threadpool that synchronous work would run directly on the
    # event loop and stall every other in-flight request for its duration.
    response = await run_in_threadpool(
        chat_service.handle_diagnose,
        contents,
        image.filename or "upload",
        image.content_type or "application/octet-stream",
        query=query,
        history=history,
        session_id=session_id,
        confirm_web_search=confirm_web_search,
        tenant_id=tenant_id,
    )

    # Append this turn to server-side history, same shape /chat uses. The
    # "user" turn has no raw text to store (the input was an image, not a
    # message) — reconstructed from the diagnosis result instead, so a
    # resumed conversation reads sensibly rather than showing a blank user
    # turn or just the assistant's answer with no visible question.
    if response.diagnosis is not None:
        diagnosis_label = (
            f"{response.diagnosis.disease} on {response.diagnosis.crop}"
            if response.diagnosis.disease != "healthy"
            else f"healthy {response.diagnosis.crop}"
        )
        user_turn = f"[Uploaded a leaf photo — diagnosed: {diagnosis_label}]"
        if query:
            user_turn += f" {query}"
    else:
        user_turn = query or "[Uploaded a leaf photo for diagnosis]"
    session_store.append_turn(session_id, "user", user_turn)
    session_store.append_turn(session_id, "assistant", response.answer)

    logger.info(
        "diagnose_response_sent",
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

    # Attach the resolved session_id, same defensive override /chat uses —
    # handle_diagnose already threads session_id through to _respond() on
    # every return path, so this is redundant today, but keeps the two
    # routes' guarantees identical rather than relying on that staying true.
    response_data = response.model_dump()
    response_data["session_id"] = session_id
    return ChatResponse(**response_data)


@router.post("/chat/feedback", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackRequest, request: Request) -> FeedbackResponse:
    # reviewer_id comes from the authenticated caller (require_auth,
    # the router-level dependency), never from the request body — a
    # client-supplied reviewer identity would let one API key pose as
    # multiple reviewers and fabricate Inter-Annotator Agreement.
    reviewer_id = getattr(request.state, "client_name", None)
    record_feedback(
        feedback.message_id,
        feedback.rating,
        feedback.comment,
        reviewer_id=reviewer_id,
        rubric=feedback.rubric.model_dump() if feedback.rubric else None,
    )

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "feedback_submitted",
                "path": request.url.path,
                "message_id": feedback.message_id,
                "rating": feedback.rating,
                "client": reviewer_id or "unknown",
                "has_rubric": feedback.rubric is not None,
            }
        },
    )

    return FeedbackResponse(status="recorded")


@router.get("/chat/sessions")
def list_chat_sessions(request: Request) -> dict:
    """List the caller's own past conversations (title, timestamps),
    newest-accessed first — the history sidebar's data source. []
    when the DB is disabled: session listing needs durable storage that
    the in-memory store, tied to one process, can't provide anyway."""
    tenant_id = getattr(request.state, "tenant_id", None)
    sessions = list_sessions(tenant_id)

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "sessions_listed",
                "path": request.url.path,
                "count": len(sessions),
                "client": getattr(request.state, "client_name", "unknown"),
            }
        },
    )
    return {"sessions": sessions, "total": len(sessions)}


def _check_session_ownership(request: Request, session_id: str) -> None:
    """Same "unknown isn't a mismatch, but a known mismatch is a 404"
    pattern documents.py's delete route already uses for
    get_document_owner — a non-owner sees the same response a
    genuinely missing session_id would give, never a 403 that would
    confirm the session exists."""
    requester_tenant_id = getattr(request.state, "tenant_id", None)
    if requester_tenant_id is None:
        return
    owner_tenant_id = get_session_owner(session_id)
    if owner_tenant_id is not None and owner_tenant_id != requester_tenant_id:
        raise SessionNotFoundError(f"No session found with id {session_id}")


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str, request: Request) -> dict:
    """Full turn history for one session — what the frontend calls to
    resume a past conversation from the history list."""
    _check_session_ownership(request, session_id)

    session_store = get_session_store()
    history = session_store.get_history(session_id)
    if history is None:
        raise SessionNotFoundError(f"No session found with id {session_id}")

    return {"session_id": session_id, "turns": history}


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str, request: Request) -> dict:
    """Delete one session by id — replaces the old header-based
    DELETE /chat/session (which read X-Session-ID and had a dead-code
    path that tried, and failed, to also read a JSON body). A path
    param is the natural shape once a history list UI exists: each row
    has its own delete action."""
    _check_session_ownership(request, session_id)

    session_store = get_session_store()
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
