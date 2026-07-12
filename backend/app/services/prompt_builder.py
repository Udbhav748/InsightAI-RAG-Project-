"""Builds an LLM prompt from a user query and its retrieved chunks.

Pure text formatting: no retrieval, no LLM calls.
"""

import re

from app.core.exceptions import PromptGenerationError
from app.models.document import RetrievedChunk

# Matches the prompt's own "Sources:" heading (see _INSTRUCTIONS below),
# so strip_sources_section can remove the model's raw-document-id citation
# list from an answer. The app already returns document sources as
# structured data (ChatResponse.sources), resolved to friendly names by
# the frontend, so the model's own citation text would just duplicate it.
_SOURCES_HEADING = re.compile(r"\n*sources:.*", re.IGNORECASE | re.DOTALL)

_NO_CONTEXT_NOTE = "No documents were retrieved for this question."

_FALLBACK_REPLY = "I couldn't find that information in the uploaded documents."

_INSTRUCTIONS = (
    "You are InsightAI, an intelligent document assistant.\n\n"
    "Answer the user's question naturally and conversationally using ONLY "
    "the provided context.\n\n"
    "Do not say:\n"
    '- "Based on the provided document..."\n'
    '- "According to the document..."\n'
    '- "The context states..."\n\n'
    "Instead, answer as if you already know the information.\n\n"
    "If the answer is not present in the provided context, clearly reply:\n"
    f'"{_FALLBACK_REPLY}"\n\n'
    "Never hallucinate. Keep answers concise and professional.\n\n"
    "After the answer, list the document source(s) separately under:\n"
    "Sources:"
)


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    if not query or not query.strip():
        raise PromptGenerationError("Cannot build a prompt from an empty query.")

    if chunks:
        context = "\n\n".join(
            f"[Document {chunk.document_id}] {chunk.text}" for chunk in chunks
        )
    else:
        context = _NO_CONTEXT_NOTE

    return (
        f"{_INSTRUCTIONS}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query.strip()}\n\n"
        "Answer:"
    )


def strip_sources_section(answer: str) -> str:
    """Remove the model's own "Sources:" citation list from its answer.

    The prompt instructs the model to append one (using raw document ids,
    since that's all it's given), but the app already returns sources as
    structured data that the frontend renders with friendly names —
    keeping the model's copy would just duplicate it in the answer text.
    """
    return _SOURCES_HEADING.sub("", answer).strip()
