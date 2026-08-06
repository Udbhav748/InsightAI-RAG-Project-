"""Unit tests for hybrid_search.py: score normalization, BM25 indexing,
and the semantic+BM25 fusion logic — no real FAISS index or embedding
model involved (embed_query is monkeypatched; the "semantic" side of
fusion tests is a fake vector_store).
"""

from app.core.config import settings
from app.models.document import RetrievedChunk
from app.services.hybrid_search import BM25Index, _min_max_normalize, hybrid_search


def make_chunk(chunk_id, text="chunk text", score=0.5):
    return RetrievedChunk(chunk_id=chunk_id, document_id="doc-1", text=text, score=score, metadata={})


class TestMinMaxNormalize:
    def test_scales_to_unit_range(self):
        assert _min_max_normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]

    def test_preserves_relative_order(self):
        normalized = _min_max_normalize([3.0, 1.0, 2.0])
        assert normalized[1] < normalized[2] < normalized[0]

    def test_all_equal_positive_scores_normalize_to_one(self):
        assert _min_max_normalize([2.0, 2.0, 2.0]) == [1.0, 1.0, 1.0]

    def test_all_zero_scores_normalize_to_zero(self):
        assert _min_max_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]

    def test_empty_list_returns_empty(self):
        assert _min_max_normalize([]) == []

    def test_single_score_is_a_tie_with_itself(self):
        assert _min_max_normalize([7.0]) == [1.0]


class TestBM25Index:
    def _records(self):
        return [
            {"chunk_id": "c1", "document_id": "d1", "metadata": {"text": "the quick brown fox"}},
            {"chunk_id": "c2", "document_id": "d1", "metadata": {"text": "lazy dog sleeps all day"}},
            {"chunk_id": "c3", "document_id": "d1", "metadata": {"text": "fox and dog are friends"}},
        ]

    def test_search_ranks_by_term_overlap(self):
        index = BM25Index()
        index.rebuild(self._records())

        results = index.search("fox dog", top_k=3)

        assert results[0][0]["chunk_id"] == "c3"  # mentions both terms
        assert {r[0]["chunk_id"] for r in results} == {"c1", "c2", "c3"}

    def test_empty_corpus_returns_no_results(self):
        index = BM25Index()
        index.rebuild([])
        assert index.search("anything", top_k=5) == []

    def test_search_before_any_rebuild_returns_no_results(self):
        index = BM25Index()
        assert index.search("anything", top_k=5) == []

    def test_rebuild_replaces_the_previous_corpus(self):
        index = BM25Index()
        index.rebuild(self._records())
        index.rebuild([{"chunk_id": "z1", "document_id": "d2", "metadata": {"text": "unrelated content"}}])

        results = index.search("fox", top_k=5)

        # The old corpus (c1/c2/c3, one of which matched "fox") is gone —
        # only the new one-doc corpus is searchable, and "fox" doesn't
        # appear in it, so its score is 0 (still returned: BM25Index
        # doesn't filter by score, same as FAISSVectorStore.search() —
        # that's the caller's job).
        assert [r[0]["chunk_id"] for r in results] == ["z1"]
        assert results[0][1] == 0.0


class FakeVectorStore:
    """Exposes exactly the two methods hybrid_search() needs — no real
    FAISS index or BM25 corpus, so the fusion logic can be tested in
    isolation from both."""

    def __init__(self, semantic_results, bm25_results):
        self._semantic_results = semantic_results
        self._bm25_results = bm25_results

    def search(self, query_vector, top_k):
        return self._semantic_results[:top_k]

    def search_bm25(self, query, top_k):
        return self._bm25_results[:top_k]


class TestHybridSearch:
    def test_fuses_and_dedupes_by_chunk_id(self, monkeypatch):
        monkeypatch.setattr("app.services.hybrid_search.embed_query", lambda query: [0.1, 0.2])
        monkeypatch.setattr(settings, "hybrid_semantic_weight", 0.6)

        # c1 appears in both lists (should fuse), c2 only semantic, c3 only bm25.
        store = FakeVectorStore(
            semantic_results=[make_chunk("c1", score=0.9), make_chunk("c2", score=0.5)],
            bm25_results=[make_chunk("c1", score=4.0), make_chunk("c3", score=2.0)],
        )

        results = hybrid_search("query", store, top_k=10)

        assert {chunk.chunk_id for chunk in results} == {"c1", "c2", "c3"}

    def test_fused_score_combines_normalized_scores_with_configured_weight(self, monkeypatch):
        monkeypatch.setattr("app.services.hybrid_search.embed_query", lambda query: [0.1, 0.2])
        monkeypatch.setattr(settings, "hybrid_semantic_weight", 0.6)

        # Two semantic candidates (min-max -> 0.0, 1.0), two bm25 candidates
        # (min-max -> 0.0, 1.0), sharing chunk_id "hi" as the top of both.
        store = FakeVectorStore(
            semantic_results=[make_chunk("hi", score=1.0), make_chunk("lo", score=0.0)],
            bm25_results=[make_chunk("hi", score=10.0), make_chunk("other", score=0.0)],
        )

        results = hybrid_search("query", store, top_k=10)
        by_id = {chunk.chunk_id: chunk.score for chunk in results}

        # "hi": semantic_norm=1.0, bm25_norm=1.0 -> 0.6*1 + 0.4*1 = 1.0
        assert by_id["hi"] == 1.0
        # "lo": semantic_norm=0.0, bm25 absent (0.0) -> 0.0
        assert by_id["lo"] == 0.0
        # "other": semantic absent (0.0), bm25_norm=0.0 -> 0.0
        assert by_id["other"] == 0.0

    def test_returns_top_k_only(self, monkeypatch):
        monkeypatch.setattr("app.services.hybrid_search.embed_query", lambda query: [0.1, 0.2])

        store = FakeVectorStore(
            semantic_results=[make_chunk(f"s{i}", score=float(i)) for i in range(5)],
            bm25_results=[],
        )

        results = hybrid_search("query", store, top_k=2)

        assert len(results) == 2
        # Highest semantic scores (s4, s3) should win after fusion.
        assert {chunk.chunk_id for chunk in results} == {"s4", "s3"}

    def test_result_ordering_is_by_fused_score_descending(self, monkeypatch):
        monkeypatch.setattr("app.services.hybrid_search.embed_query", lambda query: [0.1, 0.2])

        store = FakeVectorStore(
            semantic_results=[make_chunk("low", score=0.1), make_chunk("high", score=0.9)],
            bm25_results=[],
        )

        results = hybrid_search("query", store, top_k=10)

        assert [chunk.chunk_id for chunk in results] == ["high", "low"]
