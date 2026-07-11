"""Builds an LLM prompt from a user query and its retrieved chunks.

Pure text formatting: no retrieval, no LLM calls.
"""

from app.core.exceptions import PromptGenerationError
from app.models.document import RetrievedChunk

_NO_CONTEXT_MESSAGE = "No relevant context was found in the uploaded documents."

_INSTRUCTIONS = (
    "You are a helpful assistant answering questions based only on the "
    "provided context. If the context does not contain the answer, say "
    "you don't know rather than guessing."
)


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    if not query or not query.strip():
        raise PromptGenerationError("Cannot build a prompt from an empty query.")

    if chunks:
        context = "\n\n".join(
            f"[Source {index + 1}] {chunk.text}" for index, chunk in enumerate(chunks)
        )
    else:
        context = _NO_CONTEXT_MESSAGE

    return (
        f"{_INSTRUCTIONS}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query.strip()}\n\n"
        "Answer:"
    )
