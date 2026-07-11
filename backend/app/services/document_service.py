"""Extracts text from previously uploaded PDF files using PyMuPDF (fitz)."""

import logging
import time
from pathlib import Path

import fitz

from app.core.exceptions import CorruptedPDFError, DocumentNotFoundError, TextExtractionError

logger = logging.getLogger(__name__)


def extract_text_from_pdf(document_id: str, file_path: Path) -> dict:
    """Extract text from every page of a PDF, in order.

    Returns a dict with extracted_text, total_pages, and extracted_characters.
    Pages with no extractable text are skipped when building extracted_text,
    but still counted in total_pages.
    """
    if not file_path.is_file():
        raise DocumentNotFoundError(f"No such file: {file_path}")

    start = time.perf_counter()

    try:
        document = fitz.open(file_path)
    except fitz.FileDataError as exc:
        raise CorruptedPDFError(f"File is not a valid PDF: {file_path.name}") from exc

    try:
        page_texts = []
        for page in document:
            try:
                page_text = page.get_text()
            except Exception as exc:
                raise TextExtractionError(
                    f"Failed to extract text from page {page.number + 1} "
                    f"of {file_path.name}"
                ) from exc

            if page_text and page_text.strip():
                page_texts.append(page_text)

        total_pages = document.page_count
    finally:
        document.close()

    extracted_text = "\n".join(page_texts)
    extracted_characters = len(extracted_text)
    duration_seconds = time.perf_counter() - start

    logger.info(
        "pdf_text_extracted",
        extra={
            "extra_fields": {
                "document_id": document_id,
                "total_pages": total_pages,
                "extracted_characters": extracted_characters,
                "duration_seconds": round(duration_seconds, 4),
            }
        },
    )

    return {
        "extracted_text": extracted_text,
        "total_pages": total_pages,
        "extracted_characters": extracted_characters,
    }
