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
    """Loop Count / Average Steps, from the chat_query_handled event
    (see rag_service.py's ChatService._respond) that every /chat and
    /chat/stream response logs regardless of which action the planner
    picked.

    Average Steps is a flat mean of steps_taken across every event,
    matching how the field is already surfaced as one number per response
    (see the README's API reference) rather than broken out per query_type.

    Loop Count only applies to query_type == "document_query" — the only
    path that ever calls ChatService._correct()/_correct_streamed().
    "conversational" and "summarize" requests always report a fixed
    steps_taken (1 and 3 respectively) and never loop. A document_query
    request "looped" when steps_taken exceeds 4 (planning + retrieval +
    grading + generation — the deterministic path when the corrective
    loop finds nothing to fix): anything above that means a reflection
    retry and/or the web-search fallback actually fired.

    One caveat: with Settings.web_search_enabled=True (off by default),
    a "weak"/"insufficient" grade also adds a step for an eager
    pre-generation web search fetch (see handle_query's docstring on why
    that's deliberately separate from _correct's own fallback) — that
    step is indistinguishable from a real loop iteration using
    steps_taken alone, so with web search enabled this slightly
    overcounts "looped". Not a concern at this project's default config.
    """
    handled = [record for record in records if record.get("message") == "chat_query_handled"]

    print("=== Loop Count / Average Steps ===")
    if not handled:
        print("No chat_query_handled entries found in the logs.\n")
        return

    all_steps = [record.get("steps_taken", 0) for record in handled]
    avg_steps = sum(all_steps) / len(all_steps)

    document_queries = [record for record in handled if record.get("query_type") == "document_query"]
    looped = [record for record in document_queries if record.get("steps_taken", 0) > 4]

    print(f"  requests (all types):    {len(handled)}")
    print(f"  average steps:           {avg_steps:.2f}")
    print(f"  document_query requests: {len(document_queries)}")
    loop_line = f"  loop count:              {len(looped)}"
    if document_queries:
        loop_line += f"  ({len(looped) / len(document_queries) * 100:.1f}% of document_query requests)"
    print(loop_line)
    print()


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
    report_tokens_and_cost(records)
    report_acceptance_rate(Path(args.feedback_file))


if __name__ == "__main__":
    main()
