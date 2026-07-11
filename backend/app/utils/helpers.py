"""Shared utility functions (e.g., file validation, text cleaning)."""

PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC_BYTES = b"%PDF-"
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def is_pdf_mime_type(content_type: str | None) -> bool:
    return content_type == PDF_CONTENT_TYPE


def has_pdf_magic_bytes(contents: bytes) -> bool:
    return contents.startswith(PDF_MAGIC_BYTES)


def is_empty(contents: bytes) -> bool:
    return len(contents) == 0


def exceeds_size_limit(contents: bytes, max_size: int = MAX_UPLOAD_SIZE_BYTES) -> bool:
    return len(contents) > max_size
