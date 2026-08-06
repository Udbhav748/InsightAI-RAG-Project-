"""Extracts text from previously uploaded PDF files using PyMuPDF (fitz).

Pages whose own text falls short of Settings.ocr_min_chars_per_page — not
just totally blank pages — fall back to OCR via pytesseract, which shells
out to the tesseract binary. That binary is a system dependency, not a
pip package (see backend/Dockerfile), and it's genuinely optional: if
it's missing, OCR is skipped and whatever thin native text a page had is
kept as-is, logged once as a warning. Ingestion must never crash over a
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

    Deliberately `except Exception`, not `except TesseractNotFoundError`:
    a present-but-broken tesseract install (missing shared libraries, a
    bad PATH, wrong architecture) raises other exception types from the
    subprocess call, and those need to degrade the same way a missing
    binary does — don't narrow this without re-checking that case.
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
    and pages_ocred. A page whose own text falls short of
    Settings.ocr_min_chars_per_page — not just a totally blank page — is
    tried via OCR (rasterize + pytesseract); real scans routinely carry a
    thin native text layer (a header, a page number, a few garbled
    characters from a bad prior OCR pass) that would otherwise pass as
    "has text" and ship a near-useless chunk to the index. If OCR isn't
    available or also comes up empty, whatever thin native text existed
    is kept rather than discarded — it's better than nothing even if it
    didn't clear the trust threshold on its own.
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

            native_text = page_text.strip() if page_text else ""

            if len(native_text) >= settings.ocr_min_chars_per_page:
                page_texts.append(page_text)
                continue

            # Below the trust threshold — either truly blank or carrying
            # only a thin native text layer. Try OCR; degrade to the thin
            # native text (if any) rather than losing it outright.
            if not _tesseract_available():
                if not ocr_unavailable_warned:
                    logger.warning(
                        "ocr_unavailable",
                        extra={"extra_fields": {"document_id": document_id}},
                    )
                    ocr_unavailable_warned = True
                if native_text:
                    page_texts.append(page_text)
                continue

            try:
                ocr_text = _ocr_page(page)
            except Exception as exc:
                # A single page's OCR failing (corrupt image data, etc.)
                # shouldn't take down the whole extraction — fall back to
                # this page's thin native text (if any) and move on.
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
                if native_text:
                    page_texts.append(page_text)
                continue

            if ocr_text and ocr_text.strip():
                page_texts.append(ocr_text)
                pages_ocred += 1
            elif native_text:
                # OCR ran but found nothing usable either — the thin
                # native text is still the best material available.
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
