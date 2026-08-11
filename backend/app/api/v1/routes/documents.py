"""Routes for PDF document upload, listing, and management."""

import logging

from fastapi import APIRouter, Depends, File, Request, UploadFile, status

from app.api.v1.routes.query import get_vector_store
from app.core.auth import require_api_key
from app.core import permissions
from app.core.config import settings
from app.core.exceptions import (
    ApprovalRequiredError,
    ConfirmationRequiredError,
    DocumentNotFoundError,
)
from app.models.schemas import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentProcessingResponse,
)
from app.services import s3_sync_service
from app.services.document_processing_service import DocumentProcessingService
from app.services.document_repository import delete_document_metadata, get_document_owner, list_documents
from app.services.upload_service import UPLOAD_DIR
from app.services.validation_service import validate_pdf_upload

router = APIRouter(tags=["Documents"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


@router.get("/documents", response_model=DocumentListResponse)
def list_uploaded_documents(request: Request, all_tenants: bool = False) -> DocumentListResponse:
    """List the caller's documents (tenant-scoped when the DB is enabled;
    empty when the DB is disabled).

    all_tenants=true is one of two permission-gated actions in this app
    (see app/core/permissions.py's registry — the other is DELETE
    /documents/{id}): an admin can opt into seeing every tenant's
    documents, for oversight, instead of only their own.
    list_documents(None) already returns everything unfiltered (see
    document_repository.py) — this route only needed to decide *when*
    passing None is allowed. A non-admin passing all_tenants=true is
    denied outright rather than silently falling back to their own
    scope, so a caller relying on this flag finds out immediately if it
    didn't take effect.
    """
    tenant_id = getattr(request.state, "tenant_id", None)

    if all_tenants:
        permissions.check_permission(
            request,
            permissions.DOCUMENT_LIST_ALL_TENANTS,
            message="Listing documents across all tenants requires the admin role.",
        )
        tenant_id = None

    docs = list_documents(tenant_id)

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "documents_listed",
                "path": request.url.path,
                "count": len(docs),
                "client": getattr(request.state, "client_name", "unknown"),
                "tenant_id": tenant_id,
                "all_tenants": all_tenants,
            }
        },
    )

    return DocumentListResponse(documents=docs, total=len(docs))


@router.post(
    "/upload",
    response_model=DocumentProcessingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request, file: UploadFile = File(...)
) -> DocumentProcessingResponse:
    contents = await file.read()
    await file.seek(0)

    validate_pdf_upload(file, contents)

    # get_vector_store() is the same cached instance the /chat route uses
    # (see query.py), so a document processed here is immediately visible
    # to chat without a reload.
    service = DocumentProcessingService(get_vector_store())
    tenant_id = getattr(request.state, "tenant_id", None)
    response = await service.process(file, tenant_id=tenant_id)

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "document_uploaded",
                "path": request.url.path,
                "document_id": response.document_id,
                "client": getattr(request.state, "client_name", "unknown"),
                "tenant_id": tenant_id,
            }
        },
    )

    return response


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str, request: Request, confirm: bool = False, approved: bool = False
) -> DocumentDeleteResponse:
    if not confirm:
        raise ConfirmationRequiredError(
            "Deleting a document is irreversible. Retry with ?confirm=true to proceed."
        )

    # Human-approval gate: a deployment policy (off by default), separate
    # from the confirm check above (mistake-prevention) and the role check
    # below (access control) — mirrors web_search_requires_approval's exact
    # shape in rag_service.py. When enabled, the caller must explicitly opt
    # in with approved=true on top of confirm=true.
    if settings.document_delete_requires_approval and not approved:
        logger.info(
            "audit_event",
            extra={
                "extra_fields": {
                    "event": "document_delete_pending_approval",
                    "path": request.url.path,
                    "document_id": document_id,
                    "client": getattr(request.state, "client_name", "unknown"),
                }
            },
        )
        raise ApprovalRequiredError(
            "Deleting this document requires approval. Retry with ?approved=true to proceed."
        )

    # Permission check (see app/core/permissions.py): only enforced when
    # the DB is enabled (role has nowhere to live otherwise —
    # request.state.role is None, not "member", when the DB is disabled,
    # matching tenant_id's own None-when-disabled convention below).
    # DOCUMENT_DELETE degrades to "allowed" when role is None, so a
    # non-DB deployment keeps today's pre-RBAC behavior (delete always
    # allowed) rather than silently locking everyone out because no role
    # could be determined.
    permissions.check_permission(
        request,
        permissions.DOCUMENT_DELETE,
        message="Deleting documents requires the admin role.",
        document_id=document_id,
    )

    # Ownership check: only enforced when we can actually verify it (a
    # requesting tenant *and* a known owner). An unknown owner (no DB row —
    # DB disabled, or uploaded before tenant tracking existed) isn't
    # treated as a mismatch: the vector store, not this row, is the source
    # of truth for whether the document exists at all. 404, not 403 — a
    # non-owner gets the same response as "doesn't exist" rather than a
    # signal that confirms the document is real.
    requester_tenant_id = getattr(request.state, "tenant_id", None)
    if requester_tenant_id is not None:
        owner_tenant_id = get_document_owner(document_id)
        if owner_tenant_id is not None and owner_tenant_id != requester_tenant_id:
            logger.warning(
                "audit_event",
                extra={
                    "extra_fields": {
                        "event": "document_delete_denied_wrong_tenant",
                        "path": request.url.path,
                        "document_id": document_id,
                        "client": getattr(request.state, "client_name", "unknown"),
                    }
                },
            )
            raise DocumentNotFoundError(f"No document found with id {document_id}")

    vector_store = get_vector_store()
    removed_count = vector_store.delete_document(document_id)

    if removed_count == 0:
        raise DocumentNotFoundError(f"No document found with id {document_id}")

    vector_store.save()

    # Best-effort cleanup of the uploaded file on disk — the document is
    # already gone from the vector store regardless of whether this finds
    # anything, so a missing file here isn't an error.
    for path in UPLOAD_DIR.glob(f"{document_id}.*"):
        path.unlink(missing_ok=True)
        # So the deleted file doesn't resurrect on the next cold start's
        # s3_sync_service.download_all() (no-op when sync is disabled).
        s3_sync_service.delete_file(path.name, settings.upload_dir_name)

    # Best-effort removal of the durable metadata row (no-op if DB disabled).
    delete_document_metadata(document_id)

    logger.info(
        "audit_event",
        extra={
            "extra_fields": {
                "event": "document_deleted",
                "path": request.url.path,
                "document_id": document_id,
                "chunks_removed": removed_count,
                "client": getattr(request.state, "client_name", "unknown"),
            }
        },
    )

    return DocumentDeleteResponse(
        document_id=document_id,
        chunks_removed=removed_count,
        status="deleted",
    )
