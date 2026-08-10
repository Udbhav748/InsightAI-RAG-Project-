"""FAISS-backed implementation of the VectorStore interface.

Uses IndexFlatIP (exact inner-product search). Callers are responsible for
passing L2-normalized embeddings (see embedding_service), so that inner
product is equivalent to cosine similarity. Metadata is persisted
separately as JSON, positionally aligned with vector rows in the index
(row i <-> metadata[i]).

Also owns a BM25Index (see hybrid_search.py) alongside the FAISS index —
a second, lexical view over the same chunk texts, rebuilt from self._metadata
every time it changes (create_index/add_embeddings/delete_document/load),
since BM25Okapi has no incremental update API. search_bm25() exposes it.
This BM25 pairing is a FAISSVectorStore-specific capability, not part of
the VectorStore ABC — see hybrid_search.py's module docstring for why.
"""

import json
import logging
import threading
import time
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.core.exceptions import (
    CorruptedVectorStoreError,
    EmbeddingDimensionMismatchError,
    MetadataSyncError,
    VectorStoreNotFoundError,
)
from app.models.document import EmbeddedChunk, RetrievedChunk
from app.services import s3_sync_service
from app.services.hybrid_search import BM25Index
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

_VECTOR_STORE_DIR = Path(__file__).resolve().parents[2] / settings.vector_store_dir_name
DEFAULT_INDEX_PATH = _VECTOR_STORE_DIR / settings.vector_index_filename
DEFAULT_METADATA_PATH = _VECTOR_STORE_DIR / settings.vector_metadata_filename


class FAISSVectorStore(VectorStore):
    def __init__(self, index_path: Path | None = None, metadata_path: Path | None = None):
        self.index_path = index_path or DEFAULT_INDEX_PATH
        self.metadata_path = metadata_path or DEFAULT_METADATA_PATH
        self._index: faiss.Index | None = None
        self._metadata: list[dict] = []
        self._bm25_index = BM25Index()
        # Guards add_embeddings/delete_document/save against two concurrent
        # writers racing (e.g. two /upload requests, or an upload and a
        # delete). threading.Lock rather than asyncio.Lock: FastAPI runs
        # async routes on the event loop but sync `def` routes (like
        # DELETE /documents/{id}) in a worker thread pool, so a lock scoped
        # to one event loop wouldn't actually cover both call paths — this
        # one does, at the cost of briefly blocking whichever thread is
        # waiting, which these already-synchronous, already-fast index/
        # metadata writes make an acceptable trade.
        self._lock = threading.Lock()

    def _record_to_chunk(self, record: dict, score: float) -> RetrievedChunk:
        record_metadata = record["metadata"]
        text = record_metadata.get("text", "")
        metadata = {key: value for key, value in record_metadata.items() if key != "text"}
        return RetrievedChunk(
            chunk_id=record["chunk_id"],
            document_id=record["document_id"],
            text=text,
            score=score,
            metadata=metadata,
        )

    def create_index(self, dimension: int) -> None:
        self._index = faiss.IndexFlatIP(dimension)
        self._metadata = []
        self._bm25_index.rebuild(self._metadata)

    def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        with self._lock:
            if self._index is None:
                raise VectorStoreNotFoundError(
                    "No index to add to. Call create_index() or load() first."
                )
            if not embedded_chunks:
                return

            dimension = self._index.d
            for chunk in embedded_chunks:
                if len(chunk.embedding) != dimension:
                    raise EmbeddingDimensionMismatchError(
                        f"Embedding for chunk {chunk.chunk_id} has dimension "
                        f"{len(chunk.embedding)}, but the index expects {dimension}."
                    )

            start = time.perf_counter()

            vectors = np.array([chunk.embedding for chunk in embedded_chunks], dtype="float32")
            self._index.add(vectors)
            self._metadata.extend(
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "metadata": chunk.metadata,
                }
                for chunk in embedded_chunks
            )

            if self._index.ntotal != len(self._metadata):
                raise MetadataSyncError(
                    f"Vector count ({self._index.ntotal}) and metadata count "
                    f"({len(self._metadata)}) diverged after add_embeddings()."
                )

            self._bm25_index.rebuild(self._metadata)

            processing_duration = time.perf_counter() - start

            logger.info(
                "vectors_added",
                extra={
                    "extra_fields": {
                        "vectors_added": len(embedded_chunks),
                        "total_vectors": self._index.ntotal,
                        "embedding_dimension": dimension,
                        "processing_duration": round(processing_duration, 4),
                    }
                },
            )

    def search(
        self, query_vector: list[float], top_k: int, tenant_id: int | None = None
    ) -> list[RetrievedChunk]:
        if self._index is None:
            raise VectorStoreNotFoundError(
                "No index to search. Call create_index() or load() first."
            )

        dimension = self._index.d
        if len(query_vector) != dimension:
            raise EmbeddingDimensionMismatchError(
                f"Query vector has dimension {len(query_vector)}, but the index "
                f"expects {dimension}."
            )

        if self._index.ntotal == 0 or top_k <= 0:
            return []

        query = np.array([query_vector], dtype="float32")
        # IndexFlatIP is exact brute-force: it scores every vector in the
        # index regardless of k, then returns the top k of those already-
        # computed scores. So when filtering by tenant, fetching *every*
        # score (k=ntotal) costs essentially the same as fetching top_k —
        # it just lets the tenant filter below see the whole ranked list
        # instead of risking top_k being filled with another tenant's
        # chunks before this tenant's actually-best matches are reached.
        k = self._index.ntotal if tenant_id is not None else min(top_k, self._index.ntotal)
        scores, positions = self._index.search(query, k)

        results = []
        for score, position in zip(scores[0], positions[0]):
            if position == -1:
                continue
            record = self._metadata[position]
            if tenant_id is not None and record["metadata"].get("tenant_id") != tenant_id:
                continue
            results.append(self._record_to_chunk(record, float(score)))
            if len(results) >= top_k:
                break

        return results

    def search_bm25(
        self, query: str, top_k: int, tenant_id: int | None = None
    ) -> list[RetrievedChunk]:
        """BM25 lexical search — a FAISSVectorStore-specific capability
        alongside search() (semantic), not part of the VectorStore ABC.
        Used by hybrid_search.hybrid_search() when
        Settings.hybrid_search_enabled. score is BM25's raw score, not a
        0-1 similarity — callers that fuse it with search()'s scores are
        responsible for normalizing first (see hybrid_search.py).

        tenant_id has the same filtering semantics as search()."""
        return [
            self._record_to_chunk(record, score)
            for record, score in self._bm25_index.search(query, top_k, tenant_id=tenant_id)
        ]

    def delete_document(self, document_id: str) -> int:
        with self._lock:
            if self._index is None:
                raise VectorStoreNotFoundError(
                    "No index to delete from. Call create_index() or load() first."
                )

            keep_positions = [
                i for i, record in enumerate(self._metadata) if record["document_id"] != document_id
            ]
            removed_count = len(self._metadata) - len(keep_positions)
            if removed_count == 0:
                return 0

            start = time.perf_counter()
            dimension = self._index.d

            # IndexFlatIP has no native remove-by-id, but it stores raw vectors,
            # so rebuilding from the vectors we want to keep is exact (not an
            # approximation) and cheap at this project's scale.
            if keep_positions:
                all_vectors = self._index.reconstruct_n(0, self._index.ntotal)
                kept_vectors = all_vectors[keep_positions]
            else:
                kept_vectors = np.empty((0, dimension), dtype="float32")

            new_index = faiss.IndexFlatIP(dimension)
            if len(kept_vectors) > 0:
                new_index.add(kept_vectors)

            self._index = new_index
            self._metadata = [self._metadata[i] for i in keep_positions]
            self._bm25_index.rebuild(self._metadata)

            processing_duration = time.perf_counter() - start

            logger.info(
                "document_deleted",
                extra={
                    "extra_fields": {
                        "document_id": document_id,
                        "vectors_removed": removed_count,
                        "total_vectors": self._index.ntotal,
                        "processing_duration": round(processing_duration, 4),
                    }
                },
            )

        return removed_count

    def get_chunks_by_document(
        self, document_id: str, tenant_id: int | None = None
    ) -> list[RetrievedChunk]:
        if self._index is None:
            return []

        # score=1.0 isn't a similarity score — there's no query here, this
        # is a full-document fetch. It just signals "included".
        matches = [
            self._record_to_chunk(record, 1.0)
            for record in self._metadata
            if record["document_id"] == document_id
            and (tenant_id is None or record["metadata"].get("tenant_id") == tenant_id)
        ]

        matches.sort(key=lambda chunk: chunk.metadata.get("chunk_index", 0))
        return matches

    def save(self) -> None:
        with self._lock:
            if self._index is None:
                raise VectorStoreNotFoundError(
                    "No index to save. Call create_index() or load() first."
                )
            if self._index.ntotal != len(self._metadata):
                raise MetadataSyncError(
                    f"Refusing to save: vector count ({self._index.ntotal}) and metadata "
                    f"count ({len(self._metadata)}) are out of sync."
                )

            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self.index_path))
            self.metadata_path.write_text(json.dumps(self._metadata))

        # Outside the lock: network I/O has no reason to hold it, and this
        # covers both of save()'s call sites (upload, delete) automatically.
        s3_sync_service.upload_dir(self.index_path.parent, settings.vector_store_dir_name)

    def load(self) -> None:
        if not self.index_path.is_file():
            raise VectorStoreNotFoundError(f"No index file at {self.index_path}")
        if not self.metadata_path.is_file():
            raise VectorStoreNotFoundError(f"No metadata file at {self.metadata_path}")

        try:
            index = faiss.read_index(str(self.index_path))
        except Exception as exc:
            raise CorruptedVectorStoreError(
                f"Failed to read FAISS index at {self.index_path}: {exc}"
            ) from exc

        try:
            metadata = json.loads(self.metadata_path.read_text())
        except Exception as exc:
            raise CorruptedVectorStoreError(
                f"Failed to read metadata at {self.metadata_path}: {exc}"
            ) from exc

        if index.ntotal != len(metadata):
            raise MetadataSyncError(
                f"Loaded index has {index.ntotal} vectors but metadata has "
                f"{len(metadata)} entries."
            )

        self._index = index
        self._metadata = metadata
        self._bm25_index.rebuild(self._metadata)

    def total_vectors(self) -> int:
        return self._index.ntotal if self._index is not None else 0
