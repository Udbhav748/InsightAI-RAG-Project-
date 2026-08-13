"""Base classes for specialized agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.agent_memory import AgentMemory
    from app.services.llm_client import LLMClient
    from app.services.vector_store import VectorStore


@dataclass
class AgentContext:
    """Context passed to agent.run() containing all dependencies."""

    vector_store: VectorStore
    llm_client: LLMClient
    agent_memory: AgentMemory | None
    tenant_id: int | None
    history: list[dict] | None
    prompt_builder: Any  # callable(query, chunks, history, web_results) -> str
    confirm_web_search: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result returned by agent.run()."""

    answer: str
    sources: list[dict]
    metadata: dict[str, Any]


class Agent(ABC):
    """Base class for all specialized agents."""

    name: str
    description: str

    @abstractmethod
    async def run(self, query: str, context: AgentContext) -> AgentResult:
        """Execute the agent on a query with the given context."""
        pass
