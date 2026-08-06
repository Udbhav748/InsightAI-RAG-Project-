"""Unit tests for document_service.py's OCR fallback.

Builds tiny real PDFs in-process with PyMuPDF — no fixture files on disk.
The actual OCR *success* path needs a working tesseract binary (a system
dependency, not a pip package — see backend/Dockerfile), so that specific
test is skipped cleanly when it's unavailable; the graceful-degradation
paths (binary missing, a single page's OCR call failing) are tested via
monkeypatch and always run, since they don't depend on the environment.
"""

import fitz
import pytest
from PIL import Image, ImageDraw

from app.services import document_service
from app.services.document_service import extract_text_from_pdf


def _tesseract_actually_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _make_text_pdf(path, text="Hello embedded text"):
    """A normal PDF with a real, extractable text layer."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _make_image_only_pdf(path, text="Hello OCR World", size=(600, 200)):
    """A PDF whose only page has no text layer at all — the text is
    rendered into an image and the image is inserted as the page's
    content, exactly like a scanned document. PyMuPDF's own get_text()
    on this page returns "" (verified in development), which is what
    triggers document_service's OCR fallback."""
    image = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(image)
    draw.text((20, size[1] // 2 - 10), text, fill="black")
    image_path = path.with_suffix(".png")
    image.save(image_path)

    doc = fitz.open()
    page = doc.new_page(width=size[0], height=size[1])
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(path)
    doc.close()


@pytest.fixture(autouse=True)
def clear_tesseract_availability_cache():
    """_tesseract_available() is lru_cache'd for the process lifetime —
    clear it around each test so one test's monkeypatching (or the real
    environment probe) can't leak into another."""
    document_service._tesseract_available.cache_clear()
    yield
    document_service._tesseract_available.cache_clear()


class TestNormalExtraction:
    def test_page_with_text_layer_is_never_sent_to_ocr(self, tmp_path, monkeypatch):
        pdf_path = tmp_path / "normal.pdf"
        _make_text_pdf(pdf_path, text="Hello embedded text")

        # If OCR were attempted here, this would raise (or return
        # something else) — proves the OCR path is only reached for
        # pages with no text layer at all.
        monkeypatch.setattr(
            document_service,
            "_ocr_page",
            lambda page: (_ for _ in ()).throw(AssertionError("OCR should not run on a text page")),
        )

        result = extract_text_from_pdf("doc-1", pdf_path)

        assert "Hello embedded text" in result["extracted_text"]
        assert result["pages_ocred"] == 0
        assert result["total_pages"] == 1


class TestOCRFallback:
    @pytest.mark.skipif(
        not _tesseract_actually_available(),
        reason="tesseract binary not installed/callable in this environment",
    )
    def test_image_only_page_is_recovered_via_real_ocr(self, tmp_path):
        pdf_path = tmp_path / "scanned.pdf"
        _make_image_only_pdf(pdf_path, text="Hello OCR World")

        result = extract_text_from_pdf("doc-1", pdf_path)

        assert result["pages_ocred"] >= 1
        assert result["extracted_text"].strip() != ""
        assert "hello" in result["extracted_text"].lower()

    def test_image_only_page_degrades_gracefully_when_tesseract_unavailable(
        self, tmp_path, monkeypatch
    ):
        pdf_path = tmp_path / "scanned.pdf"
        _make_image_only_pdf(pdf_path)

        monkeypatch.setattr(document_service, "_tesseract_available", lambda: False)

        result = extract_text_from_pdf("doc-1", pdf_path)

        # Old skip behavior: no crash, page just contributes nothing.
        assert result["pages_ocred"] == 0
        assert result["extracted_text"] == ""
        assert result["total_pages"] == 1

    def test_a_single_pages_ocr_failure_does_not_crash_extraction(self, tmp_path, monkeypatch):
        pdf_path = tmp_path / "scanned.pdf"
        _make_image_only_pdf(pdf_path)

        monkeypatch.setattr(document_service, "_tesseract_available", lambda: True)
        monkeypatch.setattr(
            document_service,
            "_ocr_page",
            lambda page: (_ for _ in ()).throw(RuntimeError("simulated OCR engine failure")),
        )

        result = extract_text_from_pdf("doc-1", pdf_path)

        assert result["pages_ocred"] == 0
        assert result["extracted_text"] == ""

    def test_ocr_returning_blank_text_does_not_count_as_ocred(self, tmp_path, monkeypatch):
        pdf_path = tmp_path / "scanned.pdf"
        _make_image_only_pdf(pdf_path)

        monkeypatch.setattr(document_service, "_tesseract_available", lambda: True)
        monkeypatch.setattr(document_service, "_ocr_page", lambda page: "   \n  ")

        result = extract_text_from_pdf("doc-1", pdf_path)

        assert result["pages_ocred"] == 0
        assert result["extracted_text"] == ""

    def test_successful_ocr_is_counted_and_included(self, tmp_path, monkeypatch):
        pdf_path = tmp_path / "scanned.pdf"
        _make_image_only_pdf(pdf_path)

        monkeypatch.setattr(document_service, "_tesseract_available", lambda: True)
        monkeypatch.setattr(document_service, "_ocr_page", lambda page: "Recovered text")

        result = extract_text_from_pdf("doc-1", pdf_path)

        assert result["pages_ocred"] == 1
        assert "Recovered text" in result["extracted_text"]

    def test_unavailability_is_only_logged_once_per_document(self, tmp_path, monkeypatch, caplog):
        doc = fitz.open()
        for _ in range(3):
            page = doc.new_page()
            image = Image.new("RGB", (200, 100), color="white")
            image_path = tmp_path / f"blank_{page.number}.png"
            image.save(image_path)
            page.insert_image(page.rect, filename=str(image_path))
        pdf_path = tmp_path / "multi_page_scanned.pdf"
        doc.save(pdf_path)
        doc.close()

        monkeypatch.setattr(document_service, "_tesseract_available", lambda: False)

        with caplog.at_level("WARNING"):
            result = extract_text_from_pdf("doc-1", pdf_path)

        assert result["total_pages"] == 3
        assert sum(1 for r in caplog.records if r.message == "ocr_unavailable") == 1
