"""Unit tests for GroqClient's construction and error-mapping.

Mirrors the style of the existing gemini tests: never calls the real
Groq API. groq.Groq() is constructed for real (it just builds an SDK
client object, no network call), then self._client.chat.completions.create
is monkeypatched per test.
"""

import groq
import pytest

from app.core.config import settings
from app.core.exceptions import (
    LLMAPIError,
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMTimeoutError,
)
from app.services.groq_client import GroqClient


class _FakeUsage:
    def __init__(self, prompt_tokens=10, completion_tokens=5):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content, usage=None):
        self.choices = [_FakeChoice(content)]
        self.usage = usage if usage is not None else _FakeUsage()


def _client(monkeypatch, groq_api_key="test-groq-key"):
    monkeypatch.setattr(settings, "groq_api_key", groq_api_key)
    return GroqClient()


class TestGroqClientConfiguration:
    def test_missing_api_key_raises_configuration_error(self, monkeypatch):
        monkeypatch.setattr(settings, "groq_api_key", "")
        with pytest.raises(LLMConfigurationError):
            GroqClient()


class TestGroqClientGenerate:
    def test_happy_path_returns_text_and_logs_usage(self, monkeypatch):
        client = _client(monkeypatch)
        monkeypatch.setattr(
            client._client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse("A grounded answer."),
        )
        assert client.generate("some prompt") == "A grounded answer."

    def test_empty_response_raises_llm_empty_response_error(self, monkeypatch):
        client = _client(monkeypatch)
        monkeypatch.setattr(
            client._client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse("   "),
        )
        with pytest.raises(LLMEmptyResponseError):
            client.generate("some prompt")

    def test_timeout_error_maps_to_llm_timeout_error(self, monkeypatch):
        client = _client(monkeypatch)

        def _raise_timeout(**kwargs):
            raise groq.APITimeoutError(request=None)

        monkeypatch.setattr(client._client.chat.completions, "create", _raise_timeout)
        with pytest.raises(LLMTimeoutError):
            client.generate("some prompt")

    def test_api_error_maps_to_llm_api_error(self, monkeypatch):
        client = _client(monkeypatch)

        def _raise_api_error(**kwargs):
            raise groq.APIConnectionError(request=None)

        monkeypatch.setattr(client._client.chat.completions, "create", _raise_api_error)
        with pytest.raises(LLMAPIError):
            client.generate("some prompt")

    def test_unexpected_error_maps_to_llm_api_error(self, monkeypatch):
        client = _client(monkeypatch)

        def _raise_value_error(**kwargs):
            raise ValueError("something unrelated broke")

        monkeypatch.setattr(client._client.chat.completions, "create", _raise_value_error)
        with pytest.raises(LLMAPIError):
            client.generate("some prompt")


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeStreamChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeStreamChunk:
    def __init__(self, content):
        self.choices = [_FakeStreamChoice(content)]


class TestGroqClientGenerateStream:
    def test_happy_path_yields_pieces_in_order(self, monkeypatch):
        client = _client(monkeypatch)
        chunks = [_FakeStreamChunk("Hello "), _FakeStreamChunk("grounded "), _FakeStreamChunk("world.")]
        monkeypatch.setattr(client._client.chat.completions, "create", lambda **kwargs: iter(chunks))

        pieces = list(client.generate_stream("some prompt"))

        assert pieces == ["Hello ", "grounded ", "world."]

    def test_empty_stream_raises_llm_empty_response_error(self, monkeypatch):
        client = _client(monkeypatch)
        monkeypatch.setattr(
            client._client.chat.completions, "create", lambda **kwargs: iter([_FakeStreamChunk(None)])
        )

        with pytest.raises(LLMEmptyResponseError):
            list(client.generate_stream("some prompt"))

    def test_timeout_during_iteration_raises_llm_timeout_error(self, monkeypatch):
        client = _client(monkeypatch)

        def _raising_stream(**kwargs):
            def _gen():
                yield _FakeStreamChunk("partial ")
                raise groq.APITimeoutError(request=None)

            return _gen()

        monkeypatch.setattr(client._client.chat.completions, "create", _raising_stream)

        with pytest.raises(LLMTimeoutError):
            list(client.generate_stream("some prompt"))

    def test_api_error_during_iteration_raises_llm_api_error(self, monkeypatch):
        client = _client(monkeypatch)

        def _raising_stream(**kwargs):
            def _gen():
                yield _FakeStreamChunk("partial ")
                raise groq.APIConnectionError(request=None)

            return _gen()

        monkeypatch.setattr(client._client.chat.completions, "create", _raising_stream)

        with pytest.raises(LLMAPIError):
            list(client.generate_stream("some prompt"))
