"""Orchestrates the end-to-end document processing pipeline: upload, text
extraction, chunking, embedding, and vector storage.

DocumentProcessingService contains no extraction, chunking, embedding, or
storage logic itself — it only calls the existing services in order and
reports on the result. Depends on the VectorStore interface, never on a
concrete implementation; that's constructed elsewhere and handed in.
"""

import logging
import time

import numpy as np
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import VectorStoreNotFoundError
from app.models.document import DocumentChunk, ExtractedDocument, ExtractedImage
from app.models.schemas import DocumentProcessingResponse
from app.services.chunking_service import chunk_document, chunk_text
from app.services.document_repository import persist_document
from app.services.document_service import extract_images_from_pdf, extract_text_from_pdf
from app.services.embedding_service import generate_embeddings
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.image_captioning_service import (
    caption_images,
    image_storage_dir as caption_image_storage_dir,
    write_image_manifest,
)
from app.services.llm_client import LLMClient
from app.services.pii_service import detect_pii
from app.services.table_extraction_service import extract_tables_from_pdf
from app.services.upload_service import UPLOAD_DIR, save_uploaded_file
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

_IMAGE_MIME_EXT = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "gif": "gif",
                   "bmp": "bmp", "webp": "webp", "tiff": "tif", "jp2": "jp2"}


def _ext_for_mime(mime_type: str) -> str:
    ext = mime_type.split("/")[-1]
    return _IMAGE_MIME_EXT.get(ext, "png")


def _persist_images(image_records: list[dict]) -> list[ExtractedImage]:
    """Write each extracted image's bytes to Settings.image_storage_dir_name
    and return the ExtractedImage records the downstream captioning/vision
    steps operate on. A write failure for one image logs and drops that
    image (its record isn't returned) rather than failing the upload."""
    directory = caption_image_storage_dir()
    directory.mkdir(parents=True, exist_ok=True)

    persisted: list[ExtractedImage] = []
    for record in image_records:
        filename = f"{record['image_id']}.{_ext_for_mime(record['mime_type'])}"
        path = directory / filename
        try:
            path.write_bytes(record["data"])
        except OSError as exc:
            logger.warning(
                "image_persist_failed",
                extra={"extra_fields": {"image_id": record["image_id"], "error": str(exc)}},
            )
            continue
        persisted.append(
            ExtractedImage(
                image_id=record["image_id"],
                document_id=record["document_id"],
                page_number=record["page_number"],
                content_type=record["content_type"],
                storage_path=filename,
                mime_type=record["mime_type"],
                width=record["width"],
                height=record["height"],
                byte_size=len(record["data"]),
            )
        )

    # Record what was persisted so the images can be listed later
    # (GET /documents/{id}/images) without re-extracting the PDF.
    write_image_manifest(persisted)
    return persisted


class DocumentProcessingService:
    def __init__(self, vector_store: VectorStore, llm_client: LLMClient | None = None):
        self._vector_store = vector_store
        # Optional, only consulted when Settings.image_captioning_enabled:
        # captioning needs a vision-capable client, which needs a configured
        # LLM provider. None simply disables captioning (a warning is logged
        # at processing time if the flag demands it).
        self._llm_client = llm_client

    async def process(
        self, file: UploadFile, tenant_id: int | None = None, collection: str | None = None
    ) -> DocumentProcessingResponse:
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

        chunks = chunk_document(extracted_document, tenant_id=tenant_id)
        self._log_stage("chunking", document_id, total_chunks=len(chunks))

        # --- Multi-modal ingestion (all off by default) ------------------
        # Image extraction (Phase 1) → captioning (Phase 2) and table
        # extraction (Phase 5) append their chunks after the body-text
        # chunks, all embedded and stored through the *same* pipeline, so
        # the vector store sees one homogeneous index. chunk_index_start
        # keeps chunk_index ordering stable for get_chunks_by_document.
        total_images = 0
        images_captioned = 0
        total_tables = 0
        multimodal_chunks: list[DocumentChunk] = []

        if settings.image_extraction_enabled:
            image_records = extract_images_from_pdf(document_id, file_path)
            total_images = len(image_records)
            self._log_stage("image_extraction", document_id, image_count=total_images)

            if image_records:
                images = _persist_images(image_records)
                if settings.image_captioning_enabled:
                    if self._llm_client is None:
                        logger.warning(
                            "image_captioning_skipped_no_llm_client",
                            extra={"extra_fields": {"document_id": document_id}},
                        )
                    else:
                        caption_chunks = caption_images(
                            images,
                            self._llm_client,
                            document_id=document_id,
                            tenant_id=tenant_id,
                            chunk_index_start=len(chunks) + len(multimodal_chunks),
                        )
                        images_captioned = len(
                            {c.metadata["image_id"] for c in caption_chunks}
                        )
                        multimodal_chunks.extend(caption_chunks)
                        self._log_stage(
                            "image_captioning",
                            document_id,
                            images_captioned=images_captioned,
                            caption_chunks=len(caption_chunks),
                        )

        if settings.table_extraction_enabled:
            tables = extract_tables_from_pdf(document_id, file_path)
            total_tables = len(tables)
            self._log_stage("table_extraction", document_id, table_count=total_tables)
            table_chunks_count = 0
            for table in tables:
                table_chunks = chunk_text(
                    text=table.markdown,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    chunk_index_start=len(chunks) + len(multimodal_chunks),
                    source="table",
                    content_type="table",
                    page_number=table.page_number,
                    table_id=table.table_id,
                )
                table_chunks_count += len(table_chunks)
                multimodal_chunks.extend(table_chunks)
            self._log_stage(
                "table_chunking",
                document_id,
                table_chunks=table_chunks_count,
            )

        all_chunks = chunks + multimodal_chunks
        embedded_chunks = generate_embeddings(all_chunks)
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

        # Best-effort durable metadata record (PostgreSQL when configured).
        # Runs after the vector store write so a DB failure can never lose
        # the searchable document — it only loses the durable record.
        persist_document(
            tenant_id=tenant_id,
            document_id=document_id,
            original_filename=uploaded["original_filename"],
            stored_filename=uploaded["stored_filename"],
            file_size=uploaded["file_size"],
            total_pages=extracted["total_pages"],
            total_chunks=len(chunks),
            total_embeddings=len(embedded_chunks),
            pages_ocred=extracted["pages_ocred"],
            collection=collection,
        )

        # Agent 3.3 — duplicate-document detection (warn, never block).
        # The upload's own first-chunk embedding is the fingerprint;
        # compare it against every other same-tenant document's first-chunk
        # embedding (L2-normalized → inner product == cosine similarity).
        # Any failure degrades to no warning — this must never fail an
        # upload.
        possible_duplicate_of: str | None = None
        if (
            settings.duplicate_document_detection_enabled
            and embedded_chunks
            and isinstance(self._vector_store, FAISSVectorStore)
        ):
            try:
                new_first = embedded_chunks[0].embedding
                for other_id in self._vector_store.list_document_ids(tenant_id=tenant_id):
                    if other_id == document_id:
                        continue
                    other_first = self._vector_store.first_chunk_vector(other_id, tenant_id=tenant_id)
                    if other_first is None:
                        continue
                    similarity = float(np.dot(new_first, other_first))
                    if similarity >= settings.duplicate_document_similarity_threshold:
                        possible_duplicate_of = other_id
                        logger.info(
                            "duplicate_document_detected",
                            extra={
                                "extra_fields": {
                                    "document_id": document_id,
                                    "possible_duplicate_of": other_id,
                                    "similarity": round(similarity, 4),
                                }
                            },
                        )
                        break
            except Exception as exc:
                logger.warning(
                    "duplicate_document_detection_failed",
                    extra={"extra_fields": {"document_id": document_id, "error": str(exc)}},
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
                    "total_images": total_images,
                    "images_captioned": images_captioned,
                    "total_tables": total_tables,
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
            total_images=total_images,
            images_captioned=images_captioned,
            total_tables=total_tables,
            processing_time=round(processing_duration, 4),
            status="processed",
            collection=collection,
            possible_duplicate_of=possible_duplicate_of,
        )

    def _log_stage(self, stage: str, document_id: str, **fields) -> None:
        logger.info(
            "pipeline_stage_completed",
            extra={"extra_fields": {"stage": stage, "document_id": document_id, **fields}},
        )
