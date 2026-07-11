"""Splits an ExtractedDocument into DocumentChunks using LangChain's
RecursiveCharacterTextSplitter.

Independent of embeddings and vector storage: this service only turns text
into sized, overlapping chunks with traceable metadata.
"""

import logging
import time
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.models.document import DocumentChunk, ExtractedDocument

logger = logging.getLogger(__name__)


def chunk_document(document: ExtractedDocument) -> list[DocumentChunk]:
    """Split document.extracted_text into DocumentChunks.

    Chunk size and overlap come from Settings (chunk_size, chunk_overlap).
    """
    start = time.perf_counter()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    texts = splitter.split_text(document.extracted_text)
    total_chunks = len(texts)

    chunks = [
        DocumentChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=document.document_id,
            chunk_index=index,
            text=text,
            metadata={
                "document_id": document.document_id,
                "chunk_index": index,
                "total_chunks": total_chunks,
                "source": "pdf",
            },
        )
        for index, text in enumerate(texts)
    ]

    processing_duration = time.perf_counter() - start

    logger.info(
        "document_chunked",
        extra={
            "extra_fields": {
                "document_id": document.document_id,
                "total_chunks": total_chunks,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return chunks
