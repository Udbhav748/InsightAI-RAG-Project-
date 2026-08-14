"""WebResearcher: Multi-step web research agent.

Wraps the ResearchAgent for queries needing current/external information
beyond the uploaded corpus.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.services.agents.base import Agent, AgentContext, AgentResult
from app.services.research_agent import ResearchAgent, ResearchFindings

if TYPE_CHECKING:
    from app.models.document import WebSearchResult
    from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class WebResearcher(Agent):
    name = "web_researcher"
    description = "Conducts multi-step web research for current/external information"

    def __init__(self, llm_client: LLMClient):
        self._research_agent = ResearchAgent(llm_client)

    async def run(self, query: str, context: AgentContext) -> AgentResult:
        if not settings.web_search_enabled:
            return AgentResult(
                answer="Web search is disabled. Cannot perform external research.",
                sources=[],
                metadata={"tool": self.name, "success": False, "reason": "web_search_disabled"},
            )

        findings: ResearchFindings = await self._run_research(query, context.confirm_web_search)

        if not findings.answer:
            return AgentResult(
                answer="Web research did not yield a usable answer.",
                sources=[],
                metadata={"tool": self.name, "success": False, "reason": "no_findings"},
            )

        sources = self._build_sources(findings.results)
        return AgentResult(
            answer=findings.answer,
            sources=sources,
            metadata={
                "tool": self.name,
                "success": True,
                "queries": findings.queries,
                "pages_read": findings.pages_read,
                "steps": findings.steps,
            },
        )

    async def _run_research(self, query: str, confirm_web_search: bool) -> ResearchFindings:
        import asyncio

        return await asyncio.to_thread(self._research_agent.run, query, confirm_web_search)

    def _build_sources(self, results: list[WebSearchResult]) -> list[dict[str, Any]]:
        from app.services.rag_service import _web_source_references

        refs = _web_source_references(results)
        return [
            {
                "document_id": r.document_id,
                "chunk_id": r.chunk_id,
                "excerpt": r.excerpt,
                "url": r.url,
            }
            for r in refs
        ]
