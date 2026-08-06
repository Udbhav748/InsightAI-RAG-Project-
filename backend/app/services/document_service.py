"""Extracts text from previously uploaded PDF files using PyMuPDF (fitz).

Pages with no extractable text layer (scanned/image-only PDFs) fall back
to OCR via pytesseract, which shells out to the tesseract binary — a
system dependency, not a pip package (see backend/Dockerfile). That
binary is genuinely optional: if it's missing, OCR is skipped and the
page is treated the way every page here used to be treated before OCR
existed, logged once as a warning. Ingestion must never crash over a
missing optional dependency.
"""

import logging
import time
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from app.core.config import settings
from app.core.exceptions import CorruptedPDFError, DocumentNotFoundError, TextExtractionError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _tesseract_available() -> bool:
    """Whether the tesseract binary is installed and callable.

    Cached, including a negative result — unlike a model load (see
    embedding_service.get_embedding_model), a missing system binary won't
    become available mid-process, so there's no reason to re-probe on
    every OCR'd page or every document.
    """
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_page(page: fitz.Page) -> str:
    """Rasterize a page at Settings.ocr_dpi and OCR it. Raises on failure
    — callers decide how to degrade (see extract_text_from_pdf)."""
    pixmap = page.get_pixmap(dpi=settings.ocr_dpi)
    image = Image.open(BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(image)


def extract_text_from_pdf(document_id: str, file_path: Path) -> dict:
    """Extract text from every page of a PDF, in order.

    Returns a dict with extracted_text, total_pages, extracted_characters,
    and pages_ocred. A page with no extractable text layer is first tried
    via OCR (rasterize + pytesseract); if OCR is unavailable or also
    finds nothing, the page is skipped when building extracted_text, but
    still counted in total_pages.
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
        pages_ocred = 0
        ocr_unavailable_warned = False

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
                continue

            # No extractable text layer — likely a scanned/image-only
            # page. Fall back to OCR if the tesseract binary is available.
            if not _tesseract_available():
                if not ocr_unavailable_warned:
                    logger.warning(
                        "ocr_unavailable",
                        extra={"extra_fields": {"document_id": document_id}},
                    )
                    ocr_unavailable_warned = True
                continue

            try:
                ocr_text = _ocr_page(page)
            except Exception as exc:
                # A single page's OCR failing (corrupt image data, etc.)
                # shouldn't take down the whole extraction — skip just
                # this page, same as if it had no text at all.
                logger.warning(
                    "ocr_page_failed",
                    extra={
                        "extra_fields": {
                            "document_id": document_id,
                            "page_number": page.number + 1,
                            "error": str(exc),
                        }
                    },
                )
                continue

            if ocr_text and ocr_text.strip():
                page_texts.append(ocr_text)
                pages_ocred += 1

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
                "pages_ocred": pages_ocred,
                "duration_seconds": round(duration_seconds, 4),
            }
        },
    )

    return {
        "extracted_text": extracted_text,
        "total_pages": total_pages,
        "extracted_characters": extracted_characters,
        "pages_ocred": pages_ocred,
    }
