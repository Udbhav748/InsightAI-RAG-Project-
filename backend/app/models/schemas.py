"""Pydantic request/response schemas for API validation and serialization."""

from datetime import datetime

from pydantic import BaseModel

from app.models.document import RetrievedChunk


class DocumentUploadResponse(BaseModel):
    document_id: str
    original_filename: str
    stored_filename: str
    file_size: int
    upload_timestamp: datetime
    status: str


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    sources: list[str]
    processing_time: float
