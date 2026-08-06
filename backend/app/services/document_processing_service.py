"""Orchestrates the end-to-end document processing pipeline: upload, text
extraction, chunking, embedding, and vector storage.

DocumentProcessingService contains no extraction, chunking, embedding, or
storage logic itself — it only calls the existing services in order and
reports on the result. Depends on the VectorStore interface, never on a
concrete implementation; that's constructed elsewhere and handed in.
"""

import logging
import time

from fastapi import UploadFile

from app.core.exceptions import VectorStoreNotFoundError
from app.models.document import ExtractedDocument
from app.models.schemas import DocumentProcessingResponse
from app.services.chunking_service import chunk_document
from app.services.document_service import extract_text_from_pdf
from app.services.embedding_service import generate_embeddings
from app.services.pii_service import detect_pii
from app.services.upload_service import UPLOAD_DIR, save_uploaded_file
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    def __init__(self, vector_store: VectorStore):
        self._vector_store = vector_store

    async def process(self, file: UploadFile) -> DocumentProcessingResponse:
        start = time.perf_counter()

        uploaded = await save_uploaded_file(file)
        document_id = uploaded["document_id"]
        self._log_stage("upload", document_id, file_size=uploaded["file_size"])

        file_path = UPLOAD_DIR / uploaded["stored_filename"]
        extracted = extract_text_from_pdf(document_id, file_path)
        self._log_stage(
            "extraction",
            document_id,
            total_pages=extracted["total_pages"],
            pages_ocred=extracted["pages_ocred"],
        )

        extracted_document = ExtractedDocument(document_id=document_id, **extracted)

        # Policy: flag and continue. PII does not block ingestion — it's
        # only logged (as counts, never raw values) for later review.
        pii_counts = detect_pii(extracted_document.extracted_text)
        if pii_counts:
            logger.warning(
                "pii_detected",
                extra={
                    "extra_fields": {
                        "document_id": document_id,
                        "pii_counts": pii_counts,
                    }
                },
            )

        chunks = chunk_document(extracted_document)
        self._log_stage("chunking", document_id, total_chunks=len(chunks))

        embedded_chunks = generate_embeddings(chunks)
        self._log_stage("embedding", document_id, total_embeddings=len(embedded_chunks))

        if embedded_chunks:
            try:
                self._vector_store.add_embeddings(embedded_chunks)
            except VectorStoreNotFoundError:
                # First document ever processed against this store: create
                # it now, sized to what we just embedded, then retry once.
                self._vector_store.create_index(dimension=len(embedded_chunks[0].embedding))
                self._vector_store.add_embeddings(embedded_chunks)
            self._vector_store.save()

        self._log_stage(
            "vector_store", document_id, total_vectors=self._vector_store.total_vectors()
        )

        processing_duration = time.perf_counter() - start

        logger.info(
            "document_processing_completed",
            extra={
                "extra_fields": {
                    "document_id": document_id,
                    "total_pages": extracted["total_pages"],
                    "total_chunks": len(chunks),
                    "total_embeddings": len(embedded_chunks),
                    "pages_ocred": extracted["pages_ocred"],
                    "processing_duration": round(processing_duration, 4),
                }
            },
        )

        return DocumentProcessingResponse(
            document_id=document_id,
            original_filename=uploaded["original_filename"],
            total_pages=extracted["total_pages"],
            total_chunks=len(chunks),
            total_embeddings=len(embedded_chunks),
            pages_ocred=extracted["pages_ocred"],
            processing_time=round(processing_duration, 4),
            status="processed",
        )

    def _log_stage(self, stage: str, document_id: str, **fields) -> None:
        logger.info(
            "pipeline_stage_completed",
            extra={"extra_fields": {"stage": stage, "document_id": document_id, **fields}},
        )
