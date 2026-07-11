"""Generates embeddings for DocumentChunks using Sentence Transformers.

Independent of FAISS, retrieval, and Gemini: this service only turns chunk
text into embedding vectors.
"""

import logging
import time
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.exceptions import EmbeddingGenerationError, EmbeddingModelLoadError
from app.models.document import DocumentChunk, EmbeddedChunk

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it on every subsequent call.

    lru_cache serializes concurrent cache misses (CPython locks around the
    cache), so concurrent first calls block on one load instead of racing
    to load the model independently. A failed load isn't cached, so the
    next call retries rather than staying permanently broken.
    """
    try:
        return SentenceTransformer(settings.embedding_model_name)
    except Exception as exc:
        raise EmbeddingModelLoadError(
            f"Failed to load embedding model '{settings.embedding_model_name}': {exc}"
        ) from exc


def embed_query(query: str) -> list[float]:
    """Embed a single query string, using the same model and normalization
    as generate_embeddings, so query and chunk vectors share one space."""
    model = get_embedding_model()

    try:
        vector = model.encode(query, normalize_embeddings=True)
    except Exception as exc:
        raise EmbeddingGenerationError(f"Failed to generate embedding for query: {exc}") from exc

    return vector.tolist()


def generate_embeddings(chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
    """Generate one embedding per chunk, preserving chunk_id, document_id, and metadata."""
    if not chunks:
        return []

    model = get_embedding_model()
    document_id = chunks[0].document_id
    start = time.perf_counter()

    try:
        vectors = model.encode(
            [chunk.text for chunk in chunks],
            normalize_embeddings=True,
        )
    except Exception as exc:
        raise EmbeddingGenerationError(
            f"Failed to generate embeddings for document {document_id}: {exc}"
        ) from exc

    embedded_chunks = [
        EmbeddedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            embedding=vector.tolist(),
            # Chunk text rides along in metadata so the vector store can
            # persist and later return it, without adding a field to
            # EmbeddedChunk itself.
            metadata={**chunk.metadata, "text": chunk.text},
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    processing_duration = time.perf_counter() - start
    embedding_dimension = len(embedded_chunks[0].embedding)

    logger.info(
        "embeddings_generated",
        extra={
            "extra_fields": {
                "document_id": document_id,
                "embedding_model": settings.embedding_model_name,
                "total_chunks": len(chunks),
                "embedding_dimension": embedding_dimension,
                "processing_duration": round(processing_duration, 4),
            }
        },
    )

    return embedded_chunks
