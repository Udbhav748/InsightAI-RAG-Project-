"""Routes for PDF document upload and management."""

from fastapi import APIRouter, File, UploadFile, status

from app.api.v1.routes.query import get_vector_store
from app.models.schemas import DocumentProcessingResponse
from app.services.document_processing_service import DocumentProcessingService
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
