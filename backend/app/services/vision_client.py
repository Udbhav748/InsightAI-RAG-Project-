"""HTTP client for LeafSense, a separate FastAPI vision service that
classifies plant leaf photos into one of 38 disease/healthy classes.

LeafSense keeps its own TensorFlow/Keras stack in its own process;
InsightAI never imports TensorFlow or any LeafSense code — this module
only makes an HTTP call, the same isolation web_search_service.py uses
for duckduckgo_search or gemini_client.py uses for the google-genai SDK.

Contract (verified against LeafSense's backend/main.py directly, not
assumed): POST /predict/{model_id} (model_id is accepted for compatibility
with LeafSense's own frontend's per-crop routes but unused server-side —
every model_id runs the same hybrid model) with a multipart field named
"file", returning {"class": "<raw label>", "confidence": <float 0-1>}.
"""

import logging
import time

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app.core.config import settings
from app.core.exceptions import VisionServiceError
from app.models.document import VisionPrediction
from app.services.tool_registry import track_tool

logger = logging.getLogger(__name__)


def _log_retry(retry_state: RetryCallState) -> None:
    # .outcome is a property, not a plain attribute -- assign it to a local
    # so mypy can narrow the None check (it won't narrow across repeated
    # property reads, since a property isn't guaranteed to return the same
    # value each access).
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    logger.warning(
        "vision_request_retrying",
        extra={
            "extra_fields": {
                "attempt": retry_state.attempt_number,
                "exception": str(exception),
            }
        },
    )


# model_id is unused by LeafSense's endpoint (every id runs the same hybrid
# model) — kept as a fixed, descriptive literal rather than a config value
# since it has no actual effect on the call.
_MODEL_ID = "insightai"

# LeafSense's CLASS_NAMES (backend/main.py), copied verbatim — order
# doesn't matter here since this client only ever receives the label
# *string* back, never an index, but the exact spelling (including the
# raw space in the corn/GLS entry and the trailing underscore in
# "Common_rust_") must match exactly for CLASS_LABEL_MAP lookups to hit.
# Do not "clean up" these strings.
CLASS_LABEL_MAP: dict[str, tuple[str, str]] = {
    "Apple___Apple_scab": ("apple", "apple scab"),
    "Apple___Black_rot": ("apple", "black rot"),
    "Apple___Cedar_apple_rust": ("apple", "cedar apple rust"),
    "Apple___healthy": ("apple", "healthy"),
    "Blueberry___healthy": ("blueberry", "healthy"),
    "Cherry_(including_sour)___Powdery_mildew": ("cherry", "powdery mildew"),
    "Cherry_(including_sour)___healthy": ("cherry", "healthy"),
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": ("corn", "gray leaf spot"),
    "Corn_(maize)___Common_rust_": ("corn", "common rust"),
    "Corn_(maize)___Northern_Leaf_Blight": ("corn", "northern corn leaf blight"),
    "Corn_(maize)___healthy": ("corn", "healthy"),
    "Grape___Black_rot": ("grape", "black rot"),
    "Grape___Esca_(Black_Measles)": ("grape", "esca (black measles)"),
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": ("grape", "leaf blight (isariopsis leaf spot)"),
    "Grape___healthy": ("grape", "healthy"),
    "Orange___Haunglongbing_(Citrus_greening)": ("orange", "citrus greening (huanglongbing)"),
    "Peach___Bacterial_spot": ("peach", "bacterial spot"),
    "Peach___healthy": ("peach", "healthy"),
    "Pepper,_bell___Bacterial_spot": ("bell pepper", "bacterial spot"),
    "Pepper,_bell___healthy": ("bell pepper", "healthy"),
    "Potato___Early_blight": ("potato", "early blight"),
    "Potato___Late_blight": ("potato", "late blight"),
    "Potato___healthy": ("potato", "healthy"),
    "Raspberry___healthy": ("raspberry", "healthy"),
    "Soybean___healthy": ("soybean", "healthy"),
    "Squash___Powdery_mildew": ("squash", "powdery mildew"),
    "Strawberry___Leaf_scorch": ("strawberry", "leaf scorch"),
    "Strawberry___healthy": ("strawberry", "healthy"),
    "Tomato___Bacterial_spot": ("tomato", "bacterial spot"),
    "Tomato___Early_blight": ("tomato", "early blight"),
    "Tomato___Late_blight": ("tomato", "late blight"),
    "Tomato___Leaf_Mold": ("tomato", "leaf mold"),
    "Tomato___Septoria_leaf_spot": ("tomato", "septoria leaf spot"),
    "Tomato___Spider_mites Two-spotted_spider_mite": ("tomato", "two-spotted spider mite"),
    "Tomato___Target_Spot": ("tomato", "target spot"),
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": ("tomato", "tomato yellow leaf curl virus"),
    "Tomato___Tomato_mosaic_virus": ("tomato", "tomato mosaic virus"),
    "Tomato___healthy": ("tomato", "healthy"),
}


@track_tool("diagnose")
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(VisionServiceError),
    reraise=True,
    before_sleep=_log_retry,
)
def diagnose_image(contents: bytes, filename: str, content_type: str) -> VisionPrediction:
    """POST an image to LeafSense and return its prediction, mapped to a
    plain-language crop/disease pair.

    Raises VisionServiceError if LeafSense is unreachable, times out, or
    returns something outside its documented {class, confidence} contract
    — callers are expected to let this propagate as a request failure
    rather than guess at a diagnosis. Transient failures (timeout,
    connection error, non-2xx) get up to 3 attempts total (same retry
    shape as web_search_service.search_web) before that happens.
    """
    start = time.perf_counter()
    headers = {}
    if settings.vision_service_api_key:
        # Same X-API-Key convention this app's own inbound auth uses, so a
        # single shared secret style can protect both directions. Empty by
        # default (local LeafSense needs no auth) — see Settings.
        headers["X-API-Key"] = settings.vision_service_api_key
    try:
        response = httpx.post(
            f"{settings.vision_service_url}/predict/{_MODEL_ID}",
            files={"file": (filename, contents, content_type)},
            headers=headers,
            timeout=settings.vision_service_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise VisionServiceError(
            f"LeafSense request timed out after {settings.vision_service_timeout_seconds}s: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise VisionServiceError(
            f"LeafSense returned {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        raise VisionServiceError(
            f"Could not reach LeafSense at {settings.vision_service_url}: {exc}"
        ) from exc

    try:
        payload = response.json()
        raw_class = payload["class"]
        confidence = float(payload["confidence"])
    except (ValueError, KeyError, TypeError) as exc:
        raise VisionServiceError(f"LeafSense returned an unexpected response shape: {exc}") from exc

    crop, disease = CLASS_LABEL_MAP.get(raw_class, (None, None))
    if crop is None:
        # LeafSense returned a class label this map doesn't recognize —
        # most likely its CLASS_NAMES changed out from under us. Don't
        # fail the request over it; fall through with the raw label so
        # retrieval still has *something* to search on, but log loudly
        # since this means the map is stale and needs updating.
        logger.warning("vision_unmapped_class", extra={"extra_fields": {"raw_class": raw_class}})
        crop, disease = "unknown", raw_class

    processing_duration = time.perf_counter() - start
    low_confidence = confidence < settings.vision_confidence_threshold

    logger.info(
        "vision_diagnosis_completed",
        extra={
            "extra_fields": {
                "raw_class": raw_class,
                "crop": crop,
                "disease": disease,
                "confidence": round(confidence, 4),
                "low_confidence": low_confidence,
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return VisionPrediction(
        raw_class=raw_class,
        crop=crop,
        disease=disease,
        confidence=confidence,
        low_confidence=low_confidence,
    )
