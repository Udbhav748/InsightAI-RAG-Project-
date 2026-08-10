"""Hybrid search: fuses FAISS semantic search with BM25 lexical search.

BM25Index wraps rank_bm25.BM25Okapi and is owned by FAISSVectorStore (see
faiss_vector_store.py), rebuilt from scratch on every
add_embeddings/delete_document/load/create_index — BM25Okapi has no
incremental update API, so a full rebuild is the only option, and this
project's scale makes that cheap enough not to matter.

This is a FAISSVectorStore-specific capability, not part of the portable
VectorStore interface (app/services/vector_store.py): swapping in a
different VectorStore backend later would need its own BM25 (or
equivalent) if hybrid search is still wanted, since lexical indexing over
an arbitrary backend isn't something the abstract interface promises.
retrieval_service.py checks for it explicitly (isinstance) rather than
assuming every VectorStore has it.
"""

import logging
import re
import time

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.models.document import RetrievedChunk
from app.services.embedding_service import embed_query

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Lexical (BM25) index over a corpus of FAISSVectorStore metadata
    records. Not thread-safe against concurrent rebuild + search — the
    same caveat FAISSVectorStore itself already has around concurrent
    writes (see docs/ARCHITECTURE.md)."""

    def __init__(self):
        self._bm25: BM25Okapi | None = None
        self._records: list[dict] = []

    def rebuild(self, records: list[dict]) -> None:
        """records is FAISSVectorStore._metadata — each a dict with
        chunk_id, document_id, and metadata (which carries the chunk
        text under metadata["text"]). Rebuilds from scratch every time;
        BM25Okapi has no incremental add."""
        self._records = records
        if not records:
            self._bm25 = None
            return

        corpus = [_tokenize(record["metadata"].get("text", "")) for record in records]
        self._bm25 = BM25Okapi(corpus)

    def search(
        self, query: str, top_k: int, tenant_id: int | None = None
    ) -> list[tuple[dict, float]]:
        """Return up to top_k (record, score) pairs, highest score first.
        score is BM25Okapi's raw score: unbounded above, exactly 0.0 for a
        document with no query-term overlap at all.

        tenant_id, when given, restricts candidates to records tagged with
        that tenant (see FAISSVectorStore.search's docstring for the same
        semantics) — applied before ranking, not after, so a wrong-tenant
        record can never crowd out a same-tenant one within top_k."""
        if self._bm25 is None or top_k <= 0:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        candidate_positions = range(len(scores))
        if tenant_id is not None:
            candidate_positions = [
                i for i in candidate_positions if self._records[i]["metadata"].get("tenant_id") == tenant_id
            ]
        ranked_positions = sorted(candidate_positions, key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self._records[i], float(scores[i])) for i in ranked_positions]


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Scale to [0, 1]. If every score is identical — including the
    degenerate empty-list case — there's no discriminative signal to
    preserve by dividing by a zero range: returns 1.0 for a positive tie
    (every candidate is equally "best") or 0.0 for an all-zero tie (BM25's
    "no lexical overlap at all" case)."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0 if hi > 0 else 0.0 for _ in scores]
    return [(score - lo) / (hi - lo) for score in scores]


def hybrid_search(
    query: str,
    vector_store,
    top_k: int,
    candidate_k: int | None = None,
    tenant_id: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse FAISS semantic search with BM25 lexical search.

    vector_store must be a FAISSVectorStore (or anything exposing the same
    .search()/.search_bm25() pair) — see the module docstring on why this
    isn't typed against the VectorStore ABC.

    Pulls candidate_k results from each retriever (Settings.retrieval_candidate_k
    by default), min-max normalizes each set's scores independently, fuses
    as Settings.hybrid_semantic_weight * semantic + (1 - that) * bm25 (0
    contribution from whichever side didn't return a given chunk), dedupes
    by chunk_id, and returns the top_k fused results. The returned
    RetrievedChunk.score is the fused score (roughly 0-1, the same rough
    scale as cosine similarity) — not either input score directly, so it
    stays meaningful to retrieval_min_score filtering and
    ChatService._grade_retrieval downstream.

    tenant_id is passed through to both retrievers unchanged — see
    FAISSVectorStore.search's docstring for its filtering semantics.
    """
    resolved_candidate_k = candidate_k if candidate_k is not None else settings.retrieval_candidate_k
    semantic_weight = settings.hybrid_semantic_weight
    bm25_weight = 1.0 - semantic_weight

    start = time.perf_counter()

    query_vector = embed_query(query)
    semantic_results = vector_store.search(query_vector, resolved_candidate_k, tenant_id=tenant_id)
    bm25_results = vector_store.search_bm25(query, resolved_candidate_k, tenant_id=tenant_id)

    semantic_norm = _min_max_normalize([chunk.score for chunk in semantic_results])
    bm25_norm = _min_max_normalize([chunk.score for chunk in bm25_results])

    fused: dict[str, dict] = {}
    for chunk, norm_score in zip(semantic_results, semantic_norm):
        fused[chunk.chunk_id] = {"chunk": chunk, "semantic": norm_score, "bm25": 0.0}
    for chunk, norm_score in zip(bm25_results, bm25_norm):
        entry = fused.get(chunk.chunk_id)
        if entry is None:
            fused[chunk.chunk_id] = {"chunk": chunk, "semantic": 0.0, "bm25": norm_score}
        else:
            entry["bm25"] = norm_score

    scored = [
        (entry["chunk"], semantic_weight * entry["semantic"] + bm25_weight * entry["bm25"])
        for entry in fused.values()
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    results = [chunk.model_copy(update={"score": score}) for chunk, score in scored[:top_k]]

    processing_duration = time.perf_counter() - start
    logger.info(
        "hybrid_search_completed",
        extra={
            "extra_fields": {
                "query_length": len(query),
                "candidate_k": resolved_candidate_k,
                "top_k": top_k,
                "semantic_candidate_count": len(semantic_results),
                "bm25_candidate_count": len(bm25_results),
                "fused_result_count": len(results),
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return results
