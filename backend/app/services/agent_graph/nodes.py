"""Graph node functions wrapping InsightAI's core multi-agent capabilities.

Nodes:
- planner_node: routes query intent (document_analysis, summarization, research, conversational).
- document_analyst_node: dense + BM25 retrieval and chunk extraction.
- fact_checker_node: verifies citations and claims against ground-truth chunks.
- web_researcher_node: external search fallback when context is weak or query is outside corpus.
- summarizer_node: full-document summarization.
- synthesizer_node: LLM generation with prompt injection delimiters and reflection context.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.models.schemas import ChatResponse, SourceReference
from app.services.prompt_builder import (
    FALLBACK_REPLY,
    REFLECTION_INSTRUCTION,
    build_prompt,
    strip_sources_section,
)
from app.services.prompt_injection_service import detect_possible_injection
from app.services.rag_service import (
    _CONVERSATIONAL_INTENTS,
    _DOCUMENT_ID_RE,
    _SUMMARIZE_RE,
    _normalize,
    _source_references,
    _web_source_references,
)
from app.services.retrieval_service import retrieve
from app.services.summarization_service import summarize_document
from app.services.web_search_service import search_web

if TYPE_CHECKING:
    from app.services.agent_graph.state import AgentState
    from app.services.llm_client import LLMClient
    from app.services.router_agent import RouterAgent
    from app.services.tools.registry import ToolRegistry
    from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class GraphContext:
    """Dependencies injected into node functions during graph execution."""

    llm_client: LLMClient | None = None
    vector_store: VectorStore | None = None
    tool_registry: ToolRegistry | None = None
    image_vector_store: VectorStore | None = None
    router_agent: RouterAgent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


async def planner_node(state: AgentState, context: GraphContext | None = None) -> AgentState:
    """Classifies user intent and sets state.plan."""
    query = state.query.strip()
    norm = _normalize(query)

    # 1. Fast path: conversational small talk
    for phrases, canned_resp in _CONVERSATIONAL_INTENTS:
        if norm in phrases:
            return state.copy_with(
                plan={"action": "conversational", "canned": canned_resp, "reason": "fast_path"},
                draft_answer=canned_resp,
                steps_taken=state.steps_taken + 1,
            )

    # 2. Fast path: document summarization with explicit UUID
    if _SUMMARIZE_RE.search(query):
        match = _DOCUMENT_ID_RE.search(query)
        if match:
            doc_id = match.group(0)
            return state.copy_with(
                plan={"action": "summarize", "document_id": doc_id, "reason": "fast_path"},
                document_id=doc_id,
                steps_taken=state.steps_taken + 1,
            )

    # 3. Router agent / LLM classification if available
    if context and context.router_agent:
        decision = context.router_agent.decide(query, state.history)
        action = decision.action
        routed_doc_id = decision.document_id or state.document_id
        return state.copy_with(
            plan={"action": action, "document_id": routed_doc_id, "reason": "router_agent"},
            document_id=routed_doc_id,
            steps_taken=state.steps_taken + 1,
        )

    # 4. Keyword heuristic fallback
    lower = query.lower()
    if any(term in lower for term in ["latest", "recent", "today", "news", "price of", "weather"]):
        action = "research" if settings.web_search_enabled else "retrieve"
    else:
        action = "retrieve"

    return state.copy_with(
        plan={"action": action, "document_id": state.document_id, "reason": "heuristic_fallback"},
        steps_taken=state.steps_taken + 1,
    )


async def document_analyst_node(
    state: AgentState,
    context: GraphContext | None = None,
) -> AgentState:
    """Executes dense + BM25 retrieval and chunk extraction."""
    if not context or not context.vector_store:
        logger.warning("document_analyst_node: no vector_store in context")
        return state.copy_with(steps_taken=state.steps_taken + 1)

    doc_filter = [state.document_id] if state.document_id else None
    chunks = retrieve(
        query=state.query,
        vector_store=context.vector_store,
        tenant_id=state.tenant_id,
        document_ids=doc_filter,
        image_vector_store=context.image_vector_store,
    )

    # Prompt injection heuristic logging for retrieved chunks
    for chunk in chunks:
        injections = detect_possible_injection(chunk.text)
        if injections:
            logger.warning(
                "possible_injection_detected",
                extra={"extra_fields": {"source": "chunk", "categories": injections}},
            )

    return state.copy_with(
        retrieved_chunks=chunks,
        steps_taken=state.steps_taken + 1,
    )


async def web_researcher_node(
    state: AgentState,
    context: GraphContext | None = None,
) -> AgentState:
    """Conducts external web search fallback when context is weak or query is external."""
    if not settings.web_search_enabled:
        return state.copy_with(
            metadata={"web_search": "disabled"},
            steps_taken=state.steps_taken + 1,
        )

    if settings.web_search_requires_approval and not state.confirm_web_search:
        return state.copy_with(
            metadata={"web_search": "pending_approval"},
            steps_taken=state.steps_taken + 1,
        )

    try:
        results = search_web(state.query, max_results=3)
    except Exception as exc:
        logger.warning("web_researcher_failed", extra={"extra_fields": {"error": str(exc)}})
        results = []

    return state.copy_with(
        web_results=results,
        steps_taken=state.steps_taken + 1,
    )


async def summarizer_node(
    state: AgentState,
    context: GraphContext | None = None,
) -> AgentState:
    """Full-document summarization for target document_id."""
    if not state.document_id:
        return state.copy_with(
            draft_answer="No document_id provided for summarization.",
            steps_taken=state.steps_taken + 1,
        )

    if not context or not context.vector_store or not context.llm_client:
        return state.copy_with(
            draft_answer="Summarization dependencies unavailable.",
            steps_taken=state.steps_taken + 1,
        )

    try:
        summary, chunks = summarize_document(
            document_id=state.document_id,
            vector_store=context.vector_store,
            llm_client=context.llm_client,
            tenant_id=state.tenant_id,
        )
        return state.copy_with(
            draft_answer=summary or "Could not generate summary.",
            retrieved_chunks=chunks,
            steps_taken=state.steps_taken + 1,
        )
    except Exception as exc:
        logger.warning("summarizer_node_failed", extra={"extra_fields": {"error": str(exc)}})
        return state.copy_with(
            draft_answer="I couldn't summarize that document.",
            error=str(exc),
            steps_taken=state.steps_taken + 1,
        )


async def synthesizer_node(
    state: AgentState,
    context: GraphContext | None = None,
) -> AgentState:
    """Synthesizes an answer using LLM with prompt injection delimiters & reflection."""
    # If conversational fast path already set draft_answer, construct final response
    if isinstance(state.plan, dict) and state.plan.get("action") == "conversational":
        answer = state.draft_answer or "Hello! How can I assist you with your documents?"
        chat_resp = ChatResponse(
            answer=answer,
            retrieved_chunks=[],
            sources=[],
            processing_time=0.0,
            tool_used="conversational",
            steps_taken=state.steps_taken + 1,
            session_id=state.session_id or "",
        )
        return state.copy_with(
            draft_answer=answer,
            final_response=chat_resp,
            steps_taken=state.steps_taken + 1,
        )

    if not context or not context.llm_client:
        answer = state.draft_answer or "Synthesizer LLM unavailable."
        return state.copy_with(
            draft_answer=answer,
            steps_taken=state.steps_taken + 1,
        )

    # Empty context check
    if not state.retrieved_chunks and not state.web_results:
        answer = FALLBACK_REPLY
        chat_resp = ChatResponse(
            answer=answer,
            retrieved_chunks=[],
            sources=[],
            processing_time=0.0,
            tool_used="retrieval",
            steps_taken=state.steps_taken + 1,
            session_id=state.session_id or "",
            retrieval_confidence="insufficient",
        )
        return state.copy_with(
            draft_answer=answer,
            final_response=chat_resp,
            steps_taken=state.steps_taken + 1,
        )

    extra_instruction = None
    if state.reflection_count > 0:
        extra_instruction = (
            f"{REFLECTION_INSTRUCTION} "
            "Ensure all cited claims strictly match the provided excerpts."
        )

    prompt = build_prompt(
        query=state.query,
        chunks=state.retrieved_chunks,
        history=state.history,
        extra_instruction=extra_instruction,
        web_results=state.web_results,
        persona=state.persona,
    )

    try:
        raw_answer = context.llm_client.generate(prompt)
        answer = strip_sources_section(raw_answer)
    except Exception as exc:
        logger.error("synthesizer_llm_failed", extra={"extra_fields": {"error": str(exc)}})
        answer = FALLBACK_REPLY

    # Build structured sources
    sources: list[SourceReference] = []
    if state.retrieved_chunks:
        sources.extend(_source_references(state.retrieved_chunks, start=1))
    if state.web_results:
        sources.extend(_web_source_references(state.web_results, start=len(sources) + 1))

    answer_source = "documents"
    if state.web_results and not state.retrieved_chunks:
        answer_source = "web"
    elif state.web_results and state.retrieved_chunks:
        answer_source = "mixed"

    chat_resp = ChatResponse(
        answer=answer,
        retrieved_chunks=state.retrieved_chunks,
        sources=sources,
        processing_time=0.0,
        tool_used="agent_graph",
        steps_taken=state.steps_taken + 1,
        answer_source=answer_source,
        session_id=state.session_id or "",
    )

    return state.copy_with(
        draft_answer=answer,
        final_response=chat_resp,
        steps_taken=state.steps_taken + 1,
    )


async def fact_checker_node(
    state: AgentState,
    context: GraphContext | None = None,
) -> AgentState:
    """Verifies answer citations and claims against ground-truth source chunks."""
    answer = state.draft_answer
    chunks = state.retrieved_chunks
    web_results = state.web_results

    if not answer or (not chunks and not web_results):
        return state.copy_with(
            fact_check_result={"verified": True, "skipped": True, "reason": "no_citations_needed"},
            steps_taken=state.steps_taken + 1,
        )

    citation_numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    if not citation_numbers:
        return state.copy_with(
            fact_check_result={"verified": True, "skipped": True, "reason": "no_inline_citations"},
            steps_taken=state.steps_taken + 1,
        )

    all_texts = {i + 1: c.text for i, c in enumerate(chunks)}
    start_web = len(chunks) + 1
    for i, w in enumerate(web_results):
        all_texts[start_web + i] = w.snippet

    # Check for non-existent citation references
    invalid_citations = [n for n in citation_numbers if n not in all_texts]
    if invalid_citations:
        return state.copy_with(
            fact_check_result={
                "verified": False,
                "score": 0.0,
                "invalid_citations": invalid_citations,
                "reason": "hallucinated_citation_index",
            },
            reflection_count=state.reflection_count + 1,
            steps_taken=state.steps_taken + 1,
        )

    if not settings.citation_verification_enabled or not context or not context.llm_client:
        return state.copy_with(
            fact_check_result={
                "verified": True,
                "skipped": True,
                "reason": "verification_disabled",
            },
            steps_taken=state.steps_taken + 1,
        )

    cited_pairs = [(n, all_texts[n]) for n in citation_numbers if n in all_texts]
    prompt = (
        "Answer:\n"
        + answer
        + "\n\n"
        + "\n\n".join(f"Excerpt [{n}]:\n{text}" for n, text in cited_pairs)
        + "\n\nFor each excerpt number above, does the answer's claim attributed to it "
        "match what that excerpt says? "
        'Respond with ONLY a JSON object like {"1": true, "2": false}.'
    )

    try:
        import json

        raw = context.llm_client.generate(prompt)
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        verifications = json.loads(raw)
        verified = all(bool(verifications.get(str(n), True)) for n, _ in cited_pairs)
        score = sum(1 for n, _ in cited_pairs if verifications.get(str(n), True)) / len(cited_pairs)
        result = {"verified": verified, "score": score, "details": verifications}
    except Exception as exc:
        logger.warning(
            "fact_check_verification_failed", extra={"extra_fields": {"error": str(exc)}}
        )
        result = {"verified": True, "skipped": True, "reason": "parse_error"}

    return state.copy_with(
        fact_check_result=result,
        reflection_count=state.reflection_count + (0 if result["verified"] else 1),
        steps_taken=state.steps_taken + 1,
    )
