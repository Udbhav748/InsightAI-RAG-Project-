"""Routes for PDF document upload and management."""

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.schemas import DocumentUploadResponse
from app.services.upload_service import save_uploaded_file
from app.utils.helpers import (
    exceeds_size_limit,
    has_pdf_magic_bytes,
    is_empty,
    is_pdf_mime_type,
)

router = APIRouter(tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    if not is_pdf_mime_type(file.content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only application/pdf files are accepted.",
        )

    contents = await file.read()
    await file.seek(0)

    if is_empty(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if exceeds_size_limit(contents):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds the 20 MB size limit.",
        )

    if not has_pdf_magic_bytes(contents):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content is not a valid PDF.",
        )

    saved = await save_uploaded_file(file)
    return DocumentUploadResponse(**saved)
