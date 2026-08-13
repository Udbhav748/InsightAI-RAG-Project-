"""Summarizer: Whole-document summarization agent.

Wraps the SummarizationService for "summarize <document_id>" requests.
"""

from __future__ import annotations

import logging

from app.services.agents.base import Agent, AgentContext, AgentResult
from app.services.summarization_service import summarize_document

logger = logging.getLogger(__name__)


class Summarizer(Agent):
    name = "summarizer"
    description = "Produces a whole-document summary for one uploaded document"

    def __init__(self):
        pass

    async def run(self, query: str, context: AgentContext) -> AgentResult:
        document_id = context.metadata.get("document_id")
        if not document_id:
            return AgentResult(
                answer="No document_id provided for summarization.",
                sources=[],
                metadata={"tool": self.name, "success": False, "reason": "missing_document_id"},
            )

        import asyncio

        try:
            summary, chunks = await asyncio.to_thread(
                summarize_document,
                document_id,
                context.vector_store,
                context.llm_client,
                context.tenant_id,
            )
        except Exception as exc:
            logger.warning(
                "summarizer_failed",
                extra={"extra_fields": {"document_id": document_id, "error": str(exc)}},
            )
            return AgentResult(
                answer="I couldn't summarize that document.",
                sources=[],
                metadata={"tool": self.name, "success": False, "reason": "summarization_error"},
            )

        if not summary:
            return AgentResult(
                answer="No summary available for that document.",
                sources=[],
                metadata={"tool": self.name, "success": False, "reason": "empty_summary"},
            )

        sources = self._build_sources(chunks)
        return AgentResult(
            answer=summary,
            sources=sources,
            metadata={"tool": self.name, "success": True, "chunks": len(chunks)},
        )

    def _build_sources(self, chunks: list) -> list[dict]:
        from app.services.rag_service import _source_references

        refs = _source_references(chunks)
        return [
            {"document_id": r.document_id, "chunk_id": r.chunk_id, "excerpt": r.excerpt}
            for r in refs
        ]
