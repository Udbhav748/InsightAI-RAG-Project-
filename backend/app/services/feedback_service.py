"""Appends chat feedback events (thumbs up/down, plus an optional detailed
rubric review) to a local JSONL file.

No database: feedback is low-volume and append-only for this project's
scale, so one file plus eval/metrics_report.py reading it back to compute
Acceptance Rate (and, for rubric-bearing events, per-criterion averages
and Inter-Annotator Agreement) is enough. Mirrors upload_service.py's
path convention (a directory name from Settings, resolved relative to
backend/).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

FEEDBACK_DIR = Path(__file__).resolve().parents[2] / settings.feedback_dir_name
FEEDBACK_PATH = FEEDBACK_DIR / settings.feedback_filename

logger = logging.getLogger(__name__)


def record_feedback(
    message_id: str,
    rating: str,
    comment: str | None,
    reviewer_id: str | None = None,
    rubric: dict | None = None,
) -> None:
    """reviewer_id identifies who submitted this judgment — resolved from
    the authenticated caller's client_name (see query.py's submit_feedback),
    never client-supplied, so one API key can't pose as multiple reviewers
    to game Inter-Annotator Agreement. None for older/non-rubric callers;
    such events are excluded from agreement (see
    eval/metrics_report.py.report_inter_annotator_agreement) since "who
    agrees with whom" is undefined without knowing who "who" is.

    rubric, when given, is RubricScores.model_dump() — the seven 1-5
    per-criterion scores (see app/models/schemas.py).
    """
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
        "rating": rating,
        "comment": comment,
        "reviewer_id": reviewer_id,
        "rubric": rubric,
    }

    with FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")

    logger.debug(
        "feedback_written",
        extra={
            "extra_fields": {
                "message_id": message_id,
                "rating": rating,
                "reviewer_id": reviewer_id,
                "has_rubric": rubric is not None,
            }
        },
    )
