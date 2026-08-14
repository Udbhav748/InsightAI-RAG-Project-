"""Retrieval quality grading for Corrective RAG.

Evaluates the relevance and sufficiency of retrieved document chunks
based on chunk count and similarity scores:
- "good": Top retrieval score clears Settings.retrieval_grade_threshold
- "weak": Chunks found, but top score falls below threshold (eligible for web fallback)
- "insufficient": No chunks cleared min_score threshold
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.metrics import get_metrics
from app.models.document import RetrievedChunk

logger = logging.getLogger(__name__)


def grade_retrieval(
    query: str,
    chunks: list[RetrievedChunk],
    threshold: float | None = None,
) -> str:
    """Cheap heuristic grade of retrieval quality — no LLM call, a
    function of chunk count and top score alone. query is accepted for
    a future semantic grader but isn't used by this heuristic today.

    - "insufficient": nothing survived retrieval_service's min_score
      floor.
    - "weak": chunks survived that floor, but the top score is still
      below Settings.retrieval_grade_threshold — technically on-topic,
      not confidently so.
    - "good": top score clears the threshold.

    A "weak"/"insufficient" grade is what makes the web search fallback
    eligible to fire (see handle_query), if Settings.web_search_enabled.
    """
    thresh = threshold if threshold is not None else settings.retrieval_grade_threshold
    if not chunks:
        grade, top_score = "insufficient", None
    else:
        top_score = max(chunk.score for chunk in chunks)
        grade = "good" if top_score >= thresh else "weak"

    logger.info(
        "retrieval_graded",
        extra={
            "extra_fields": {"grade": grade, "top_score": top_score, "chunk_count": len(chunks)}
        },
    )
    get_metrics().record_retrieval_grade(grade)
    return grade


class RetrievalGrader:
    """Evaluates retrieval quality against configured thresholds."""

    def __init__(self, threshold: float | None = None) -> None:
        self._threshold = threshold

    def grade(self, query: str, chunks: list[RetrievedChunk]) -> str:
        return grade_retrieval(query, chunks, threshold=self._threshold)
