"""Rollup + alert thresholds for the backend's JSON logs.

A tiny, dependency-free stand-in for a hosted monitoring/alerting stack:
aggregates a captured log file (same format as metrics_report.py consumes)
into a windowed health rollup — error rate, latency percentiles, token/cost
totals — and fails (exit 1) if any configured threshold is breached, which a
scheduled job (cron / GitHub Actions) can turn into an alert.

This is explicitly NOT a replacement for Prometheus/Grafana: it's
pull-on-demand over a file, with no long-term storage, no dashboards, and
no push alerting. See docs/CHECKLIST.md §10.

Usage (from backend/):
    python monitoring/log_aggregate.py app.log
    python monitoring/log_aggregate.py app.log --window-min 30 --json

Exit codes: 0 = within thresholds, 1 = threshold breached.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Default thresholds (set each via --*. Values are the alert limit; breaching
# any of them flips the run to "alert").
DEFAULT_ERROR_RATE = 0.05       # fraction of requests that failed
DEFAULT_P95_LATENCY_MS = 5000.0 # p95 of processing_duration
DEFAULT_LOOP_CAPPED_RATE = 0.2  # fraction of requests that hit the loop cap


def _load_records(path: str) -> list[dict]:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def aggregate(records: list[dict], window_min: float = 0.0) -> dict:
    from datetime import datetime, timezone

    # Optionally narrow to the trailing window by timestamp field.
    if window_min > 0:
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
        filtered = []
        for rec in records:
            ts = rec.get("timestamp")
            if not ts:
                continue
            try:
                parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed >= cutoff:
                filtered.append(rec)
        records = filtered

    total_requests = 0
    failures = 0
    by_category = {}
    durations = []
    loop_capped = 0
    tokens_in = tokens_out = 0
    cost = 0.0
    tool_attempts = {}  # tool -> total invocations
    tool_successes = {}

    for rec in records:
        msg = rec.get("message", "")
        if msg == "request_failed":
            total_requests += 1
            failures += 1
            cat = rec.get("taxonomy_category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        elif msg == "chat_query_handled":
            total_requests += 1
            duration = rec.get("processing_duration")
            if duration is not None:
                durations.append(float(duration))
        if msg == "loop_capped":
            loop_capped += 1
        if msg == "llm_generation_completed":
            tokens_in += int(rec.get("prompt_tokens", 0) or 0)
            tokens_out += int(rec.get("completion_tokens", 0) or 0)
            cost += float(rec.get("estimated_cost_usd", 0.0) or 0.0)
        if msg == "tool_invocation":
            tool = rec.get("tool", "unknown")
            tool_attempts[tool] = tool_attempts.get(tool, 0) + 1
            if rec.get("success") is True:
                tool_successes[tool] = tool_successes.get(tool, 0) + 1

    error_rate = failures / total_requests if total_requests else 0.0
    loop_capped_rate = loop_capped / total_requests if total_requests else 0.0
    tool_success_rate = {
        tool: (tool_successes.get(tool, 0) / attempts if attempts else 0.0)
        for tool, attempts in tool_attempts.items()
    }
    return {
        "records_scanned": len(records),
        "requests": total_requests,
        "failures": failures,
        "error_rate": round(error_rate, 4),
        "error_rate_by_category": by_category,
        "p50_latency_ms": round(_percentile(durations, 50), 1),
        "p95_latency_ms": round(_percentile(durations, 95), 1),
        "p99_latency_ms": round(_percentile(durations, 99), 1),
        "loop_capped_rate": round(loop_capped_rate, 4),
        "tool_attempts": tool_attempts,
        "tool_successes": tool_successes,
        "tool_success_rate": tool_success_rate,
        "total_tokens": tokens_in + tokens_out,
        "estimated_cost_usd": round(cost, 6),
    }


def _breaches(agg: dict, max_error: float, max_p95: float, max_loop: float, min_tool_success: float = 0.8) -> list[str]:
    problems = []
    if agg["error_rate"] > max_error:
        problems.append(f"error_rate {agg['error_rate']:.4f} > {max_error}")
    if agg["p95_latency_ms"] > max_p95:
        problems.append(f"p95_latency {agg['p95_latency_ms']:.1f}ms > {max_p95}ms")
    if agg["loop_capped_rate"] > max_loop:
        problems.append(f"loop_capped_rate {agg['loop_capped_rate']:.4f} > {max_loop}")
    for tool, rate in agg["tool_success_rate"].items():
        if rate < min_tool_success:
            problems.append(f"tool_success_rate({tool}) {rate:.4f} < {min_tool_success}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile", help="Path to a captured backend JSON log file.")
    parser.add_argument("--window-min", type=float, default=0.0, help="Only aggregate records within the trailing N minutes (0 = all).")
    parser.add_argument("--max-error-rate", type=float, default=DEFAULT_ERROR_RATE)
    parser.add_argument("--max-p95-latency-ms", type=float, default=DEFAULT_P95_LATENCY_MS)
    parser.add_argument("--max-loop-capped-rate", type=float, default=DEFAULT_LOOP_CAPPED_RATE)
    parser.add_argument("--min-tool-success-rate", type=float, default=0.8)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text.")
    args = parser.parse_args()

    records = _load_records(args.logfile)
    agg = aggregate(records, window_min=args.window_min)
    problems = _breaches(
        agg, args.max_error_rate, args.max_p95_latency_ms, args.max_loop_capped_rate, args.min_tool_success_rate
    )

    if args.json:
        print(json.dumps({"aggregate": agg, "alerts": problems, "alert": bool(problems)}))
    else:
        print(f"records scanned : {agg['records_scanned']}")
        print(f"requests        : {agg['requests']}  failures: {agg['failures']}  "
              f"error_rate: {agg['error_rate']:.4f}  by_category: {agg['error_rate_by_category']}")
        print(f"latency (ms)    : p50={agg['p50_latency_ms']}  p95={agg['p95_latency_ms']}  p99={agg['p99_latency_ms']}")
        print(f"loop capped rate: {agg['loop_capped_rate']:.4f}")
        print(f"tool success    : {agg['tool_success_rate']}")
        print(f"tokens / cost   : {agg['total_tokens']} / ${agg['estimated_cost_usd']:.6f}")
        if problems:
            print("ALERTS BREACHED:")
            for p in problems:
                print(f"  - {p}")
        else:
            print("Within thresholds.")

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
