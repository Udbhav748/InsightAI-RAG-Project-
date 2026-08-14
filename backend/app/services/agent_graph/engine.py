"""StateGraph engine: lightweight, pure-Python graph-based agent runtime.

Supports:
- Typed node registration (add_node)
- Deterministic and conditional edge routing (add_edge, add_conditional_edges)
- State checkpoint history & step snapshot tracking
- Loop cycle capping (max_steps guardrail)
- Async execution and streaming iteration
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from app.services.agent_graph.state import AgentState

logger = logging.getLogger(__name__)

START = "__start__"
END = "__end__"


class StateGraphError(Exception):
    """Base exception for StateGraph errors."""


class GraphCompilationError(StateGraphError):
    """Raised when the graph validation fails during compilation."""


class MaxStepsExceededError(StateGraphError):
    """Raised when execution exceeds the maximum allowed step threshold."""


@dataclass
class StateSnapshot:
    """Snapshot of agent state at a specific step in graph execution."""

    step_index: int
    node_name: str
    state: AgentState
    timestamp: float
    duration_ms: float


class StateGraph:
    """Graph builder for multi-agent workflows."""

    def __init__(self) -> None:
        self._nodes: dict[str, Callable[..., Any]] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, tuple[Callable[..., Any], dict[str, str] | None]] = {}
        self._entry_point: str | None = None

    def add_node(self, name: str, fn: Callable[..., Any]) -> StateGraph:
        """Register a node function with a unique name."""
        if name in (START, END):
            raise ValueError(f"Cannot name a node '{name}': reserved keyword.")
        if name in self._nodes:
            raise ValueError(f"Node '{name}' is already registered.")
        self._nodes[name] = fn
        return self

    def add_edge(self, from_node: str, to_node: str) -> StateGraph:
        """Register a deterministic transition edge from one node to another."""
        if from_node == END:
            raise ValueError("Cannot add an outgoing edge from END.")
        self._edges[from_node] = to_node
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        condition: Callable[..., Any],
        mapping: dict[str, str] | None = None,
    ) -> StateGraph:
        """Register a conditional edge routing function from a node."""
        if from_node == END:
            raise ValueError("Cannot add conditional edges from END.")
        self._conditional_edges[from_node] = (condition, mapping)
        return self

    def set_entry_point(self, node_name: str) -> StateGraph:
        """Designate the graph entry node."""
        self._entry_point = node_name
        return self

    def compile(self, max_steps: int = 10) -> CompiledGraph:
        """Validate and compile the graph into an executable CompiledGraph."""
        if not self._entry_point:
            raise GraphCompilationError("Graph entry point is not set.")
        if self._entry_point not in self._nodes:
            raise GraphCompilationError(f"Entry point '{self._entry_point}' not found in nodes.")

        # Validate deterministic edges
        for from_n, to_n in self._edges.items():
            if from_n not in self._nodes and from_n != START:
                raise GraphCompilationError(f"Edge source '{from_n}' is not a registered node.")
            if to_n not in self._nodes and to_n != END:
                raise GraphCompilationError(f"Edge target '{to_n}' is not a registered node.")

        # Validate conditional edges
        for from_n, (_, mapping) in self._conditional_edges.items():
            if from_n not in self._nodes:
                raise GraphCompilationError(f"Conditional edge source '{from_n}' not found.")
            if mapping:
                for target in mapping.values():
                    if target not in self._nodes and target != END:
                        raise GraphCompilationError(
                            f"Conditional target '{target}' from '{from_n}' is not a registered node."
                        )

        return CompiledGraph(
            nodes=dict(self._nodes),
            edges=dict(self._edges),
            conditional_edges=dict(self._conditional_edges),
            entry_point=self._entry_point,
            max_steps=max_steps,
        )


class CompiledGraph:
    """Compiled, validated graph runtime ready for execution."""

    def __init__(
        self,
        nodes: dict[str, Callable[..., Any]],
        edges: dict[str, str],
        conditional_edges: dict[str, tuple[Callable[..., Any], dict[str, str] | None]],
        entry_point: str,
        max_steps: int = 10,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.max_steps = max_steps
        self._history: list[StateSnapshot] = []

    def get_state_history(self) -> list[StateSnapshot]:
        """Return the sequence of state snapshots from the most recent run."""
        return list(self._history)

    async def _invoke_node(
        self,
        node_name: str,
        current_state: AgentState,
        context: Any,
    ) -> AgentState:
        fn = self.nodes[node_name]
        sig = inspect.signature(fn)
        num_params = len(sig.parameters)

        if num_params >= 2:
            res = fn(current_state, context)
        else:
            res = fn(current_state)

        if asyncio.iscoroutine(res):
            res = await res

        if isinstance(res, AgentState):
            return res
        if isinstance(res, dict):
            return current_state.copy_with(**res)
        return current_state

    async def _get_next_node(
        self,
        current_node: str,
        current_state: AgentState,
        context: Any,
    ) -> str:
        if current_node in self.conditional_edges:
            condition_fn, mapping = self.conditional_edges[current_node]
            sig = inspect.signature(condition_fn)
            if len(sig.parameters) >= 2:
                route_res = condition_fn(current_state, context)
            else:
                route_res = condition_fn(current_state)

            if asyncio.iscoroutine(route_res):
                route_res = await route_res

            route_name = str(route_res)
            if mapping is not None:
                next_node = mapping.get(route_name, route_name)
            else:
                next_node = route_name
            return next_node

        if current_node in self.edges:
            return self.edges[current_node]

        return END

    async def run(
        self,
        initial_state: AgentState | dict[str, Any],
        context: Any = None,
    ) -> AgentState:
        """Execute the graph from entry point to END or max_steps."""
        current_state = (
            initial_state
            if isinstance(initial_state, AgentState)
            else AgentState(**initial_state)
        )
        self._history = []
        current_node = self.entry_point
        step_index = 0

        while current_node != END and step_index < self.max_steps:
            step_index += 1
            start_t = time.perf_counter()

            try:
                current_state = await self._invoke_node(current_node, current_state, context)
            except Exception as exc:
                logger.error(
                    "graph_node_execution_failed",
                    extra={"extra_fields": {"node": current_node, "error": str(exc)}},
                )
                current_state = current_state.copy_with(error=f"{type(exc).__name__}: {exc}")
                break

            duration_ms = (time.perf_counter() - start_t) * 1000
            self._history.append(
                StateSnapshot(
                    step_index=step_index,
                    node_name=current_node,
                    state=current_state.model_copy(deep=True),
                    timestamp=time.time(),
                    duration_ms=duration_ms,
                )
            )

            current_node = await self._get_next_node(current_node, current_state, context)

        if step_index >= self.max_steps and current_node != END:
            logger.warning(
                "graph_cycle_capped_max_steps",
                extra={"extra_fields": {"max_steps": self.max_steps, "last_node": current_node}},
            )
            current_state = current_state.copy_with(
                error=current_state.error or f"Max steps exceeded ({self.max_steps})"
            )

        return current_state

    async def stream(
        self,
        initial_state: AgentState | dict[str, Any],
        context: Any = None,
    ) -> AsyncIterator[tuple[str, AgentState]]:
        """Stream each step's (node_name, state) as nodes finish execution."""
        current_state = (
            initial_state
            if isinstance(initial_state, AgentState)
            else AgentState(**initial_state)
        )
        self._history = []
        current_node = self.entry_point
        step_index = 0

        while current_node != END and step_index < self.max_steps:
            step_index += 1
            start_t = time.perf_counter()

            try:
                current_state = await self._invoke_node(current_node, current_state, context)
            except Exception as exc:
                logger.error(
                    "graph_node_execution_failed",
                    extra={"extra_fields": {"node": current_node, "error": str(exc)}},
                )
                current_state = current_state.copy_with(error=f"{type(exc).__name__}: {exc}")
                yield (current_node, current_state)
                break

            duration_ms = (time.perf_counter() - start_t) * 1000
            self._history.append(
                StateSnapshot(
                    step_index=step_index,
                    node_name=current_node,
                    state=current_state.model_copy(deep=True),
                    timestamp=time.time(),
                    duration_ms=duration_ms,
                )
            )

            yield (current_node, current_state)
            current_node = await self._get_next_node(current_node, current_state, context)
