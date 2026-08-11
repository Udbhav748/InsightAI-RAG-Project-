"""Handles saving uploaded files to disk using UUID-based filenames."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.services import s3_sync_service

UPLOAD_DIR = settings.data_dir(settings.upload_dir_name)

logger = logging.getLogger(__name__)


async def save_uploaded_file(file: UploadFile) -> dict:
    """Save an uploaded file to UPLOAD_DIR under a UUID-based filename.

    Returns a dict of the fields needed to build a DocumentUploadResponse.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix
    stored_filename = f"{document_id}{extension}"
    destination = UPLOAD_DIR / stored_filename

    contents = await file.read()
    destination.write_bytes(contents)
    s3_sync_service.upload_file(destination, settings.upload_dir_name)

    logger.debug(
        "file_written",
        extra={
            "extra_fields": {
                "stored_filename": stored_filename,
                "path": str(destination),
                "file_size": len(contents),
            }
        },
    )

    return {
        "document_id": document_id,
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "file_size": len(contents),
        "upload_timestamp": datetime.now(timezone.utc),
        "status": "uploaded",
    }
