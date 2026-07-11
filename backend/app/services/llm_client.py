"""Abstract interface for a language model client.

The rest of the application should depend on this interface, not on any
specific provider (e.g. Gemini), so the backing LLM can be swapped without
touching calling code.
"""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a text completion for the given prompt."""
