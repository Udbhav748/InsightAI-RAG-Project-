"""Regression gate for eval results.

Compares a freshly-produced eval result JSON (run_eval.py output) against a
committed baseline and fails (exit code 1) if any tracked metric regressed
beyond tolerance. Designed to run in CI (eval.yml) after `run_eval.py` so a
change that degrades answer quality can't merge silently.

Usage (from backend/):
    python eval/regression_check.py --results eval/results/<new>.json \
        --baseline eval/baselines/v1_v2_groq.json

Metrics compared (when present in both files):

    Higher-is-better (regression = value dropped by more than tol):
        planner.accuracy, planner.macro_f1, planner.weighted_f1,
        task_success_rate, groundedness_proxy, entailment_groundedness,
        injection_resistance, source_accuracy, precision_at_5, recall_at_5,
        mrr, hit_rate_at_5, citation_accuracy, tool_arg_accuracy

    Lower-is-better (regression = value rose by more than tol):
        false_refusal_rate, data_leak_rate

A missing metric in either file is skipped (new metrics on a fresh run have
no baseline yet; old runs predate them). Tolerances are absolute-percentage
for rates (0-1 scale) unless overridden with --tol. Exit codes:
    0 = no regression, 1 = regression detected, 2 = usage/input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HIGHER_IS_BETTER = [
    "task_success_rate",
    "groundedness_proxy",
    "entailment_groundedness",
    "injection_resistance",
    "source_accuracy",
    "precision_at_5",
    "recall_at_5",
    "mrr",
    "hit_rate_at_5",
    "citation_accuracy",
    "tool_arg_accuracy",
]

LOWER_IS_BETTER = [
    "false_refusal_rate",
    "data_leak_rate",
]

# Top-level metrics nested under a "planner" object, same HIGHER_IS_BETTER
# semantics as the flat list above.
PLANNER_METRICS = ["accuracy", "macro_f1", "weighted_f1"]


def _failures(results: dict, baseline: dict, tol: float) -> list[str]:
    problems: list[str] = []
    for key in HIGHER_IS_BETTER:
        new = results.get(key)
        old = baseline.get(key)
        if new is None or old is None:
            continue
        if old - new > tol:
            problems.append(f"{key}: {new:.4f} (baseline {old:.4f}) — dropped > {tol}")
    for key in LOWER_IS_BETTER:
        new = results.get(key)
        old = baseline.get(key)
        if new is None or old is None:
            continue
        if new - old > tol:
            problems.append(f"{key}: {new:.4f} (baseline {old:.4f}) — rose > {tol}")
    new_planner = results.get("planner") or {}
    old_planner = baseline.get("planner") or {}
    for key in PLANNER_METRICS:
        new = new_planner.get(key)
        old = old_planner.get(key)
        if new is None or old is None:
            continue
        if old - new > tol:
            problems.append(f"planner.{key}: {new:.4f} (baseline {old:.4f}) — dropped > {tol}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        required=True,
        help="New eval result JSON (run_eval.py output) to gate.",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Baseline result JSON to compare against.",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=0.05,
        help="Absolute regression tolerance on the 0-1 scale (default 0.05).",
    )
    args = parser.parse_args()

    try:
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"regression_check: could not load results/baseline: {exc}", file=sys.stderr)
        sys.exit(2)

    print(
        f"Comparing {args.results} vs baseline {args.baseline} "
        f"(tolerance {args.tol:.3f})"
    )
    problems = _failures(results, baseline, args.tol)
    if not problems:
        print("No regression detected.")
        sys.exit(0)

    print("REGRESSIONS DETECTED:")
    for problem in problems:
        print(f"  - {problem}")
    print("See backend/eval/README.md for how to re-baseline intentionally.")
    sys.exit(1)


if __name__ == "__main__":
    main()
