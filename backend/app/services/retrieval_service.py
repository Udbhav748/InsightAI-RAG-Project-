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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from app.core.config import settings
from app.core.exceptions import RerankingError
from app.core.metrics import get_metrics
from app.models.document import RetrievedChunk
from app.services.embedding_service import embed_query
from app.services.faiss_vector_store import FAISSVectorStore
from app.services.hybrid_search import hybrid_search
from app.services.prompt_injection_service import detect_possible_injection
from app.services.reranking_service import rerank
from app.services.tool_registry import track_tool
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _search_with_timeout(
    query: str,
    vector_store: VectorStore,
    fetch_k: int,
    resolved_top_k: int,
    tenant_id: int | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Run the retrieval search block (hybrid or plain semantic) under a
    configurable wall-clock timeout.

    The search + optional reranking is CPU-bound in-process work, so the
    only portable way to bound it is a worker thread whose result is
    waited on with a timeout. If the timeout fires, the search thread keeps
    running (Python threads can't be killed) but this request degrades to
    an empty result list instead of hanging — which flows through the
    existing retrieval-grading path as "insufficient" and, if enabled, the
    web-search fallback, so a pathological index never wedges a request.

    With settings.retrieval_timeout_seconds == 0 (the default), the search
    runs inline with no thread overhead at all — behavior unchanged.
    """
    def _do_search() -> list[RetrievedChunk]:
        if settings.hybrid_search_enabled and isinstance(vector_store, FAISSVectorStore):
            if document_ids is not None:
                return hybrid_search(
                    query, vector_store, top_k=fetch_k, tenant_id=tenant_id, document_ids=document_ids
                )
            return hybrid_search(query, vector_store, top_k=fetch_k, tenant_id=tenant_id)
        query_vector = embed_query(query)
        # document_ids filtering is only available at the FAISS search
        # layer; for any other VectorStore implementation the caller's
        # exact post-filter in retrieve() is the enforcement point.
        if isinstance(vector_store, FAISSVectorStore):
            if document_ids is not None:
                return vector_store.search(
                    query_vector, fetch_k, tenant_id=tenant_id, document_ids=document_ids
                )
            return vector_store.search(query_vector, fetch_k, tenant_id=tenant_id)
        return vector_store.search(query_vector, fetch_k, tenant_id=tenant_id)

    timeout = settings.retrieval_timeout_seconds
    if timeout <= 0:
        return _do_search()

    # No `with` block here: ThreadPoolExecutor.__exit__ calls
    # shutdown(wait=True), which would block until the hung worker thread
    # finishes — exactly what the timeout exists to avoid. shutdown
    # (wait=False) lets the orphaned thread drain in the background while
    # this request already moved on.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_do_search)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            get_metrics().inc_counter("retrieval_timeouts_total")
            logger.warning(
                "retrieval_timed_out",
                extra={"extra_fields": {"timeout_seconds": timeout, "top_k": resolved_top_k}},
            )
            return []
    finally:
        executor.shutdown(wait=False)


@track_tool("retrieval")
def retrieve(
    query: str,
    vector_store: VectorStore,
    top_k: int | None = None,
    min_score: float | None = None,
    tenant_id: int | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve (optionally hybrid + reranked), then drop results below
    min_score.

    top_k and min_score default to Settings when not given explicitly.
    tenant_id (not part of RetrievalInput's user-facing schema — it's
    system-injected auth context, same treatment as the vector_store
    param) restricts results to that tenant's own chunks; see
    FAISSVectorStore.search's docstring for exact filtering semantics.
    document_ids restricts results to chunks belonging to those
    documents (Agent 3.1 "chat with a collection") — applied as an exact
    post-filter so it composes with any VectorStore implementation and
    any retrieval path (semantic, hybrid, reranked).
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

    results = _search_with_timeout(
        query, vector_store, fetch_k, resolved_top_k, tenant_id=tenant_id, document_ids=document_ids
    )

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

    if document_ids:
        allowed = set(document_ids)
        filtered = [chunk for chunk in filtered if chunk.document_id in allowed]

    if document_ids:
        log_extra = {"document_id_count": len(allowed), "results_after_doc_filter": len(filtered)}
    else:
        log_extra = {}

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
            | log_extra
        },
    )

    # Detection only, same flag-and-continue policy as the query-side check
    # in rag_service.ChatService._route — text embedded in an uploaded
    # document reaching the LLM via retrieval is failure mode #4 in
    # docs/DESIGN_REVIEW.md, and this is what makes an attempt visible in
    # production logs instead of only the offline eval harness.
    flagged = [
        {"chunk_id": chunk.chunk_id, "document_id": chunk.document_id, "categories": categories}
        for chunk in filtered
        if (categories := detect_possible_injection(chunk.text))
    ]
    if flagged:
        logger.warning(
            "possible_injection_detected",
            extra={"extra_fields": {"source": "chunk", "flagged_chunks": flagged}},
        )

    return filtered
