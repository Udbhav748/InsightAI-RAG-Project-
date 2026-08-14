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

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.exceptions import ClipServiceError
from app.models.document import RetrievedChunk
from app.services import clip_client
from app.services.embedding_service import embed_query

if TYPE_CHECKING:
    from app.services.faiss_vector_store import FAISSVectorStore
    from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Lexical (BM25) index over a corpus of FAISSVectorStore metadata
    records. Not thread-safe against concurrent rebuild + search — the
    same caveat FAISSVectorStore itself already has around concurrent
    writes (see docs/ARCHITECTURE.md)."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._records: list[dict[str, Any]] = []

    def rebuild(self, records: list[dict[str, Any]]) -> None:
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
        self,
        query: str,
        top_k: int,
        tenant_id: int | None = None,
        document_ids: list[str] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Return up to top_k (record, score) pairs, highest score first.
        score is BM25Okapi's raw score: unbounded above, exactly 0.0 for a
        document with no query-term overlap at all.

        tenant_id, when given, restricts candidates to records tagged with
        that tenant (see FAISSVectorStore.search's docstring for the same
        semantics) — applied before ranking, not after, so a wrong-tenant
        record can never crowd out a same-tenant one within top_k.
        document_ids, when given, restricts candidates to records whose
        document_id is in the list (Agent 3.1 collection-scoped chat)."""
        if self._bm25 is None or top_k <= 0:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        candidate_positions: list[int] = list(range(len(scores)))
        if tenant_id is not None:
            candidate_positions = [
                i
                for i in candidate_positions
                if self._records[i]["metadata"].get("tenant_id") == tenant_id
            ]
        if document_ids is not None:
            allowed = set(document_ids)
            candidate_positions = [
                i for i in candidate_positions if self._records[i]["document_id"] in allowed
            ]
        ranked_positions = sorted(candidate_positions, key=lambda i: scores[i], reverse=True)[
            :top_k
        ]
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
    vector_store: FAISSVectorStore,
    top_k: int,
    candidate_k: int | None = None,
    tenant_id: int | None = None,
    document_ids: list[str] | None = None,
    image_vector_store: VectorStore | None = None,
) -> list[RetrievedChunk]:
    """Fuse FAISS semantic search with BM25 lexical search, and (when CLIP
    cross-modal retrieval is enabled) a third CLIP image-similarity signal.

    vector_store must be a FAISSVectorStore (or anything exposing the same
    .search()/.search_bm25() pair) — see the module docstring on why this
    isn't typed against the VectorStore ABC.

    Pulls candidate_k results from each retriever (Settings.retrieval_candidate_k
    by default), min-max normalizes each set's scores independently, fuses
    as a weighted sum (0 contribution from whichever side didn't return a
    given chunk), dedupes by chunk_id, and returns the top_k fused results.
    The returned RetrievedChunk.score is the fused score (roughly 0-1, the
    same rough scale as cosine similarity) — not any input score directly,
    so it stays meaningful to retrieval_min_score filtering and
    ChatService._grade_retrieval downstream.

    Two-signal fusion (CLIP off / image_vector_store absent): score =
    Settings.hybrid_semantic_weight * semantic + (1 - that) * bm25.

    Three-signal fusion (Settings.clip_embedding_enabled and
    image_vector_store given): the query is embedded *in CLIP space*
    (embed_text via clip_client), run against the image store, and fused as
    score = w_clip * clip + (1 - w_clip) * (w_sem * semantic + (1 - w_sem)
    * bm25), where w_clip = Settings.hybrid_clip_weight and w_sem =
    Settings.hybrid_semantic_weight. What comes back from the image side
    are image-derived chunks (source="clip_image", text = the figure's
    caption or a placeholder) — so a query that matches an image purely by
    visual semantics can surface that figure's content even when no text
    chunk overlaps lexically. clip_weight=0 or an unreachable CLIP service
    reproduces the two-signal behavior exactly (degrade, not fail).

    tenant_id is passed through to all retrievers unchanged — see
    FAISSVectorStore.search's docstring for its filtering semantics.
    """
    resolved_candidate_k = (
        candidate_k if candidate_k is not None else settings.retrieval_candidate_k
    )
    semantic_weight = settings.hybrid_semantic_weight

    start = time.perf_counter()

    query_vector = embed_query(query)
    search_kwargs = {}
    if document_ids is not None:
        search_kwargs["document_ids"] = document_ids
    semantic_results = vector_store.search(
        query_vector, resolved_candidate_k, tenant_id=tenant_id, **search_kwargs
    )
    bm25_results = vector_store.search_bm25(
        query, resolved_candidate_k, tenant_id=tenant_id, **search_kwargs
    )

    # CLIP cross-modal signal (Phase 4) — opt-in, degrade-don't-fail.
    clip_weight = 0.0
    clip_results: list[RetrievedChunk] = []
    if settings.clip_embedding_enabled and image_vector_store is not None:
        clip_weight = settings.hybrid_clip_weight
        try:
            clip_query = clip_client.embed_text(query)
            clip_results = image_vector_store.search(
                clip_query.embedding, resolved_candidate_k, tenant_id=tenant_id, **search_kwargs
            )
        except ClipServiceError as exc:
            logger.warning(
                "clip_query_degraded",
                extra={"extra_fields": {"error": str(exc), "query_length": len(query)}},
            )
            clip_results = []

    semantic_norm = _min_max_normalize([chunk.score for chunk in semantic_results])
    bm25_norm = _min_max_normalize([chunk.score for chunk in bm25_results])
    clip_norm = _min_max_normalize([chunk.score for chunk in clip_results])

    fused: dict[str, dict[str, Any]] = {}
    for chunk, norm_score in zip(semantic_results, semantic_norm, strict=False):
        fused[chunk.chunk_id] = {
            "chunk": chunk,
            "semantic": norm_score,
            "bm25": 0.0,
            "clip": 0.0,
        }
    for chunk, norm_score in zip(bm25_results, bm25_norm, strict=False):
        entry = fused.get(chunk.chunk_id)
        if entry is None:
            fused[chunk.chunk_id] = {
                "chunk": chunk,
                "semantic": 0.0,
                "bm25": norm_score,
                "clip": 0.0,
            }
        else:
            entry["bm25"] = norm_score
    for chunk, norm_score in zip(clip_results, clip_norm, strict=False):
        entry = fused.get(chunk.chunk_id)
        if entry is None:
            fused[chunk.chunk_id] = {
                "chunk": chunk,
                "semantic": 0.0,
                "bm25": 0.0,
                "clip": norm_score,
            }
        else:
            entry["clip"] = norm_score

    def _blend(entry: dict[str, Any]) -> float:
        text_blend: float = (
            semantic_weight * entry["semantic"] + (1.0 - semantic_weight) * entry["bm25"]
        )
        if clip_weight > 0.0:
            # Scale the text blend down so three-way weights sum to 1.
            return float(clip_weight * entry["clip"] + (1.0 - clip_weight) * text_blend)
        return text_blend

    scored = [(entry["chunk"], _blend(entry)) for entry in fused.values()]
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
                "clip_candidate_count": len(clip_results),
                "clip_weight": clip_weight,
                "fused_result_count": len(results),
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return results
