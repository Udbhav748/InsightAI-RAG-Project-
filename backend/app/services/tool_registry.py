"""Formal tool I/O schemas and a tool-invocation tracking decorator.

The agent's tools (retrieval, summarization, web search, diagnose) each get
a declared Pydantic input and output schema here, so tool arguments are
validated at the boundary instead of being untyped function parameters, and
so the tool registry is the single source of truth for what each tool takes
and returns (used by the agent spec in prompt_builder.py and the eval
harness).

@track_tool wraps a tool function and emits a structured "tool_invocation"
log event on every call — name, input summary, success/failure flag, error
type, and latency — which is what Tool Success Rate is computed from at
runtime (see eval/ and monitoring/).

Inputs are validated against the schema *before* the wrapped call runs; a
validation failure raises ToolInputError (an AppError, 422) rather than
proceeding, so a malformed tool call surfaces loudly instead of failing
halfway through the pipeline.
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import AppError, ChatServiceError

logger = logging.getLogger(__name__)


class ToolInputError(ChatServiceError):
    """Raised when a tool is invoked with arguments that fail its schema."""

    status_code = 422
    error_code = "TOOL_INPUT_ERROR"

    def __init__(self, tool: str, detail: str):
        super().__init__(f"Invalid arguments for tool '{tool}': {detail}")


# --- Per-tool input schemas -------------------------------------------------

class RetrievalInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, gt=0)
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class SummarizationInput(BaseModel):
    document_id: str = Field(min_length=1)


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1)
    max_results: int | None = Field(default=None, gt=0)


class DiagnoseInput(BaseModel):
    contents: bytes
    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    query: str | None = None


# --- Per-tool output schemas -------------------------------------------------

class RetrievalOutput(BaseModel):
    chunks: list[Any]


class SummarizationOutput(BaseModel):
    summary: str
    chunks: list[Any]


class WebSearchOutput(BaseModel):
    results: list[Any]


class DiagnoseOutput(BaseModel):
    raw_class: str
    crop: str
    disease: str
    confidence: float
    low_confidence: bool


# --- Registry ----------------------------------------------------------------

TOOL_SCHEMAS: dict[str, dict[str, type[BaseModel]]] = {
    "retrieval": {"input": RetrievalInput, "output": RetrievalOutput},
    "summarization": {"input": SummarizationInput, "output": SummarizationOutput},
    "web_search": {"input": WebSearchInput, "output": WebSearchOutput},
    "diagnose": {"input": DiagnoseInput, "output": DiagnoseOutput},
}


def track_tool(name: str):
    """Decorator: validates args against the tool's input schema, runs the
    wrapped function, and logs one structured tool_invocation event.

    Success, failure, error type, and latency are all captured so runtime
    Tool Success Rate is computable from the log (each event is one
    attempt, exactly, on success or failure).
    """

    def decorator(func):
        # Bind call-site args to parameter names so schemas can be applied
        # regardless of whether callers pass args positionally or by keyword.
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            input_schema = TOOL_SCHEMAS[name]["input"]
            # Only schema-declared fields are validated — tool functions take
            # injected collaborators (vector_store, llm_client) that aren't
            # part of the tool's user-facing I/O contract.
            schema_fields = {
                k: v for k, v in bound.arguments.items() if k in input_schema.model_fields
            }
            try:
                validated = input_schema.model_validate(schema_fields)
            except ValidationError as exc:
                raise ToolInputError(name, str(exc)) from exc

            input_summary = _summarize_input(validated.model_dump())
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except AppError as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.warning(
                    "tool_invocation",
                    extra={
                        "extra_fields": {
                            "tool": name,
                            "success": False,
                            "error_type": type(exc).__name__,
                            "input": input_summary,
                            "latency_ms": round(latency_ms, 2),
                        }
                    },
                )
                raise
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.warning(
                    "tool_invocation",
                    extra={
                        "extra_fields": {
                            "tool": name,
                            "success": False,
                            "error_type": type(exc).__name__,
                            "input": input_summary,
                            "latency_ms": round(latency_ms, 2),
                        }
                    },
                )
                raise
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "tool_invocation",
                extra={
                    "extra_fields": {
                        "tool": name,
                        "success": True,
                        "input": input_summary,
                        "latency_ms": round(latency_ms, 2),
                    }
                },
            )
            return result

        return wrapper

    return decorator


def _summarize_input(data: dict) -> dict:
    """Trim values that would bloat the log (long query strings, image
    bytes) to a short length — the event records shape, not content."""
    summary = {}
    for key, value in data.items():
        if isinstance(value, bytes):
            summary[key] = f"<{len(value)} bytes>"
        elif isinstance(value, str) and len(value) > 120:
            summary[key] = value[:120] + "..."
        else:
            summary[key] = value
    return summary
