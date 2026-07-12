"""Routes for PDF document upload and management."""

from fastapi import APIRouter, File, UploadFile, status

from app.api.v1.routes.query import get_vector_store
from app.core.exceptions import DocumentNotFoundError
from app.models.schemas import DocumentDeleteResponse, DocumentProcessingResponse
from app.services.document_processing_service import DocumentProcessingService
from app.services.upload_service import UPLOAD_DIR
from app.services.validation_service import validate_pdf_upload

router = APIRouter(tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentProcessingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile = File(...)) -> DocumentProcessingResponse:
    contents = await file.read()
    await file.seek(0)

    validate_pdf_upload(file, contents)

    # get_vector_store() is the same cached instance the /chat route uses
    # (see query.py), so a document processed here is immediately visible
    # to chat without a reload.
    service = DocumentProcessingService(get_vector_store())
    return await service.process(file)


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(document_id: str) -> DocumentDeleteResponse:
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

    return DocumentDeleteResponse(
        document_id=document_id,
        chunks_removed=removed_count,
        status="deleted",
    )
