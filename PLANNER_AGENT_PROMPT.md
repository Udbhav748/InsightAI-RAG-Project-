# PlannerAgent Implementation Prompt

## Goal
Create a `PlannerAgent` that decomposes a user query into an ordered list of executable tasks (Plan), using `ToolRegistry` and `AgentMemory` as dependencies.

## File Location
`backend/app/services/planner_agent.py`

## Interface
```python
from pydantic import BaseModel, Field
from typing import Literal
from app.services.tool_registry import ToolRegistry
from app.services.agent_memory import AgentMemory

class Task(BaseModel):
    tool: str                          # must exist in ToolRegistry
    args: dict                         # validated against tool.args_schema
    description: str                   # human-readable step description
    depends_on: list[int] = Field(default_factory=list)  # indices of prior tasks whose output this needs

class Plan(BaseModel):
    tasks: list[Task]
    reasoning: str                     # why this plan answers the query

class PlannerAgent:
    def __init__(self, tool_registry: ToolRegistry, memory: AgentMemory):
        ...

    async def plan(self, query: str, session_id: str) -> Plan:
        ...
```

## Behavior
1. **Retrieve context** from `AgentMemory` for `session_id` (last 5 turns + extracted facts)
2. **List available tools** from `ToolRegistry` (name, description, args_schema)
3. **Call LLM** (GeminiClient) with a structured prompt that includes:
   - User query
   - Conversation context
   - Available tools (as JSON schema)
   - Output format: `Plan` (Pydantic model)
4. **Validate** the returned plan:
   - Every `tool` exists in registry
   - Every `args` conforms to that tool's `args_schema`
   - No circular dependencies in `depends_on`
5. **Return** validated `Plan` or raise `PlanningError(AppError)`

## Prompt Template (for LLM call)
```
You are a planner that breaks down a user query into a sequence of tool calls.
Available tools:
{{tool_schemas}}

Conversation context (last 5 turns + facts):
{{context}}

User query: "{{query}}"

Output a JSON object matching this schema:
{
  "tasks": [
    {"tool": "string", "args": {}, "description": "string", "depends_on": [int]}
  ],
  "reasoning": "string"
}

Rules:
- Use ONLY tools from the available list
- Each task must be executable independently given its dependencies
- Minimize number of tasks; prefer parallelizable steps
- If query is simple (greeting, small talk), return empty tasks with reasoning
```

## Dependencies to Wire
- `ToolRegistry` (singleton via `get_tool_registry()` in `query.py`)
- `AgentMemory` (new singleton `get_agent_memory()` in `query.py`)
- `GeminiClient` (via `get_llm_client()`)

## Tests Required
`tests/test_planner_agent.py`:
- Valid plan for multi-hop query (e.g., "summarize doc X then compare with web results for Y")
- Rejects unknown tool
- Rejects invalid args
- Handles empty plan for small talk
- Uses cached memory context correctly

## Integration Point
`ResearchAgent.__init__` accepts optional `planner: PlannerAgent`; if provided, `_plan_queries()` delegates to `planner.plan()` instead of internal LLM call.