"""Modular RAG package for InsightAI.

Provides:
- router: Intent classification, small talk detection, and routing
- retrieval_grader: Quality evaluation of retrieved chunks (good/weak/insufficient)
- reflection_engine: Corrective RAG reflection loop, LLM call capping, hallucination detection
- stream_adapter: SSE token filtering and event formatting
"""

from app.services.rag.reflection_engine import (
    _MAX_LLM_CALLS,
    CHEMICAL_SAFETY_INSTRUCTION,
    ReflectionEngine,
    answer_source,
    capture_prompt,
    content_tokens,
    contextualize_query,
    correct_answer,
    correct_answer_streamed,
    detect_hallucination,
    excerpt,
    generate_answer,
    generate_answer_streamed,
    generate_answer_structured,
    grounding_score,
    is_ungrounded,
    search_web_fallback,
    source_references,
    suggest_follow_ups,
    verify_chemical_safety,
    verify_citations,
    web_source_references,
)
from app.services.rag.retrieval_grader import RetrievalGrader, grade_retrieval
from app.services.rag.router import (
    PlanDecision,
    QueryRouter,
    build_diagnosis_query,
    extract_crop_context,
    match_conversational_reply,
    normalize_query,
    plan_query,
    route_query,
)
from app.services.rag.stream_adapter import (
    StreamAdapter,
    format_answer_chunk,
    format_done_event,
    format_error_event,
    stream_filtering_sources,
    trace_event,
)

__all__ = [
    # Router
    "PlanDecision",
    "QueryRouter",
    "plan_query",
    "route_query",
    "match_conversational_reply",
    "build_diagnosis_query",
    "extract_crop_context",
    "normalize_query",
    # Grader
    "RetrievalGrader",
    "grade_retrieval",
    # Reflection Engine
    "_MAX_LLM_CALLS",
    "CHEMICAL_SAFETY_INSTRUCTION",
    "ReflectionEngine",
    "correct_answer",
    "correct_answer_streamed",
    "generate_answer",
    "generate_answer_streamed",
    "generate_answer_structured",
    "detect_hallucination",
    "grounding_score",
    "content_tokens",
    "is_ungrounded",
    "contextualize_query",
    "verify_citations",
    "verify_chemical_safety",
    "suggest_follow_ups",
    "source_references",
    "web_source_references",
    "answer_source",
    "excerpt",
    "capture_prompt",
    "search_web_fallback",
    # Stream Adapter
    "StreamAdapter",
    "stream_filtering_sources",
    "trace_event",
    "format_answer_chunk",
    "format_error_event",
    "format_done_event",
]
