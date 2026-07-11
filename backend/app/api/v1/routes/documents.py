"""Routes for PDF document upload and management."""

from fastapi import APIRouter, File, UploadFile, status

from app.models.schemas import DocumentUploadResponse
from app.services.upload_service import save_uploaded_file

router = APIRouter(tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    saved = await save_uploaded_file(file)
    return DocumentUploadResponse(**saved)
