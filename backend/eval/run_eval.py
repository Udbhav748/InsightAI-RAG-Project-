"""Evaluation harness for ChatService's planner and answers.

Runs every entry in a dataset file (see eval/README.md) through
ChatService._plan (for planner classification) and ChatService.handle_query
(for the actual answer), then reports:

- a confusion matrix + accuracy/precision/recall/F1 for planner routing
- Task Success Rate: does the answer contain an expected keyword?
- Groundedness proxy: for retrieval answers, do they share vocabulary with
  the chunks that were actually retrieved?
- Injection Resistance: for adversarial entries, did the answer avoid
  complying with the injected instruction?

Requires a real GEMINI_API_KEY (this calls the live LLM) and at least one
document already indexed in the backend's vector store — see
eval/README.md for both preconditions.

Usage (from backend/):
    python eval/run_eval.py
    python eval/run_eval.py --dataset dataset_v2.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.exceptions import AppError, VectorStoreNotFoundError  # noqa: E402
from app.models.document import RetrievedChunk  # noqa: E402
from app.services.faiss_vector_store import DEFAULT_METADATA_PATH, FAISSVectorStore  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.llm_provider import build_llm_client  # noqa: E402
from app.services.prompt_builder import PROMPT_VERSION  # noqa: E402
from app.services.rag_service import ChatService  # noqa: E402

ACTIONS = ["conversational", "retrieve", "summarize"]

_STOPWORDS = {
    "about", "after", "also", "before", "being", "between", "could", "couldn",
    "during", "everything", "explain", "however", "other", "should", "since",
    "their", "there", "these", "third", "those", "though", "through", "under",
    "using", "which", "while", "would", "based", "context", "document",
    "documents", "provided", "answer", "question",
}


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{5,}", text.lower())
    return {word for word in words if word not in _STOPWORDS}


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def is_grounded(answer: str, chunks: list[RetrievedChunk]) -> bool:
    """Lexical-overlap proxy for groundedness: does the answer share at
    least one non-trivial word with the chunks it was supposedly built
    from? This is NOT a faithfulness/entailment check — an answer can
    share vocabulary with its context while still misrepresenting it, and
    a correct refusal (FALLBACK_REPLY) will usually score as ungrounded
    even though refusing was the right call. See eval/README.md."""
    answer_words = _content_words(answer)
    if not answer_words:
        return False
    chunk_words: set[str] = set()
    for chunk in chunks:
        chunk_words |= _content_words(chunk.text)
    return bool(answer_words & chunk_words)


def discover_document_id() -> str:
    """Pick the document with the most indexed chunks.

    Several small/near-empty documents (e.g. a PDF with almost no
    extractable text) can already be sitting in the store alongside the
    real target document. Taking metadata[0] would pick whichever was
    uploaded first, which is often one of those — using the most-chunked
    document is a much better proxy for "the substantive document this
    dataset was written against."
    """
    if not DEFAULT_METADATA_PATH.is_file():
        raise SystemExit(
            "No vector store found at "
            f"{DEFAULT_METADATA_PATH}. Upload at least one document via "
            "POST /upload before running the eval harness — see eval/README.md."
        )
    metadata = json.loads(DEFAULT_METADATA_PATH.read_text(encoding="utf-8"))
    if not metadata:
        raise SystemExit(
            "Vector store is empty. Upload at least one document via "
            "POST /upload before running the eval harness — see eval/README.md."
        )
    counts = Counter(record["document_id"] for record in metadata)
    return counts.most_common(1)[0][0]


def confusion_matrix(y_true: list[str], y_pred: list[str]) -> dict[str, dict[str, int]]:
    matrix = {actual: {predicted: 0 for predicted in ACTIONS} for actual in ACTIONS}
    for actual, predicted in zip(y_true, y_pred):
        matrix[actual][predicted] += 1
    return matrix


def classification_report(y_true: list[str], y_pred: list[str]) -> dict:
    per_class = {}
    for label in ACTIONS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        support = sum(1 for t in y_true if t == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    total = len(y_true)
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / total if total else 0.0
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)
    weighted_f1 = (
        sum(v["f1"] * v["support"] for v in per_class.values()) / total if total else 0.0
    )

    return {
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
    }


def run(dataset_path: Path) -> dict:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    vector_store = FAISSVectorStore()
    try:
        vector_store.load()
    except VectorStoreNotFoundError:
        raise SystemExit(
            "No vector store found. Upload at least one document via POST "
            "/upload before running the eval harness — see eval/README.md."
        ) from None
    if vector_store.total_vectors() == 0:
        raise SystemExit(
            "Vector store is empty. Upload at least one document via POST "
            "/upload before running the eval harness — see eval/README.md."
        )

    document_id = discover_document_id()
    # build_llm_client() reads Settings.llm_provider/fallback_llm_provider,
    # so switching LLM_PROVIDER in .env and re-running this script is the
    # entire A/B procedure documented in docs/OPERATIONS.md — no code
    # change needed here to eval a different provider.
    chat_service = ChatService(vector_store, build_llm_client())

    y_true: list[str] = []
    y_pred: list[str] = []
    task_success_flags: list[bool] = []
    grounded_flags: list[bool] = []
    injection_flags: list[bool] = []
    entries_out = []

    print(f"Running {len(dataset)} eval entries against document {document_id}...\n")

    for entry in dataset:
        query = entry["query"].replace("{{document_id}}", document_id)
        expected_action = entry["expected_action"]
        case_type = entry["case_type"]
        keywords = entry.get("expected_keywords") or []

        plan = chat_service._plan(query, history=None)
        y_true.append(expected_action)
        y_pred.append(plan.action)

        task_success = None
        grounded = None
        injection_resisted = None
        answer = ""
        tool_used = "none"
        steps_taken = 0
        error = None

        try:
            response = chat_service.handle_query(query, history=None)
            answer = response.answer
            tool_used = response.tool_used
            steps_taken = response.steps_taken

            if keywords:
                task_success = contains_any_keyword(answer, keywords)
                task_success_flags.append(task_success)

            if tool_used == "retrieval" and response.retrieved_chunks:
                grounded = is_grounded(answer, response.retrieved_chunks)
                grounded_flags.append(grounded)

            if case_type == "adversarial":
                marker = entry.get("injection_marker", "")
                injection_resisted = marker.lower() not in answer.lower()
                injection_flags.append(injection_resisted)
        except AppError as exc:
            error = str(exc)
            if keywords:
                task_success_flags.append(False)
                task_success = False
            if case_type == "adversarial":
                injection_flags.append(True)  # an error can't have complied
                injection_resisted = True

        status = "OK" if error is None else f"ERROR: {error}"
        print(f"[{case_type:11s}] {expected_action:>13s} -> {plan.action:<13s} | {query[:70]!r} | {status}")

        entries_out.append(
            {
                "query": entry["query"],
                "case_type": case_type,
                "expected_action": expected_action,
                "predicted_action": plan.action,
                "tool_used": tool_used,
                "steps_taken": steps_taken,
                "answer": answer,
                "error": error,
                "task_success": task_success,
                "grounded": grounded,
                "injection_resisted": injection_resisted,
            }
        )

    planner_report = classification_report(y_true, y_pred)
    matrix = confusion_matrix(y_true, y_pred)

    task_success_rate = (
        sum(task_success_flags) / len(task_success_flags) if task_success_flags else None
    )
    groundedness_proxy = (
        sum(grounded_flags) / len(grounded_flags) if grounded_flags else None
    )
    injection_resistance = (
        sum(injection_flags) / len(injection_flags) if injection_flags else None
    )

    report = {
        "dataset": dataset_path.name,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "llm_provider": settings.llm_provider,
        "fallback_llm_provider": settings.fallback_llm_provider,
        "prompt_version": PROMPT_VERSION,
        "document_id_used": document_id,
        "n_entries": len(dataset),
        "case_type_counts": dict(Counter(entry["case_type"] for entry in dataset)),
        "planner": {
            "confusion_matrix": matrix,
            **planner_report,
        },
        "task_success_rate": round(task_success_rate, 4) if task_success_rate is not None else None,
        "task_success_n": len(task_success_flags),
        "groundedness_proxy": round(groundedness_proxy, 4) if groundedness_proxy is not None else None,
        "groundedness_n": len(grounded_flags),
        "injection_resistance": round(injection_resistance, 4) if injection_resistance is not None else None,
        "injection_resistance_n": len(injection_flags),
        "entries": entries_out,
    }
    return report


def print_report(report: dict) -> None:
    print("\n" + "=" * 70)
    print("PLANNER CONFUSION MATRIX (rows = expected, cols = predicted)")
    print("=" * 70)
    header = " " * 16 + "".join(f"{action:>15s}" for action in ACTIONS)
    print(header)
    for actual in ACTIONS:
        row = report["planner"]["confusion_matrix"][actual]
        print(f"{actual:>15s} " + "".join(f"{row[predicted]:>15d}" for predicted in ACTIONS))

    print("\n" + "=" * 70)
    print("PLANNER CLASSIFICATION METRICS")
    print("=" * 70)
    print(f"{'class':>15s}{'precision':>12s}{'recall':>12s}{'f1':>12s}{'support':>10s}")
    for label, metrics in report["planner"]["per_class"].items():
        print(
            f"{label:>15s}{metrics['precision']:>12.4f}{metrics['recall']:>12.4f}"
            f"{metrics['f1']:>12.4f}{metrics['support']:>10d}"
        )
    print(f"\naccuracy:     {report['planner']['accuracy']:.4f}")
    print(f"macro F1:     {report['planner']['macro_f1']:.4f}")
    print(f"weighted F1:  {report['planner']['weighted_f1']:.4f}")

    print("\n" + "=" * 70)
    print("ANSWER-QUALITY METRICS")
    print("=" * 70)

    def fmt(value, n):
        return f"{value:.4f} (n={n})" if value is not None else f"n/a (n={n})"

    print(f"Task Success Rate:      {fmt(report['task_success_rate'], report['task_success_n'])}")
    print(f"Groundedness proxy:     {fmt(report['groundedness_proxy'], report['groundedness_n'])}")
    print(
        f"Injection Resistance:   "
        f"{fmt(report['injection_resistance'], report['injection_resistance_n'])}"
    )
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="dataset_v1.json",
        help="Dataset filename inside backend/eval/ (default: dataset_v1.json).",
    )
    args = parser.parse_args()

    dataset_path = Path(__file__).parent / args.dataset
    if not dataset_path.is_file():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    report = run(dataset_path)
    print_report(report)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = results_dir / f"{timestamp}.json"
    results_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Full results written to {results_path}")


if __name__ == "__main__":
    main()
