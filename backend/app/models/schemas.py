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
        "6 are used.",
    )


class SourceReference(BaseModel):
    document_id: str
    chunk_id: str
    excerpt: str = Field(..., description="First ~200 characters of the cited chunk's text.")


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    sources: list[SourceReference]
    processing_time: float
    tool_used: str
    steps_taken: int


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    rating: Literal["up", "down"]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    status: str


class DocumentProcessingResponse(BaseModel):
    document_id: str
    original_filename: str
    total_pages: int
    total_chunks: int
    total_embeddings: int
    processing_time: float
    status: str


class DocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_removed: int
    status: str
