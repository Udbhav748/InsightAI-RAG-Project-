"""SSE streaming event adapter and token stream filtering for RAG responses.

Handles real-time token filtering (suppressing inline 'Sources:' sections),
formatting pipeline trace events, streaming answer chunks, error payloads,
and final ChatResponse done events.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.exceptions import AppError, ChatServiceError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.models.schemas import ChatResponse

logger = logging.getLogger(__name__)

# Matches prompt_builder._SOURCES_HEADING's own marker string (not the
# regex itself — this operates incrementally on a live token stream,
# where a full-string regex can't run until the heading has fully
# arrived). See stream_filtering_sources.
_SOURCES_MARKER = "sources:"
_SOURCES_HOLD_BACK = len(_SOURCES_MARKER) + 4  # margin for surrounding newlines


def stream_filtering_sources(chunks: Iterator[str]) -> Iterator[str]:
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


def trace_event(stage: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Build an SSE trace event dict and log it server-side in the same
    call — the same pipeline progress already logged via plan_decided/
    retrieval_completed/retrieval_graded/etc. elsewhere in this file, this
    just adds one more named line marking exactly what was fanned out to
    the client, for correlating client-observed timing against the
    existing structured logs."""
    logger.info("trace_event_emitted", extra={"extra_fields": {"stage": stage, **detail}})
    return {"type": "trace", "stage": stage, "detail": detail}


def format_answer_chunk(text: str) -> dict[str, Any]:
    """Format an incremental answer chunk event."""
    return {"type": "answer_chunk", "text": text}


def format_error_event(exc: Exception) -> dict[str, Any]:
    """Format an error event from an exception, preserving AppError taxonomy."""
    if isinstance(exc, AppError):
        logger.info(
            "chat_stream_error",
            extra={
                "extra_fields": {
                    "error_type": type(exc).__name__,
                    "status_code": exc.status_code,
                }
            },
        )
        return {
            "type": "error",
            "detail": {
                "error_type": type(exc).__name__,
                "message": exc.detail,
                "status_code": exc.status_code,
            },
        }
    chat_error = ChatServiceError(f"Unexpected error while handling chat query: {exc}")
    logger.info(
        "chat_stream_error",
        extra={
            "extra_fields": {
                "error_type": type(chat_error).__name__,
                "status_code": chat_error.status_code,
            }
        },
    )
    return {
        "type": "error",
        "detail": {
            "error_type": type(chat_error).__name__,
            "message": chat_error.detail,
            "status_code": chat_error.status_code,
        },
    }


def format_done_event(response: ChatResponse) -> dict[str, Any]:
    """Format the final done event payload."""
    return {"type": "done", "payload": response}


class StreamAdapter:
    """Adapts RAG generation events into SSE stream event dictionaries."""

    @staticmethod
    def trace(stage: str, detail: dict[str, Any]) -> dict[str, Any]:
        return trace_event(stage, detail)

    @staticmethod
    def chunk(text: str) -> dict[str, Any]:
        return format_answer_chunk(text)

    @staticmethod
    def error(exc: Exception) -> dict[str, Any]:
        return format_error_event(exc)

    @staticmethod
    def done(response: ChatResponse) -> dict[str, Any]:
        return format_done_event(response)

    @staticmethod
    def filter_sources(chunks: Iterator[str]) -> Iterator[str]:
        return stream_filtering_sources(chunks)
