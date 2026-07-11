"""Handles saving uploaded files to disk using UUID-based filenames."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


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

    return {
        "document_id": document_id,
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "file_size": len(contents),
        "upload_timestamp": datetime.now(timezone.utc),
        "status": "uploaded",
    }
