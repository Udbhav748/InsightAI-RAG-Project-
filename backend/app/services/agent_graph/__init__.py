"""Graph-Based Agent State Engine / StateGraph Runtime for InsightAI-RAG.

Public API exporting:
- StateGraph, CompiledGraph
- AgentState
- GraphContext
- Node functions (planner_node, document_analyst_node, fact_checker_node,
  web_researcher_node, summarizer_node, synthesizer_node)
- create_rag_agent_graph (pre-configured multi-agent workflow graph)
- START, END
"""

from __future__ import annotations

from app.services.agent_graph.engine import (
    END,
    START,
    CompiledGraph,
    GraphCompilationError,
    MaxStepsExceededError,
    StateGraph,
    StateSnapshot,
)
from app.services.agent_graph.nodes import (
    GraphContext,
    document_analyst_node,
    fact_checker_node,
    planner_node,
    summarizer_node,
    synthesizer_node,
    web_researcher_node,
)
from app.services.agent_graph.state import AgentState


def create_rag_agent_graph(
    context: GraphContext | None = None,
    max_steps: int = 10,
    max_reflections: int = 2,
) -> CompiledGraph:
    """Build and compile the standard InsightAI RAG multi-agent graph.

    Topology:
    1. START -> planner
    2. planner ->
       - conversational -> synthesizer -> END
       - summarize -> summarizer -> synthesizer -> fact_checker
       - research -> web_researcher -> synthesizer -> fact_checker
       - retrieve -> document_analyst
    3. document_analyst ->
       - if chunks empty and web search allowed -> web_researcher
       - else -> synthesizer
    4. web_researcher -> synthesizer
    5. synthesizer -> fact_checker
    6. fact_checker ->
       - if verified or reflections >= max_reflections -> END
       - if unverified and reflections < max_reflections -> synthesizer (reflection loop)
    """
    graph = StateGraph()

    # Register nodes
    graph.add_node("planner", planner_node)
    graph.add_node("document_analyst", document_analyst_node)
    graph.add_node("web_researcher", web_researcher_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("fact_checker", fact_checker_node)

    # Set entry point
    graph.set_entry_point("planner")

    # Routing from planner
    def route_planner(state: AgentState) -> str:
        if not isinstance(state.plan, dict):
            return "document_analyst"
        action = state.plan.get("action", "retrieve")
        if action == "conversational":
            return "synthesizer"
        if action == "summarize":
            return "summarizer"
        if action == "research":
            return "web_researcher"
        return "document_analyst"

    graph.add_conditional_edges("planner", route_planner)

    # Routing from summarizer -> synthesizer
    graph.add_edge("summarizer", "synthesizer")

    # Routing from document_analyst
    def route_document_analyst(state: AgentState) -> str:
        # If no chunks found and web search is enabled, fallback to web research
        if not state.retrieved_chunks and state.confirm_web_search:
            return "web_researcher"
        return "synthesizer"

    graph.add_conditional_edges("document_analyst", route_document_analyst)

    # Routing from web_researcher -> synthesizer
    graph.add_edge("web_researcher", "synthesizer")

    # Routing from synthesizer -> fact_checker
    def route_synthesizer(state: AgentState) -> str:
        # Conversational fast path can skip fact checking directly
        if isinstance(state.plan, dict) and state.plan.get("action") == "conversational":
            return END
        return "fact_checker"

    graph.add_conditional_edges("synthesizer", route_synthesizer)

    # Routing from fact_checker (Reflection loop)
    def route_fact_checker(state: AgentState) -> str:
        if state.is_fact_check_passed() or state.reflection_count >= max_reflections:
            return END
        # Self-correction loop: return to synthesizer with reflection context
        return "synthesizer"

    graph.add_conditional_edges("fact_checker", route_fact_checker)

    return graph.compile(max_steps=max_steps)


__all__ = [
    "AgentState",
    "CompiledGraph",
    "END",
    "GraphCompilationError",
    "GraphContext",
    "MaxStepsExceededError",
    "START",
    "StateGraph",
    "StateSnapshot",
    "create_rag_agent_graph",
    "document_analyst_node",
    "fact_checker_node",
    "planner_node",
    "summarizer_node",
    "synthesizer_node",
    "web_researcher_node",
]
