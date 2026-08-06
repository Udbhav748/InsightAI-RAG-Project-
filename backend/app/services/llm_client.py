"""Abstract interface for a language model client.

The rest of the application should depend on this interface, not on any
specific provider (e.g. Gemini), so the backing LLM can be swapped without
touching calling code.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a text completion for the given prompt."""

    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Generate a text completion, yielding it in pieces as it's
        produced. Default implementation: no real streaming, just yields
        generate()'s full result once — this is what FallbackLLMClient
        inherits (streaming would mean re-streaming from the fallback
        provider mid-response if the primary failed partway, which isn't
        a sensible thing to do to a client that's already rendered
        partial output) and what any client/test that hasn't implemented
        real streaming falls back to. Concrete clients that support it
        (GeminiClient, GroqClient) override this with real streaming.
        """
        yield self.generate(prompt)
