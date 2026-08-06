"""Reusable domain models for the document processing pipeline.

These represent a document as it moves through upload, text extraction, and
chunking. They are consumed and produced by services (upload, extraction,
future chunking/embedding/retrieval) rather than being API wire formats
themselves.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UploadedDocument(BaseModel):
    document_id: str = Field(..., description="Unique identifier assigned to the uploaded document.")
    original_filename: str = Field(..., description="Filename as provided by the client at upload time.")
    stored_filename: str = Field(..., description="UUID-based filename the document is stored under on disk.")
    file_size: int = Field(..., description="Size of the uploaded file, in bytes.")
    upload_timestamp: datetime = Field(..., description="UTC timestamp of when the document was uploaded.")


class ExtractedDocument(BaseModel):
    document_id: str = Field(..., description="Identifier of the document this extraction was produced from.")
    extracted_text: str = Field(..., description="Full text extracted from the document, in page order.")
    total_pages: int = Field(..., description="Total number of pages in the source document.")
    extracted_characters: int = Field(..., description="Character count of extracted_text.")
    pages_ocred: int = Field(
        ..., description="Number of pages that had no extractable text layer and were recovered via OCR."
    )


class DocumentChunk(BaseModel):
    chunk_id: str = Field(..., description="Unique identifier for this chunk.")
    document_id: str = Field(..., description="Identifier of the document this chunk was derived from.")
    chunk_index: int = Field(..., description="Zero-based position of this chunk within the document.")
    text: str = Field(..., description="Text content of the chunk.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata about the chunk (e.g. page number, section).",
    )


class EmbeddedChunk(BaseModel):
    chunk_id: str = Field(..., description="Identifier of the chunk this embedding was generated from.")
    document_id: str = Field(..., description="Identifier of the document this chunk was derived from.")
    embedding: list[float] = Field(..., description="Embedding vector generated from the chunk's text.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata carried over unchanged from the source DocumentChunk.",
    )


class RetrievedChunk(BaseModel):
    chunk_id: str = Field(..., description="Identifier of the retrieved chunk.")
    document_id: str = Field(..., description="Identifier of the document this chunk was derived from.")
    text: str = Field(..., description="Text content of the retrieved chunk.")
    score: float = Field(..., description="Similarity score between the query and this chunk.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata associated with the chunk (e.g. chunk_index, total_chunks, source).",
    )


class WebSearchResult(BaseModel):
    title: str = Field(..., description="Title of the web search result.")
    url: str = Field(..., description="URL of the web search result.")
    snippet: str = Field(..., description="Snippet/summary text of the web search result.")
