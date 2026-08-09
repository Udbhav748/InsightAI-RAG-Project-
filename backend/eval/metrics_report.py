"""Parses the backend's JSON logs and prints a lightweight metrics report:
latency percentiles, error rate by taxonomy_category, corrective-RAG Loop
Count and Average Steps, total LLM token usage/cost, and Acceptance Rate
from chat feedback.

This is a stand-in for real observability, not a replacement for it — in
production you'd ship these same structured log lines to something like
Prometheus/Grafana (metrics + dashboards + alerting) instead of grepping
log files after the fact. This script exists so the numbers are
inspectable locally without standing up that infrastructure.

Each line of input is expected to be one JSON object, as emitted by
app.core.logging.JSONFormatter — i.e. the backend's own stdout.

Usage (from backend/):
    uvicorn app.main:app | tee app.log   # in one terminal, generate traffic
    python eval/metrics_report.py app.log   # in another

    # or pipe directly:
    cat app.log | python eval/metrics_report.py

Acceptance Rate is read separately, from backend/feedback/feedback.jsonl
(written by POST /chat/feedback — see app/services/feedback_service.py),
not from the log file argument above:
    python eval/metrics_report.py app.log --feedback-file feedback/feedback.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Mirrors Settings.feedback_dir_name / feedback_filename's defaults
# (app/core/config.py) without importing app.core.config itself — this
# script is otherwise dependency-free (no .env/Settings needed to just
# parse log files), and the default here is only a convenience;
# --feedback-file overrides it for a non-default FEEDBACK_DIR_NAME.
DEFAULT_FEEDBACK_PATH = Path(__file__).resolve().parents[1] / "feedback" / "feedback.jsonl"


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. No numpy/scipy dependency for a script this small."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def parse_log_lines(lines: list[str]) -> list[dict]:
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # Non-JSON lines (e.g. a stray print, uvicorn's startup banner
            # if it slipped into the same stream) are skipped rather than
            # crashing the whole report over one bad line.
            continue
    return records


def report_latency(records: list[dict]) -> None:
    by_event = defaultdict(list)
    for record in records:
        duration = record.get("processing_duration")
        if isinstance(duration, (int, float)):
            by_event[record.get("message", "unknown")].append(duration)

    all_durations = [duration for durations in by_event.values() for duration in durations]

    print("=== Latency (processing_duration, seconds) ===")
    if not all_durations:
        print("No processing_duration values found in the logs.\n")
        return

    print(
        f"overall (n={len(all_durations)}): "
        f"P50={_percentile(all_durations, 50):.4f}  "
        f"P95={_percentile(all_durations, 95):.4f}  "
        f"P99={_percentile(all_durations, 99):.4f}"
    )
    for event, durations in sorted(by_event.items()):
        print(
            f"  {event:<32s} (n={len(durations):>4d}): "
            f"P50={_percentile(durations, 50):.4f}  "
            f"P95={_percentile(durations, 95):.4f}  "
            f"P99={_percentile(durations, 99):.4f}"
        )
    print()


def report_error_rate_by_category(records: list[dict]) -> None:
    errors = [record for record in records if record.get("message") == "request_failed"]

    print("=== Error rate by taxonomy_category ===")
    if not errors:
        print("No request_failed entries found in the logs.\n")
        return

    counts: dict[str, int] = defaultdict(int)
    for error in errors:
        counts[error.get("taxonomy_category", "unknown")] += 1

    total = len(errors)
    for category, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {category:<12s} {count:>4d}  ({count / total * 100:.1f}% of errors)")
    print(f"  {'total':<12s} {total:>4d}")
    print()


def report_loop_count_and_avg_steps(records: list[dict]) -> None:
    """Average Steps and loop_capped rate, from two events ChatService
    already logs — no new logging needed, this only aggregates fields
    that exist today:

    - chat_query_handled (ChatService._respond, one per /chat or
      /chat/stream response): its steps_taken field is averaged across
      every request regardless of query_type, matching how the field is
      already surfaced as one number per response (see the README's API
      reference).
    - loop_capped (ChatService._correct/_correct_streamed,
      rag_service.py): logged specifically when the corrective loop hits
      Settings-independent _MAX_LLM_CALLS (3) generate() calls without
      resolving — i.e. the loop was forced to stop and return whatever
      answer it had, rather than looping freely. This is a narrower,
      more precise signal than "did the loop run at all" (most
      reflection/web-fallback iterations resolve well under the cap and
      never log this event) — it specifically flags requests where the
      cap, not the model being satisfied, ended the loop.

    The fraction is loop_capped events over chat_query_handled requests:
    both are counted straight from the same parsed log stream, so no
    correlation by request id is needed (there's exactly one
    chat_query_handled per request, and at most one loop_capped per
    request since hitting the cap ends the loop immediately).
    """
    handled = [record for record in records if record.get("message") == "chat_query_handled"]
    capped = [record for record in records if record.get("message") == "loop_capped"]

    print("=== Loop Count / Average Steps ===")
    if not handled:
        print("No chat_query_handled entries found in the logs.\n")
        return

    all_steps = [record.get("steps_taken", 0) for record in handled]
    avg_steps = sum(all_steps) / len(all_steps)
    capped_rate = len(capped) / len(handled)

    print(f"  requests:            {len(handled)}")
    print(f"  average steps:       {avg_steps:.2f}")
    print(f"  loop_capped events:  {len(capped)}  ({capped_rate * 100:.1f}% of requests)")
    print()


def report_retry_success_rate(records: list[dict]) -> None:
    """Retry Success Rate, from two events the LLM clients already emit:

    - llm_generation_retrying (GeminiClient/GroqClient._log_retry,
      tenacity's before_sleep) — logged once per retry attempt.
    - llm_generation_completed — logged on a successful generation.

    A "retry event" is correlated to its eventual outcome by request_id
    (set by the request middleware on every log line). A request that
    logged >=1 retry and >=1 completed generation counts as a retry
    success; a request that retried and produced no completed generation
    counts as a retry failure. Records without a request_id (off-request
    calls) are correlated by a time-window fallback: a completed
    generation within RETRY_WINDOW_SECONDS of a retry counts as the
    retry's outcome.

    The checklist's Retry Success Rate: the fraction of retried requests
    whose retries ended in a successful generation.
    """
    retries = [record for record in records if record.get("message") == "llm_generation_retrying"]
    completed = [record for record in records if record.get("message") == "llm_generation_completed"]

    print("=== Retry Success Rate ===")
    if not retries:
        print("No llm_generation_retrying entries found in the logs.\n")
        return

    completed_ids = {record.get("request_id") for record in completed if record.get("request_id")}
    success_ids: set[str] = set()
    failure_ids: set[str] = set()

    for record in retries:
        request_id = record.get("request_id")
        if request_id:
            (success_ids if request_id in completed_ids else failure_ids).add(request_id)
        else:
            # No request_id context (e.g. a call outside a request): fall
            # back to a time window — the retry "succeeded" if any
            # completed generation appears within RETRY_WINDOW_SECONDS.
            retry_time = record.get("timestamp")
            completed_time = next(
                (c.get("timestamp") for c in completed if _within_window(retry_time, c.get("timestamp"))),
                None,
            )
            (success_ids if completed_time else failure_ids).add(f"unid:{retry_time or 'unknown'}")

    total = len(success_ids) + len(failure_ids)
    success_rate = len(success_ids) / total if total else 0.0

    print(f"  retry events:             {len(retries)}")
    print(f"  retried requests:         {total}")
    print(f"  retry successes:          {len(success_ids)}")
    print(f"  retry failures:           {len(failure_ids)}")
    print(f"  Retry Success Rate:       {success_rate:.4f} ({success_rate * 100:.1f}%)")
    print()


RETRY_WINDOW_SECONDS = 60.0


def _within_window(a: str | None, b: str | None) -> bool:
    """True if ISO timestamps a and b are within RETRY_WINDOW_SECONDS.

    String comparison is unsafe across offsets, so parse both to epoch
    seconds. Any parse failure returns False (conservative: no match).
    """
    if not a or not b:
        return False
    try:
        a_ts = datetime.fromisoformat(a.replace("Z", "+00:00")).timestamp()
        b_ts = datetime.fromisoformat(b.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return False
    return abs(a_ts - b_ts) <= RETRY_WINDOW_SECONDS


def report_tokens_and_cost(records: list[dict]) -> None:
    generations = [
        record for record in records if record.get("message") == "llm_generation_completed"
    ]

    print("=== Token usage & estimated cost ===")
    if not generations:
        print("No llm_generation_completed entries found in the logs.\n")
        return

    prompt_tokens = sum(record.get("prompt_tokens", 0) or 0 for record in generations)
    completion_tokens = sum(record.get("completion_tokens", 0) or 0 for record in generations)
    total_tokens = sum(record.get("total_tokens", 0) or 0 for record in generations)
    total_cost = sum(record.get("estimated_cost_usd", 0) or 0 for record in generations)

    print(f"  generations:        {len(generations)}")
    print(f"  prompt tokens:      {prompt_tokens}")
    print(f"  completion tokens:  {completion_tokens}")
    print(f"  total tokens:       {total_tokens}")
    print(f"  estimated cost:     ${total_cost:.6f}")
    print()


def report_acceptance_rate(feedback_path: Path) -> None:
    """Acceptance Rate = thumbs-up ÷ total feedback events — the LLMOps
    acceptance-rate metric. Reads backend/feedback/feedback.jsonl, one
    JSON feedback event per line (see app/services/feedback_service.py)."""
    print("=== Acceptance Rate (chat feedback) ===")
    if not feedback_path.is_file():
        print(f"No feedback file found at {feedback_path}.\n")
        return

    lines = feedback_path.read_text(encoding="utf-8").splitlines()
    events = parse_log_lines(lines)
    ratings = [event.get("rating") for event in events]
    ups = sum(1 for rating in ratings if rating == "up")
    downs = sum(1 for rating in ratings if rating == "down")
    total = ups + downs

    if total == 0:
        print("No feedback events found.\n")
        return

    acceptance_rate = ups / total
    print(f"  up:               {ups}")
    print(f"  down:             {downs}")
    print(f"  total:            {total}")
    print(f"  Acceptance Rate:  {acceptance_rate:.4f} ({acceptance_rate * 100:.1f}%)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Path to a JSON log file (one JSON object per line). Reads stdin if omitted.",
    )
    parser.add_argument(
        "--feedback-file",
        default=str(DEFAULT_FEEDBACK_PATH),
        help=f"Path to the feedback JSONL file (default: {DEFAULT_FEEDBACK_PATH}).",
    )
    args = parser.parse_args()

    if args.log_file:
        path = Path(args.log_file)
        if not path.is_file():
            raise SystemExit(f"Log file not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin.readlines()

    records = parse_log_lines(lines)
    if not records:
        raise SystemExit("No parseable JSON log lines found.")

    print(f"Parsed {len(records)} log lines.\n")
    report_latency(records)
    report_error_rate_by_category(records)
    report_loop_count_and_avg_steps(records)
    report_retry_success_rate(records)
    report_tokens_and_cost(records)
    report_acceptance_rate(Path(args.feedback_file))


if __name__ == "__main__":
    main()
