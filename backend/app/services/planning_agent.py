"""PlanningAgent: LLM-based planner that outputs structured execution plans.

The planner replaces the deterministic keyword router with an LLM that
chooses tools dynamically based on the query and available tools.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.llm_client import LLMClient
    from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_PLAN_SCHEMA = """{
  "steps": [
    {"tool": "retrieval|web_search|summarization|diagnose|vision_qa", "args": {...}, "reason": "..."},
    ...
  ],
  "final_answer_tool": "synthesize"
}"""

_PLAN_PROMPT_TEMPLATE = """You are the planner for a multi-agent document assistant. Given a user query and available tools, output a JSON execution plan.

Available tools:
{tool_descriptions}

Rules:
- Break complex queries into multiple steps (max 5 steps total)
- Use retrieval for document questions
- Use web_search for current/external info (only if web_search_enabled in settings)
- Use summarization for "summarize <doc_id>" requests
- Use diagnose for image classification queries
- Use vision_qa for questions about figures/charts in documents
- Last step must be "synthesize" to produce final answer
- Only use tools that are available in the tool list above

Output ONLY valid JSON matching:
{plan_schema}"""

_SYNTHESIZE_TOOL_DESC = """synthesize: Combine all gathered information into a final grounded answer. Args: {{"query": "original user query", "context_summary": "brief summary of all tool results"}}. Always use as the final step."""


@dataclass
class PlanStep:
    tool: str
    args: dict[str, Any]
    reason: str


@dataclass
class ExecutionPlan:
    steps: list[PlanStep]
    final_answer_tool: str = "synthesize"


class PlanningAgent:
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self._llm = llm_client
        self._tools = tool_registry

    async def plan(self, query: str, history: list[dict] | None = None) -> ExecutionPlan:
        tool_descs = self._format_tool_descriptions()
        prompt = _PLAN_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_descs,
            plan_schema=_PLAN_SCHEMA,
        )
        if history:
            hist = "\n".join(f"{h['role']}: {h['content']}" for h in history[-4:])
            prompt += f"\n\nConversation history:\n{hist}"
        prompt += f"\n\nQuery: {query}"

        try:
            raw = self._llm.generate_structured(prompt)
        except Exception as exc:
            logger.warning(
                "planner_llm_failed",
                extra={"extra_fields": {"query_length": len(query), "error": str(exc)}},
            )
            return self._fallback_plan(query)
        return self._parse_plan(raw, query)

    def _format_tool_descriptions(self) -> str:
        specs = self._tools.list()
        lines = []
        for spec in specs:
            args_json = json.dumps(spec.args_schema, indent=2)
            lines.append(f"- {spec.name}: {spec.description}\n  Args schema: {args_json}")
        lines.append(f"\n- synthesize: {_SYNTHESIZE_TOOL_DESC}")
        return "\n".join(lines)

    def _parse_plan(self, raw: str, query: str) -> ExecutionPlan:
        if not raw or not raw.strip():
            logger.warning(
                "planner_empty_response", extra={"extra_fields": {"query_length": len(query)}}
            )
            return self._fallback_plan(query)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                logger.warning(
                    "planner_no_json_object", extra={"extra_fields": {"query_length": len(query)}}
                )
                return self._fallback_plan(query)
            try:
                payload = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                logger.warning(
                    "planner_json_parse_failed",
                    extra={"extra_fields": {"query_length": len(query)}},
                )
                return self._fallback_plan(query)

        if not isinstance(payload, dict):
            logger.warning("planner_not_dict", extra={"extra_fields": {"query_length": len(query)}})
            return self._fallback_plan(query)

        steps_data = payload.get("steps")
        if not isinstance(steps_data, list) or not steps_data:
            logger.warning("planner_no_steps", extra={"extra_fields": {"query_length": len(query)}})
            return self._fallback_plan(query)

        valid_tools = {t.name for t in self._tools.list()}
        valid_tools.add("synthesize")

        steps: list[PlanStep] = []
        for step in steps_data:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool", "")).strip()
            if tool not in valid_tools:
                logger.warning(
                    "planner_unknown_tool",
                    extra={"extra_fields": {"tool": tool, "query_length": len(query)}},
                )
                continue
            args = step.get("args", {})
            if not isinstance(args, dict):
                args = {}
            reason = str(step.get("reason", "")).strip()
            steps.append(PlanStep(tool=tool, args=args, reason=reason))

        if not steps:
            logger.warning(
                "planner_no_valid_steps", extra={"extra_fields": {"query_length": len(query)}}
            )
            return self._fallback_plan(query)

        if steps[-1].tool != "synthesize":
            steps.append(
                PlanStep(
                    tool="synthesize",
                    args={"query": query, "context_summary": "auto-generated"},
                    reason="final answer synthesis",
                )
            )

        logger.info(
            "planner_generated_plan",
            extra={"extra_fields": {"step_count": len(steps), "query_length": len(query)}},
        )
        return ExecutionPlan(
            steps=steps, final_answer_tool=payload.get("final_answer_tool", "synthesize")
        )

    def _fallback_plan(self, query: str) -> ExecutionPlan:
        logger.info("planner_using_fallback", extra={"extra_fields": {"query_length": len(query)}})
        return ExecutionPlan(
            steps=[
                PlanStep(
                    tool="retrieval", args={"query": query}, reason="fallback: direct retrieval"
                ),
                PlanStep(
                    tool="synthesize",
                    args={"query": query, "context_summary": "fallback retrieval"},
                    reason="fallback synthesis",
                ),
            ]
        )
