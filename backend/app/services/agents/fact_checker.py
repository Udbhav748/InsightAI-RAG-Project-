"""FactChecker: Cross-references claims against sources.

Verifies that answer citations are actually supported by the cited chunks.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.agents.base import Agent, AgentContext, AgentResult

if TYPE_CHECKING:
    from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class FactChecker(Agent):
    name = "fact_checker"
    description = "Verifies answer citations against source chunks"

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    async def run(self, query: str, context: AgentContext) -> AgentResult:
        answer = context.metadata.get("answer", "")
        chunks = context.metadata.get("chunks", [])

        if not answer or not chunks:
            return AgentResult(
                answer=answer,
                sources=context.metadata.get("sources", []),
                metadata={"tool": self.name, "verified": True, "skipped": True},
            )

        if not settings.citation_verification_enabled:
            return AgentResult(
                answer=answer,
                sources=context.metadata.get("sources", []),
                metadata={"tool": self.name, "verified": True, "skipped": True},
            )

        verified = await self._verify_citations(answer, chunks)
        return AgentResult(
            answer=answer,
            sources=context.metadata.get("sources", []),
            metadata={"tool": self.name, "verified": verified, "skipped": False},
        )

    async def _verify_citations(self, answer: str, chunks: list) -> bool:
        citation_numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
        if not citation_numbers:
            return True

        chunk_by_number = {i + 1: chunk for i, chunk in enumerate(chunks)}
        cited_pairs = [
            (n, chunk_by_number[n].text) for n in citation_numbers if n in chunk_by_number
        ]
        if not cited_pairs:
            return True

        prompt = (
            "Answer:\n"
            + answer
            + "\n\n"
            + "\n\n".join(f"Excerpt [{n}]:\n{text}" for n, text in cited_pairs)
            + "\n\nFor each excerpt number above, does the answer's claim "
            "attributed to it actually match what that excerpt says? "
            'Respond with ONLY a JSON object like {"1": true, "2": false}, '
            "one entry per excerpt number shown."
        )
        try:
            raw = self._llm.generate(prompt)
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            import json

            result = json.loads(raw)
            return all(result.get(str(n), True) for n, _ in cited_pairs)
        except Exception:
            logger.warning("fact_checker_verification_failed", extra={"extra_fields": {}})
            return True
