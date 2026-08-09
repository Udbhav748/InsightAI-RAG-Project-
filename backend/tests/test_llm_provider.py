"""Unit tests for the provider factory and fallback-wiring logic in
app/services/llm_provider.py.

Constructing GeminiClient/GroqClient here is safe offline — both SDK
clients validate their config and build an HTTP client object without
making a network call.
"""

import pytest

from app.core.config import settings
from app.core.exceptions import LLMConfigurationError
from app.services.fallback_llm_client import FallbackLLMClient
from app.services.gemini_client import GeminiClient
from app.services.groq_client import GroqClient
from app.services.llm_provider import build_llm_client, get_llm_client_for_provider


class TestGetLLMClientForProvider:
    def test_gemini_returns_gemini_client(self):
        assert isinstance(get_llm_client_for_provider("gemini"), GeminiClient)

    def test_groq_returns_groq_client(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
        assert isinstance(get_llm_client_for_provider("groq"), GroqClient)

    def test_unknown_provider_raises_configuration_error(self):
        with pytest.raises(LLMConfigurationError):
            get_llm_client_for_provider("not-a-real-provider")


class TestBuildLLMClient:
    def test_no_fallback_configured_returns_bare_primary(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "fallback_llm_provider", None)
        client = build_llm_client()
        assert isinstance(client, GeminiClient)
        assert not isinstance(client, FallbackLLMClient)

    def test_fallback_same_as_primary_returns_bare_primary(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "fallback_llm_provider", "gemini")
        client = build_llm_client()
        assert isinstance(client, GeminiClient)
        assert not isinstance(client, FallbackLLMClient)

    def test_different_fallback_wraps_in_fallback_client(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "fallback_llm_provider", "groq")
        monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
        client = build_llm_client()
        assert isinstance(client, FallbackLLMClient)
        assert isinstance(client._primary, GeminiClient)
        assert isinstance(client._fallback, GroqClient)
