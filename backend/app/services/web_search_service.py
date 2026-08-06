"""Web search fallback tool: fetches top web results via DuckDuckGo when
document retrieval doesn't confidently answer a query (see
rag_service.ChatService's corrective RAG loop).

No API key required — duckduckgo-search queries DDG's public search
directly. Isolated wrapper: nothing else in the codebase imports
duckduckgo_search directly, the same pattern gemini_client.py/
groq_client.py use to isolate their own SDKs.

Note: DuckDuckGo's unofficial search endpoints are known to rate-limit or
silently return zero results from data-center/cloud IPs (bot detection),
even with no error raised. search_web() doesn't try to distinguish that
from "genuinely no results" — callers already treat an empty list as "no
web context available" either way, so there's nothing more useful to do
with the distinction than log it.
"""

import logging
import time

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from app.core.config import settings
from app.core.exceptions import WebSearchError
from app.models.document import WebSearchResult

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int | None = None) -> list[WebSearchResult]:
    """Fetch top web results for query.

    Raises WebSearchError on failure — callers (ChatService) are expected
    to catch it and degrade gracefully (treat it like zero results) rather
    than fail the whole chat request over a best-effort fallback tool.
    """
    resolved_max_results = (
        max_results if max_results is not None else settings.web_search_result_count
    )

    start = time.perf_counter()
    try:
        with DDGS(timeout=settings.web_search_timeout_seconds) as ddgs:
            raw_results = list(ddgs.text(query, max_results=resolved_max_results))
    except DuckDuckGoSearchException as exc:
        raise WebSearchError(f"Web search failed: {exc}") from exc
    except Exception as exc:
        raise WebSearchError(f"Unexpected error during web search: {exc}") from exc

    processing_duration = time.perf_counter() - start

    results = [
        WebSearchResult(
            title=raw.get("title", ""),
            url=raw.get("href", ""),
            snippet=raw.get("body", ""),
        )
        for raw in raw_results
    ]

    logger.info(
        "web_search_completed",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "result_count": len(results),
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return results
