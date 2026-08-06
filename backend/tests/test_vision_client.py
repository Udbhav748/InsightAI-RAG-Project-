"""Unit tests for vision_client.py's LeafSense HTTP call and class-label
mapping. Never calls a real LeafSense instance — httpx.post is
monkeypatched per test, the same boundary-mocking style test_groq_client.py
uses for the Groq SDK.
"""

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import VisionServiceError
from app.services import vision_client as vision_client_module
from app.services.vision_client import CLASS_LABEL_MAP, diagnose_image


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://leafsense.test/predict/insightai")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError(
                f"{self.status_code} error", request=request, response=response
            )

    def json(self):
        return self._json_data


class TestClassLabelMap:
    def test_has_38_classes(self):
        assert len(CLASS_LABEL_MAP) == 38

    def test_disambiguates_shared_disease_name_across_crops(self):
        # Bacterial_spot exists for both peach and tomato in LeafSense's
        # class list, with different corpus content behind each — the map
        # must key by the full raw class, not just the disease suffix.
        assert CLASS_LABEL_MAP["Peach___Bacterial_spot"] == ("peach", "bacterial spot")
        assert CLASS_LABEL_MAP["Tomato___Bacterial_spot"] == ("tomato", "bacterial spot")

    def test_maps_healthy_classes(self):
        assert CLASS_LABEL_MAP["Apple___healthy"] == ("apple", "healthy")


class TestDiagnoseImage:
    def test_happy_path_high_confidence_in_corpus(self, monkeypatch):
        monkeypatch.setattr(settings, "vision_confidence_threshold", 0.5)
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse({"class": "Peach___Bacterial_spot", "confidence": 0.94}),
        )

        prediction = diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

        assert prediction.raw_class == "Peach___Bacterial_spot"
        assert prediction.crop == "peach"
        assert prediction.disease == "bacterial spot"
        assert prediction.confidence == pytest.approx(0.94)
        assert prediction.low_confidence is False

    def test_low_confidence_prediction_is_flagged_not_hidden(self, monkeypatch):
        monkeypatch.setattr(settings, "vision_confidence_threshold", 0.5)
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse({"class": "Tomato___Early_blight", "confidence": 0.31}),
        )

        prediction = diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

        # Still returns the prediction rather than refusing it outright —
        # the caller decides what to do with an uncertain guess.
        assert prediction.crop == "tomato"
        assert prediction.disease == "early blight"
        assert prediction.low_confidence is True

    def test_crop_not_in_corpus_still_maps_and_flags_nothing_special(self, monkeypatch):
        # LeafSense covers 38 classes; InsightAI's corpus only covers 5
        # crops (apple, corn, potato, tomato, peach). Grape is a real
        # LeafSense class with no corpus content behind it — the client
        # itself doesn't know about the corpus, so it should map normally;
        # falling back gracefully is retrieval's job (see rag_service.py).
        monkeypatch.setattr(settings, "vision_confidence_threshold", 0.5)
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse({"class": "Grape___Black_rot", "confidence": 0.88}),
        )

        prediction = diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

        assert prediction.crop == "grape"
        assert prediction.disease == "black rot"
        assert prediction.low_confidence is False

    def test_unmapped_class_falls_back_to_raw_label(self, monkeypatch):
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse({"class": "Something___Unrecognized", "confidence": 0.7}),
        )

        prediction = diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

        assert prediction.crop == "unknown"
        assert prediction.disease == "Something___Unrecognized"

    def test_service_unreachable_raises_vision_service_error(self, monkeypatch):
        def _raise_connect_error(*a, **k):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(vision_client_module.httpx, "post", _raise_connect_error)

        with pytest.raises(VisionServiceError):
            diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

    def test_timeout_raises_vision_service_error(self, monkeypatch):
        def _raise_timeout(*a, **k):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(vision_client_module.httpx, "post", _raise_timeout)

        with pytest.raises(VisionServiceError):
            diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

    def test_http_error_status_raises_vision_service_error(self, monkeypatch):
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse(status_code=503, text="Model is not loaded."),
        )

        with pytest.raises(VisionServiceError):
            diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")

    def test_malformed_response_shape_raises_vision_service_error(self, monkeypatch):
        monkeypatch.setattr(
            vision_client_module.httpx,
            "post",
            lambda *a, **k: _FakeResponse({"unexpected": "shape"}),
        )

        with pytest.raises(VisionServiceError):
            diagnose_image(b"fake-bytes", "leaf.jpg", "image/jpeg")
