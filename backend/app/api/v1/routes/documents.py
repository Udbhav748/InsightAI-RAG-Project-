"""Routes for PDF document upload and management."""

import logging

from fastapi import APIRouter, File, UploadFile, status

from app.models.schemas import DocumentUploadResponse
from app.services.upload_service import save_uploaded_file
from app.services.validation_service import validate_pdf_upload

router = APIRouter(tags=["Documents"])
logger = logging.getLogger(__name__)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    contents = await file.read()
    await file.seek(0)

    validate_pdf_upload(file, contents)

    saved = await save_uploaded_file(file)

    logger.info(
        "document_uploaded",
        extra={
            "extra_fields": {
                "document_id": saved["document_id"],
                "original_filename": saved["original_filename"],
                "file_size": saved["file_size"],
            }
        },
    )

    return DocumentUploadResponse(**saved)
