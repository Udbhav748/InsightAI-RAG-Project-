"""Pydantic request/response schemas for API validation and serialization."""

from datetime import datetime

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


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    sources: list[str]
    processing_time: float
