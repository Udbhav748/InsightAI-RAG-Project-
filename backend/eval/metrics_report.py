"""Parses the backend's JSON logs and prints a lightweight metrics report:
latency percentiles, error rate by taxonomy_category, and total LLM token
usage/cost.

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
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Path to a JSON log file (one JSON object per line). Reads stdin if omitted.",
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
    report_tokens_and_cost(records)


if __name__ == "__main__":
    main()
