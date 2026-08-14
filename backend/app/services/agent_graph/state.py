"""State definitions for graph-based multi-agent workflows.

Provides typed, serializable AgentState capturing all data flowing through
the StateGraph runtime: query, plan, retrieval chunks, web results,
intermediate drafts, fact-check outcomes, reflection counts, and final responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.document import RetrievedChunk, WebSearchResult
    from app.models.schemas import ChatResponse, DiagnosisInfo


class AgentState(BaseModel):
    """The central state container passed between nodes in the StateGraph runtime.

    Pure Python, typed Pydantic model supporting state immutability,
    step snapshotting, and serialized checkpointing.
    """

    # Core user input and intent plan
    query: str = Field(..., description="The user's natural-language query or prompt.")
    plan: dict[str, Any] | str | None = Field(
        default=None,
        description="Current workflow plan or routed action decided by the planner node.",
    )

    # Retrieval and research artifacts
    retrieved_chunks: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Document chunks retrieved from local vector store / BM25 index.",
    )
    web_results: list[WebSearchResult] = Field(
        default_factory=list,
        description="External search results retrieved from web research passes.",
    )
    diagnosis: DiagnosisInfo | None = Field(
        default=None,
        description="Optional image diagnosis information for multimodal queries.",
    )

    # Generation and verification artifacts
    draft_answer: str = Field(
        default="",
        description="Intermediate synthesized answer before verification/reflection.",
    )
    fact_check_result: dict[str, Any] | bool | None = Field(
        default=None,
        description="Outcome of citation and claim verification against ground-truth chunks.",
    )

    # Execution telemetry and control
    steps_taken: int = Field(
        default=0,
        description="Number of node executions completed in this graph run.",
    )
    reflection_count: int = Field(
        default=0,
        description="Number of corrective reflection loops executed so far.",
    )
    history: list[dict[str, Any]] | None = Field(
        default=None,
        description="Recent conversation history turns for multi-turn context.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if a node failed during execution.",
    )
    final_response: ChatResponse | None = Field(
        default=None,
        description="The final validated ChatResponse payload delivered to the client.",
    )

    # Contextual metadata and configuration flags
    document_id: str | None = Field(
        default=None,
        description="Specific document UUID for document-targeted actions (e.g. summarization).",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier for state persistence and memory integration.",
    )
    tenant_id: int | None = Field(
        default=None,
        description="Tenant ID for multi-tenant data isolation.",
    )
    confirm_web_search: bool = Field(
        default=False,
        description="Human approval flag for external web search side-effects.",
    )
    persona: str | None = Field(
        default=None,
        description="Optional tone/style preset (e.g. 'concise', 'eli5').",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional node-specific metadata or intermediate flags.",
    )

    def copy_with(self, **kwargs: Any) -> AgentState:
        """Return a new copy of AgentState with updated fields."""
        return self.model_copy(update=kwargs)

    def is_fact_check_passed(self) -> bool:
        """Check whether fact verification passed."""
        if self.fact_check_result is None:
            return True
        if isinstance(self.fact_check_result, bool):
            return self.fact_check_result
        if isinstance(self.fact_check_result, dict):
            return bool(self.fact_check_result.get("verified", True))
        return True
