"""Retrieves the most relevant chunks for a natural-language query.

Depends only on the VectorStore interface and embedding_service.embed_query,
so it never touches a specific vector store backend, an API route, prompt
generation, or Gemini.
"""

import logging
import time

from app.core.config import settings
from app.models.document import RetrievedChunk
from app.services.embedding_service import embed_query
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    vector_store: VectorStore,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Embed query, search vector_store, and drop results below min_score.

    top_k and min_score default to Settings when not given explicitly.
    """
    resolved_top_k = top_k if top_k is not None else settings.retrieval_top_k
    resolved_min_score = min_score if min_score is not None else settings.retrieval_min_score

    start = time.perf_counter()

    query_vector = embed_query(query)
    results = vector_store.search(query_vector, resolved_top_k)
    filtered = [chunk for chunk in results if chunk.score >= resolved_min_score]

    processing_duration = time.perf_counter() - start

    logger.info(
        "retrieval_completed",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "top_k": resolved_top_k,
                "min_score": resolved_min_score,
                "results_before_threshold": len(results),
                "results_returned": len(filtered),
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return filtered
