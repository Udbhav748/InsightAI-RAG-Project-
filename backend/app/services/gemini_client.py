"""Gemini implementation of the LLMClient interface.

Isolated from the rest of the application: nothing outside this module
should import the google-genai SDK directly.
"""

import logging
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import (
    LLMAPIError,
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMTimeoutError,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _log_retry(retry_state) -> None:
    logger.warning(
        "llm_generation_retrying",
        extra={
            "extra_fields": {
                "attempt": retry_state.attempt_number,
                "exception": str(retry_state.outcome.exception()),
            }
        },
    )


class GeminiClient(LLMClient):
    def __init__(self):
        if not settings.gemini_api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not configured.")

        try:
            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=settings.gemini_timeout_seconds * 1000
                ),
            )
        except Exception as exc:
            raise LLMConfigurationError(f"Failed to configure Gemini client: {exc}") from exc

    # Only retries on LLMTimeoutError/LLMAPIError (transient failure modes)
    # — not on LLMEmptyResponseError, which usually means the prompt or
    # safety filters produced no content and a retry won't help.
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((LLMTimeoutError, LLMAPIError)),
        reraise=True,
        before_sleep=_log_retry,
    )
    def generate(self, prompt: str) -> str:
        start = time.perf_counter()

        try:
            response = self._client.models.generate_content(
                model=settings.gemini_model_name,
                contents=prompt,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Gemini request timed out after {settings.gemini_timeout_seconds}s: {exc}"
            ) from exc
        except genai_errors.APIError as exc:
            raise LLMAPIError(f"Gemini API request failed: {exc}") from exc
        except Exception as exc:
            raise LLMAPIError(f"Unexpected error calling Gemini: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise LLMEmptyResponseError("Gemini returned an empty response.")

        processing_duration = time.perf_counter() - start

        logger.info(
            "llm_generation_completed",
            extra={
                "extra_fields": {
                    "model_name": settings.gemini_model_name,
                    "prompt_length": len(prompt),
                    "response_length": len(text),
                    "processing_duration": round(processing_duration, 4),
                }
            },
        )

        return text
