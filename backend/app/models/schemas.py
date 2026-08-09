"""Pydantic request/response schemas for API validation and serialization."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.document import RetrievedChunk


class DocumentUploadResponse(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    file_size: int
    upload_timestamp: datetime
    status: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's natural-language question.")
    top_k: int | None = Field(
        None, gt=0, description="Number of chunks to retrieve. Defaults to Settings.retrieval_top_k."
    )
    min_score: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Minimum similarity score to keep a chunk. Defaults to Settings.retrieval_min_score.",
    )
    history: list[dict] | None = Field(
        None,
        description="Prior conversation turns, oldest first, each shaped like "
        "{'role': 'user'|'assistant', 'content': str}. Only the most recent "
        "6 are used. Ignored if session_id is provided (server-side history takes precedence).",
    )
    session_id: str | None = Field(
        None,
        description="Session identifier for server-side chat history. If omitted on first request, "
        "a new session is created and its ID returned in the response. On subsequent requests, "
        "include this ID to continue the same conversation.",
    )
    confirm_web_search: bool = Field(
        False,
        description="Human approval for the web-search tool. When Settings.web_search_requires_approval "
        "is enabled, web search is skipped unless this is true — an explicit human-in-the-loop "
        "gate on the agent's only outbound side-effect.",
    )
    structured_response: bool = Field(
        False,
        description="Request a JSON-mode structured answer. Only takes effect when "
        "Settings.structured_output_enabled is true; otherwise ignored.",
    )


class SourceReference(BaseModel):
    document_id: str
    chunk_id: str
    excerpt: str = Field(..., description="First ~200 characters of the cited chunk's text.")
    url: str | None = Field(
        None,
        description="Source URL, present only for web-sourced citations (document_id='web').",
    )


class DiagnosisInfo(BaseModel):
    raw_class: str = Field(..., description="Raw class label as returned by LeafSense.")
    crop: str = Field(..., description="Plain-language crop name, e.g. 'peach'.")
    disease: str = Field(..., description="Plain-language disease name, e.g. 'bacterial spot'.")
    confidence: float = Field(..., description="Model confidence for the predicted class, in [0, 1].")
    low_confidence: bool = Field(
        ..., description="True if confidence is below Settings.vision_confidence_threshold."
    )


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    sources: list[SourceReference]
    processing_time: float
    tool_used: str
    steps_taken: int
    answer_source: Literal["documents", "web", "mixed"] = Field(
        "documents",
        description="Whether the answer drew on retrieved document chunks, web search "
        "results, or both. Always 'documents' for non-retrieval actions.",
    )
    diagnosis: DiagnosisInfo | None = Field(
        None,
        description="Present only for image-diagnosis requests (POST /chat/diagnose) — "
        "the LeafSense prediction that produced this response's retrieval query.",
    )
    session_id: str = Field(
        ...,
        description="Session identifier for this conversation. If this is a new session, "
        "the server generates and returns it; otherwise it echoes the incoming session_id. "
        "Client should store this (e.g. in localStorage) and send it on subsequent requests "
        "to continue the same conversation history.",
    )


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    rating: Literal["up", "down"]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    status: str


class StructuredAnswer(BaseModel):
    """Schema the LLM's JSON-mode output is validated against.

    The prompt (see prompt_builder.build_structured_prompt) asks the model
    to emit exactly this shape; anything else is a parse failure and the
    caller falls back to the free-text path.
    """

    answer: str = Field(..., description="The final answer text.")
    sources: list[str] = Field(
        default_factory=list,
        description="Optional document ids the answer draws on, as given by the model.",
    )


class DocumentProcessingResponse(BaseModel):
    document_id: str
    original_filename: str
    total_pages: int
    total_chunks: int
    total_embeddings: int
    pages_ocred: int = Field(
        0, description="Number of pages that had no extractable text layer and were recovered via OCR."
    )
    processing_time: float
    status: str


class DocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_removed: int
    status: str


class DocumentListItem(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    file_size: int
    total_pages: int
    total_chunks: int
    total_embeddings: int
    pages_ocred: int
    upload_timestamp: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int
