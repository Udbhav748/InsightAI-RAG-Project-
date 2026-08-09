"""Generates embeddings for DocumentChunks using Sentence Transformers.

Independent of FAISS, retrieval, and Gemini: this service only turns chunk
text into embedding vectors.
"""

import logging
import time
from functools import lru_cache

from sentence_transformers import SentenceTransformer
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import (
    EmbeddingGenerationError,
    EmbeddingModelLoadError,
    LLMAPIError,
    LLMTimeoutError,
)
from app.models.document import DocumentChunk, EmbeddedChunk

logger = logging.getLogger(__name__)


def _log_retry(retry_state) -> None:
    logger.warning(
        "embed_query_retrying",
        extra={
            "extra_fields": {
                "attempt": retry_state.attempt_number,
                "exception": str(retry_state.outcome.exception()),
            }
        },
    )


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



# Query embeddings are a pure function of (normalized query text, model
# weights) -- the model is loaded once per process (get_embedding_model's
# own lru_cache) and never changes mid-process, so this can never go
# stale the way caching retrieval results or generated answers would
# (both depend on the vector store's mutable state -- documents can be
# uploaded/deleted between requests, which the embedding step doesn't
# care about at all). Deliberately a *separate*, smaller cache from
# get_embedding_model's maxsize=1 -- this one is keyed per distinct
# query, not per model.
#
# Returns a tuple, not a list: lru_cache shares the exact same return
# object across every cache hit, and a list is mutable -- if this were
# embed_query itself, a caller mutating its result in place (nothing
# does today, but nothing stops a future one) would silently corrupt the
# cached value for every other caller sharing that entry. embed_query()
# below always returns a fresh list built from this, so its return-type
# contract doesn't change at all; only this private helper deals in the
# cache-safe immutable form.
@lru_cache(maxsize=256)
def _embed_query_cached(normalized_query: str) -> tuple[float, ...]:
    model = get_embedding_model()
    try:
        vector = model.encode(normalized_query, normalize_embeddings=True)
    except Exception as exc:
        raise EmbeddingGenerationError(f"Failed to generate embedding for query: {exc}") from exc
    return tuple(vector.tolist())


# Scoped to the exceptions this function actually raises: EmbeddingGenerationError
# (from model.encode failures) and EmbeddingModelLoadError (from get_embedding_model
# failures). The earlier version incorrectly caught LLMTimeoutError/LLMAPIError
# which this function never raises — so the retry was effectively dead code.
# lru_cache doesn't cache exceptions, so a failed call retries the real
# model.encode() on the next attempt rather than retrying against a cached
# failure.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((EmbeddingGenerationError, EmbeddingModelLoadError)),
    reraise=True,
    before_sleep=_log_retry,
)
def embed_query(query: str) -> list[float]:
    """Embed a single query string, using the same model and normalization
    as generate_embeddings, so query and chunk vectors share one space.

    Cached (see _embed_query_cached) keyed on the query normalized by
    .strip() alone -- deliberately not case-folded or otherwise altered,
    since that's also what actually gets encoded on a cache miss (the
    normalized string, not the raw input), so a cache hit can never
    return an embedding for text other than what this exact call would
    have encoded itself.
    """
    normalized_query = query.strip()
    return list(_embed_query_cached(normalized_query))


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
            batch_size=settings.embedding_batch_size,
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
