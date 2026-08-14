"""Query intent planning, small-talk detection, and action classification for RAG.

Extracts intent routing from the monolithic rag_service:
- Small-talk and conversational canned reply matching
- Document summarization command detection (uuid extraction)
- Diagnostic query formulation from vision predictions
- LLM-assisted routing with fallback to deterministic keyword planner
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.models.document import VisionPrediction
from app.services.prompt_injection_service import detect_possible_injection

if TYPE_CHECKING:
    from app.services.router_agent import RouterAgent

logger = logging.getLogger(__name__)


@dataclass
class PlanDecision:
    action: str  # "conversational" | "retrieve" | "summarize" | "diagnose"
    document_id: str | None = None


# Each entry is (normalized exact phrases, canned response). Checked in
# order; the query must match one of the phrases entirely (after
# normalization) — a real question that merely contains a word like
# "thanks" mid-sentence should still go to the RAG pipeline.
_CONVERSATIONAL_INTENTS = [
    (
        {"hi", "hey", "yo", "hiya"},
        "Hi! I'm InsightAI. How can I help you with your uploaded documents today?",
    ),
    (
        {"hello", "good morning", "good afternoon", "good evening"},
        "Hello! Upload a document or ask me a question about one you've already uploaded.",
    ),
    (
        {"thanks", "thank you", "thanks a lot", "thank you so much", "many thanks"},
        "You're welcome! Let me know if you need help understanding anything in your documents.",
    ),
    (
        {"bye", "goodbye", "see you", "see ya", "farewell"},
        "Goodbye! Come back anytime you have questions about your documents.",
    ),
    (
        {"who are you", "what are you"},
        "I'm InsightAI, an AI-powered document assistant. I can analyze your uploaded "
        "documents, answer questions, summarize content, and help you quickly find "
        "information.",
    ),
    (
        {"what can you do", "help", "how do you work", "what do you do"},
        "I can:\n"
        "- Answer questions from uploaded PDFs\n"
        "- Summarize documents\n"
        "- Explain concepts\n"
        "- Find important information\n"
        "- Help you study or review documents",
    ),
    # Meta/status remarks — the user is checking whether the bot is
    # working or venting about it, not asking a document question. Without
    # this, these fall through to retrieve and (depending on min_score)
    # can return an odd, technically-grounded-but-irrelevant answer built
    # from whatever chunk happened to score highest.
    (
        {
            "why not responding",
            "why are you not responding",
            "why aren't you responding",
            "why is this not responding",
            "why isn't this working",
            "why is this not working",
            "this is not working",
            "this isn't working",
            "not working",
            "are you there",
            "are you working",
            "is this working",
            "is this thing working",
            "hello are you there",
            "anyone there",
            "is anyone there",
            "did you get my message",
            "what happened",
            "what happend",
            "did that work",
        },
        "I'm here and working — I just didn't find anything relevant to that in "
        "your uploaded documents. Try asking a specific question about what's in "
        'them, like "what does this document say about...".',
    ),
]

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

# Matches "summarize"/"summarise"/"summary" anywhere in the query.
_SUMMARIZE_RE = re.compile(r"\bsummar(?:y|ize|ise)\b", re.IGNORECASE)

# A document_id is a uuid4 (see upload_service.save_uploaded_file) — this
# is how a "summarize" query names which document it means. Queries that
# mention "summarize" without one fall back to the normal retrieve action:
# there's no document-name index to resolve a title against.
_DOCUMENT_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def normalize_query(query: str) -> str:
    """Strip punctuation, normalize whitespace, and lowercase the query."""
    stripped = _PUNCTUATION_RE.sub("", query.lower())
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def match_conversational_reply(query: str) -> str | None:
    """Return a canned reply if query is small talk, else None."""
    normalized = normalize_query(query)
    for phrases, response in _CONVERSATIONAL_INTENTS:
        if normalized in phrases:
            return response
    return None


def build_diagnosis_query(prediction: VisionPrediction, user_query: str | None) -> str:
    """Turn a vision prediction into the query fed to the existing
    retrieval pipeline. Includes crop, not just disease name: several
    LeafSense classes share a disease name across crops (e.g.
    "Bacterial_spot" exists for both peach and tomato, with different
    corpus content), so crop alone disambiguates which document's chunks
    should actually match."""
    base = (
        f"{prediction.disease} on {prediction.crop}"
        if prediction.disease != "healthy"
        else f"healthy {prediction.crop}"
    )
    return f"{base}. {user_query}" if user_query else base


def plan_query(query: str, history: list[dict[str, str]] | None = None) -> PlanDecision:
    """Decide which tool this query needs.

    Plain keyword/regex checks — no LLM call, no external planner.
    history is accepted for a future planner that considers context,
    but isn't used by these checks today.
    """
    if match_conversational_reply(query) is not None:
        return PlanDecision(action="conversational")

    if _SUMMARIZE_RE.search(query):
        match = _DOCUMENT_ID_RE.search(query)
        if match:
            return PlanDecision(action="summarize", document_id=match.group(0))

    return PlanDecision(action="retrieve")


def route_query(
    query: str,
    history: list[dict[str, str]] | None = None,
    router_agent: RouterAgent | None = None,
    fallback_plan: PlanDecision | None = None,
) -> PlanDecision:
    """Decide the query's action: the keyword planner, upgraded by the
    LLM router agent when Settings.agent_routing_enabled.

    The router can return "research" — the one action the regex
    planner can't express — and degrades to the planner's decision on
    any failure, so routing is additive, never a new failure mode.
    """
    injection_categories = detect_possible_injection(query)
    if injection_categories:
        logger.warning(
            "possible_injection_detected",
            extra={"extra_fields": {"source": "query", "categories": injection_categories}},
        )

    plan = fallback_plan if fallback_plan is not None else plan_query(query, history)
    if not settings.agent_routing_enabled or router_agent is None:
        return plan
    routed = router_agent.decide(query, history)
    if routed.action != plan.action or routed.document_id != plan.document_id:
        logger.info(
            "router_decision",
            extra={
                "extra_fields": {
                    "planner_action": plan.action,
                    "routed_action": routed.action,
                    "document_id": routed.document_id,
                    "query_length": len(query),
                }
            },
        )
    return PlanDecision(action=routed.action, document_id=routed.document_id)


class QueryRouter:
    """Orchestrates query intent planning and agent routing."""

    def __init__(self, router_agent: RouterAgent | None = None) -> None:
        self._router_agent = router_agent

    def plan(self, query: str, history: list[dict[str, str]] | None = None) -> PlanDecision:
        return plan_query(query, history)

    def route(self, query: str, history: list[dict[str, str]] | None = None) -> PlanDecision:
        return route_query(query, history, router_agent=self._router_agent)
