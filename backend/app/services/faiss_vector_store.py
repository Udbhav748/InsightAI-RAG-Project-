"""FAISS-backed implementation of the VectorStore interface.

Uses IndexFlatIP (exact inner-product search). Callers are responsible for
passing L2-normalized embeddings (see embedding_service), so that inner
product is equivalent to cosine similarity. Metadata is persisted
separately as JSON, positionally aligned with vector rows in the index
(row i <-> metadata[i]).
"""

import json
import logging
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

    def create_index(self, dimension: int) -> None:
        self._index = faiss.IndexFlatIP(dimension)
        self._metadata = []

    def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> None:
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

    def search(self, query_vector: list[float], top_k: int) -> list[RetrievedChunk]:
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
        k = min(top_k, self._index.ntotal)
        scores, positions = self._index.search(query, k)

        results = []
        for score, position in zip(scores[0], positions[0]):
            if position == -1:
                continue

            record = self._metadata[position]
            record_metadata = record["metadata"]
            text = record_metadata.get("text", "")
            metadata = {key: value for key, value in record_metadata.items() if key != "text"}

            results.append(
                RetrievedChunk(
                    chunk_id=record["chunk_id"],
                    document_id=record["document_id"],
                    text=text,
                    score=float(score),
                    metadata=metadata,
                )
            )

        return results

    def delete_document(self, document_id: str) -> int:
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

    def save(self) -> None:
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

    def total_vectors(self) -> int:
        return self._index.ntotal if self._index is not None else 0
