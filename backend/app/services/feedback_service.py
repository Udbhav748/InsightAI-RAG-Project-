"""Appends chat feedback events (thumbs up/down) to a local JSONL file.

No database: feedback is low-volume and append-only for this project's
scale, so one file plus eval/metrics_report.py reading it back to compute
Acceptance Rate is enough. Mirrors upload_service.py's path convention
(a directory name from Settings, resolved relative to backend/).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

FEEDBACK_DIR = Path(__file__).resolve().parents[2] / settings.feedback_dir_name
FEEDBACK_PATH = FEEDBACK_DIR / settings.feedback_filename

logger = logging.getLogger(__name__)


def record_feedback(message_id: str, rating: str, comment: str | None) -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
        "rating": rating,
        "comment": comment,
    }

    with FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")

    logger.debug(
        "feedback_written",
        extra={"extra_fields": {"message_id": message_id, "rating": rating}},
    )
