"""Validates uploaded files against configuration-driven rules before they are persisted."""

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import EmptyFileError, FileTooLargeError, UnsupportedFileTypeError
from app.utils.helpers import exceeds_size_limit, has_pdf_magic_bytes, is_empty, is_pdf_mime_type


def validate_pdf_upload(file: UploadFile, contents: bytes) -> None:
    if not is_pdf_mime_type(file.content_type, settings.allowed_upload_mime_types):
        raise UnsupportedFileTypeError("Only application/pdf files are accepted.")

    if is_empty(contents):
        raise EmptyFileError("Uploaded file is empty.")

    if exceeds_size_limit(contents, settings.max_upload_size_bytes):
        raise FileTooLargeError(
            f"File exceeds the {settings.max_upload_size_mb} MB size limit."
        )

    if not has_pdf_magic_bytes(contents):
        raise UnsupportedFileTypeError("File content is not a valid PDF.")
