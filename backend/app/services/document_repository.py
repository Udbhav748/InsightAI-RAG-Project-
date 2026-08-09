"""DB-backed persistence for document metadata.

The FAISS vector store remains the source of truth for chunks/vectors; this
module keeps the durable metadata record (who owns it, what processing
happened) in PostgreSQL. Every function is a no-op returning a sensible
default when the DB is disabled, so the upload/delete routes behave
identically on an ephemeral deployment.
"""

import logging
from datetime import datetime, timezone

from app.core.database import SessionLocal, db_enabled
from app.models.db_models import Document

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def persist_document(
    *,
    tenant_id: int | None,
    document_id: str,
    original_filename: str,
    stored_filename: str,
    file_size: int,
    total_pages: int,
    total_chunks: int,
    total_embeddings: int,
    pages_ocred: int,
) -> None:
    """Insert a document metadata row. Best-effort: a DB failure logs and
    does not fail the upload that already succeeded (the document is still
    searchable in the vector store)."""
    if not db_enabled() or tenant_id is None:
        return

    try:
        with SessionLocal() as db:
            db.add(
                Document(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    original_filename=original_filename,
                    stored_filename=stored_filename,
                    file_size=file_size,
                    total_pages=total_pages,
                    total_chunks=total_chunks,
                    total_embeddings=total_embeddings,
                    pages_ocred=pages_ocred,
                    upload_timestamp=_utcnow(),
                )
            )
            db.commit()
        logger.info("document_persisted", extra={"extra_fields": {"document_id": document_id}})
    except Exception as exc:
        logger.warning(
            "document_persist_failed",
            extra={"extra_fields": {"document_id": document_id, "error": str(exc)}},
        )


def delete_document_metadata(document_id: str) -> None:
    """Delete the metadata row for a document (best-effort). The vector
    store deletion is the source of truth; this cleans up the durable
    record."""
    if not db_enabled():
        return

    try:
        with SessionLocal() as db:
            db.query(Document).filter(Document.document_id == document_id).delete()
            db.commit()
        logger.info("document_metadata_deleted", extra={"extra_fields": {"document_id": document_id}})
    except Exception as exc:
        logger.warning(
            "document_metadata_delete_failed",
            extra={"extra_fields": {"document_id": document_id, "error": str(exc)}},
        )


def list_documents(tenant_id: int | None) -> list[dict]:
    """Return all documents for a tenant (or all when tenant_id is None,
    e.g. pre-multi-tenant). Returns [] when the DB is disabled."""
    if not db_enabled():
        return []

    with SessionLocal() as db:
        query = db.query(Document).order_by(Document.upload_timestamp.desc())
        if tenant_id is not None:
            query = query.filter(Document.tenant_id == tenant_id)
        return [
            {
                "document_id": doc.document_id,
                "original_filename": doc.original_filename,
                "stored_filename": doc.stored_filename,
                "file_size": doc.file_size,
                "total_pages": doc.total_pages,
                "total_chunks": doc.total_chunks,
                "total_embeddings": doc.total_embeddings,
                "pages_ocred": doc.pages_ocred,
                "upload_timestamp": doc.upload_timestamp,
            }
            for doc in query.all()
        ]
