"""Retrieves the most relevant chunks for a natural-language query.

The baseline path depends only on the VectorStore interface and
embedding_service.embed_query. Two opt-in enhancements layer on top,
each config-gated and defaulting to False so the baseline is unchanged
unless explicitly enabled (see docs/OPERATIONS.md's "Retrieval ablation"
for how to A/B them against each other):

- Settings.hybrid_search_enabled — fuse FAISS semantic search with a BM25
  lexical index (hybrid_search.py). Requires a FAISSVectorStore
  specifically (checked via isinstance, not assumed) since BM25 is a
  FAISSVectorStore-specific capability, not part of the VectorStore ABC.
- Settings.reranking_enabled — re-score a wider candidate pool with a
  cross-encoder (reranking_service.py) before narrowing to top_k.
"""

import logging
import time

from app.core.config import settings
from app.core.exceptions import RerankingError
from app.models.document import RetrievedChunk
from app.services.embedding_service import embed_query
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.hybrid_search import hybrid_search
from app.services.reranking_service import rerank
from app.services.tool_registry import track_tool
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


@track_tool("retrieval")
def retrieve(
    query: str,
    vector_store: VectorStore,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Retrieve (optionally hybrid + reranked), then drop results below
    min_score.

    top_k and min_score default to Settings when not given explicitly.
    """
    resolved_top_k = top_k if top_k is not None else settings.retrieval_top_k
    resolved_min_score = min_score if min_score is not None else settings.retrieval_min_score

    start = time.perf_counter()

    # If reranking will run afterward, fetch a wider candidate pool for it
    # to actually have something to re-order; otherwise fetch exactly what
    # the caller asked for. Either way, this is the "top-k" handed to
    # whichever retrieval path runs below — hybrid_search separately always
    # pulls its own (typically wider) candidate_k from each retriever
    # before fusing down to this number.
    fetch_k = settings.retrieval_candidate_k if settings.reranking_enabled else resolved_top_k

    if settings.hybrid_search_enabled and isinstance(vector_store, FAISSVectorStore):
        results = hybrid_search(query, vector_store, top_k=fetch_k)
    else:
        query_vector = embed_query(query)
        results = vector_store.search(query_vector, fetch_k)

    reranked = False
    if settings.reranking_enabled:
        try:
            results = rerank(query, results, top_k=resolved_top_k)
            reranked = True
        except RerankingError as exc:
            logger.warning("reranking_failed", extra={"extra_fields": {"error": str(exc)}})
            results = results[:resolved_top_k]

    # min_score is calibrated against raw cosine similarity. rerank() keeps
    # each chunk's pre-rerank score (see its docstring) since cross-encoder
    # scores aren't on that same scale either — but that means when hybrid
    # search is also on, this filter would compare min_score against a
    # per-query min-max-normalized fused score, not cosine similarity: a
    # different scale the threshold was never calibrated for. Once
    # reranking has actually run, its own top_k selection is the intended
    # relevance gate, so skip re-filtering by that incompatible scale.
    if reranked:
        filtered = results
    else:
        filtered = [chunk for chunk in results if chunk.score >= resolved_min_score]

    processing_duration = time.perf_counter() - start

    logger.info(
        "retrieval_completed",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "top_k": resolved_top_k,
                "min_score": resolved_min_score,
                "hybrid_search_enabled": settings.hybrid_search_enabled,
                "reranking_enabled": settings.reranking_enabled,
                "results_before_threshold": len(results),
                "results_returned": len(filtered),
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return filtered
