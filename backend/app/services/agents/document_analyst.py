"""DocumentAnalyst: Deep document Q&A agent.

Wraps retrieval + synthesis for complex document questions that may need
multi-step reasoning over the local corpus.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.agents.base import Agent, AgentContext, AgentResult
from app.services.tools.base import ToolContext

if TYPE_CHECKING:
    from app.models.document import RetrievedChunk
    from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class DocumentAnalyst(Agent):
    name = "document_analyst"
    description = "Answers complex questions by retrieving and synthesizing from uploaded documents"

    def __init__(self, tool_registry: ToolRegistry):
        self._tools = tool_registry

    async def run(self, query: str, context: AgentContext) -> AgentResult:
        tool_context = ToolContext(
            vector_store=context.vector_store,
            llm_client=context.llm_client,
            agent_memory=context.agent_memory,
            tenant_id=context.tenant_id,
        )

        result = await self._tools.execute("retrieval", {"query": query}, tool_context)

        if not result.success or not result.data:
            return AgentResult(
                answer="I couldn't find relevant information in your documents.",
                sources=[],
                metadata={"tool": self.name, "success": False},
            )

        chunks = result.data
        prompt = context.prompt_builder(query, chunks, context.history, web_results=None)

        answer = context.llm_client.generate(prompt)
        from app.services.prompt_builder import strip_sources_section

        answer = strip_sources_section(answer)

        sources = self._build_sources(chunks)

        return AgentResult(
            answer=answer,
            sources=sources,
            metadata={
                "tool": self.name,
                "success": True,
                "chunks_retrieved": len(chunks),
            },
        )

    def _build_sources(self, chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
        from app.services.rag_service import _source_references

        refs = _source_references(chunks)
        return [
            {"document_id": r.document_id, "chunk_id": r.chunk_id, "excerpt": r.excerpt}
            for r in refs
        ]
