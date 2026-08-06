"""Picks and wires the LLMClient implementation(s) named in Settings.

query.py's get_llm_client() calls build_llm_client() rather than
constructing GeminiClient/GroqClient itself, so the provider choice and
optional fallback wiring live in one place instead of being duplicated
wherever an LLMClient is needed.
"""

from app.core.config import settings
from app.core.exceptions import LLMConfigurationError
from app.services.fallback_llm_client import FallbackLLMClient
from app.services.gemini_client import GeminiClient
from app.services.groq_client import GroqClient
from app.services.llm_client import LLMClient

_PROVIDERS = {
    "gemini": GeminiClient,
    "groq": GroqClient,
}


def get_llm_client_for_provider(provider: str) -> LLMClient:
    """Construct the LLMClient for a given provider name.

    Raises LLMConfigurationError for an unrecognized provider name — the
    same exception each concrete client already raises for a missing API
    key, so callers only need to handle one error type either way.
    """
    provider_cls = _PROVIDERS.get(provider)
    if provider_cls is None:
        raise LLMConfigurationError(
            f"Unknown llm_provider '{provider}'. Expected one of: "
            f"{', '.join(sorted(_PROVIDERS))}."
        )
    return provider_cls()


def build_llm_client() -> LLMClient:
    """Build the primary LLMClient from Settings, wrapped in a fallback
    provider if Settings.fallback_llm_provider is configured and differs
    from the primary.
    """
    primary = get_llm_client_for_provider(settings.llm_provider)

    if not settings.fallback_llm_provider:
        return primary
    if settings.fallback_llm_provider == settings.llm_provider:
        return primary

    fallback = get_llm_client_for_provider(settings.fallback_llm_provider)
    return FallbackLLMClient(
        primary=primary,
        primary_name=settings.llm_provider,
        fallback=fallback,
        fallback_name=settings.fallback_llm_provider,
    )
