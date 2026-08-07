"""Evaluation harness for ChatService's planner and answers.

Runs every entry in a dataset file (see eval/README.md) through
ChatService._plan (for planner classification) and ChatService.handle_query
(for the actual answer), then reports:

- a confusion matrix + accuracy/precision/recall/F1 for planner routing
- Tool-argument accuracy: for expected_action == "summarize" entries, did
  the planner extract the right document_id from the query, not just
  pick the right action? Routing and argument extraction are separate
  failure modes (see PlanDecision in rag_service.py) and the confusion
  matrix above only covers the former.
- Task Success Rate: does the answer contain an expected keyword?
- Groundedness proxy: for retrieval answers, do they share vocabulary with
  the chunks that were actually retrieved?
- Injection Resistance: for adversarial entries, did the answer avoid
  complying with the injected instruction?
- Source Accuracy: for entries with an expected_source, did
  ChatResponse.answer_source ("documents"/"web"/"mixed") match it? Only
  meaningful with Settings.web_search_enabled=true — see dataset_v2.json's
  two web-findable entries and eval/README.md.
- Precision@5 / Recall@5 / MRR: for entries with expected_chunk_keywords,
  how good was *retrieval itself* (independent of the generated answer)?
  A retrieved chunk is "relevant" if it contains any of the entry's
  expected_chunk_keywords — see precision_at_k/recall_at_k/reciprocal_rank
  below for exactly what each measures, and eval/README.md for the
  worked definitions. This is what the "Retrieval ablation" numbers in
  docs/OPERATIONS.md are built from.

Requires a real GEMINI_API_KEY (this calls the live LLM) and at least one
document already indexed in the backend's vector store — see
eval/README.md for both preconditions.

Usage (from backend/):
    python eval/run_eval.py
    python eval/run_eval.py --dataset dataset_v2.json
    python eval/run_eval.py --delay 15   # pace requests under a free-tier rate limit
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
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


RETRIEVAL_EVAL_K = 5

# A retrieved chunk is "relevant" if it contains any of an entry's
# expected_chunk_keywords (case-insensitive substring, via
# contains_any_keyword). There's no full corpus relevance judgment to
# compute textbook Precision/Recall against — only this keyword heuristic
# — so each metric below is defined purely in terms of it:
#
#   precision_at_k: what fraction of what was retrieved is relevant.
#   recall_at_k: what fraction of the *distinct expected keywords* were
#     covered by at least one retrieved chunk — each keyword stands in
#     for one expected fact/passage, since there's no labeled set of
#     "all relevant chunks in the corpus" to divide by instead.
#   reciprocal_rank: how quickly (at what rank) the first relevant chunk
#     showed up, 0 if none did within k.


def precision_at_k(chunks: list[RetrievedChunk], keywords: list[str], k: int) -> float:
    """Fraction of the top-k retrieved chunks that are relevant. Missing
    slots (fewer than k chunks were actually retrieved) count as
    non-relevant, per the standard P@K convention."""
    top = chunks[:k]
    relevant_count = sum(1 for chunk in top if contains_any_keyword(chunk.text, keywords))
    return relevant_count / k


def recall_at_k(chunks: list[RetrievedChunk], keywords: list[str], k: int) -> float:
    """Fraction of the entry's expected_chunk_keywords covered by at least
    one of the top-k retrieved chunks."""
    if not keywords:
        return 0.0
    top = chunks[:k]
    covered = sum(
        1 for keyword in keywords if any(keyword.lower() in chunk.text.lower() for chunk in top)
    )
    return covered / len(keywords)


def reciprocal_rank(chunks: list[RetrievedChunk], keywords: list[str], k: int) -> float:
    """1 / rank of the first top-k chunk that's relevant; 0 if none are."""
    for rank, chunk in enumerate(chunks[:k], start=1):
        if contains_any_keyword(chunk.text, keywords):
            return 1.0 / rank
    return 0.0


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


def run(dataset_path: Path, delay: float = 0.0) -> dict:
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
    tool_arg_accuracy_flags: list[bool] = []
    task_success_flags: list[bool] = []
    grounded_flags: list[bool] = []
    injection_flags: list[bool] = []
    source_accuracy_flags: list[bool] = []
    precision_flags: list[float] = []
    recall_flags: list[float] = []
    reciprocal_ranks: list[float] = []
    entries_out = []

    delay_note = f", {delay:.1f}s delay between entries" if delay > 0 else ""
    print(f"Running {len(dataset)} eval entries against document {document_id}{delay_note}...\n")

    for index, entry in enumerate(dataset):
        # Space requests out to stay under the LLM API's per-minute rate
        # limit. Each entry can cost 2 generation calls (answer +
        # reflection retry), so back-to-back entries can burst past a
        # free-tier cap even though tenacity retries individual calls —
        # pacing between *entries* is what actually avoids that, not
        # retrying within one.
        if index > 0 and delay > 0:
            time.sleep(delay)

        query = entry["query"].replace("{{document_id}}", document_id)
        expected_action = entry["expected_action"]
        case_type = entry["case_type"]
        keywords = entry.get("expected_keywords") or []
        expected_source = entry.get("expected_source")
        chunk_keywords = entry.get("expected_chunk_keywords") or []

        plan = chat_service._plan(query, history=None)
        y_true.append(expected_action)
        y_pred.append(plan.action)

        document_id_correct = None
        if expected_action == "summarize":
            # Routing accuracy (did the planner pick "summarize" at all) is
            # already captured by the confusion matrix above — this checks
            # the tool *argument*: did it extract the right document_id from
            # the query, not just the right action? plan.document_id is
            # None whenever plan.action != "summarize" (see PlanDecision),
            # which correctly fails this check too — getting the argument
            # right is moot if the action itself was misrouted.
            document_id_correct = plan.document_id == document_id
            tool_arg_accuracy_flags.append(document_id_correct)

        task_success = None
        grounded = None
        injection_resisted = None
        answer_source = None
        source_correct = None
        precision = None
        recall = None
        rr = None
        answer = ""
        tool_used = "none"
        steps_taken = 0
        error = None

        try:
            response = chat_service.handle_query(query, history=None)
            answer = response.answer
            tool_used = response.tool_used
            steps_taken = response.steps_taken
            answer_source = response.answer_source

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

            if expected_source:
                source_correct = answer_source == expected_source
                source_accuracy_flags.append(source_correct)

            if chunk_keywords:
                precision = precision_at_k(response.retrieved_chunks, chunk_keywords, RETRIEVAL_EVAL_K)
                recall = recall_at_k(response.retrieved_chunks, chunk_keywords, RETRIEVAL_EVAL_K)
                rr = reciprocal_rank(response.retrieved_chunks, chunk_keywords, RETRIEVAL_EVAL_K)
                precision_flags.append(precision)
                recall_flags.append(recall)
                reciprocal_ranks.append(rr)
        except AppError as exc:
            error = str(exc)
            if keywords:
                task_success_flags.append(False)
                task_success = False
            if case_type == "adversarial":
                injection_flags.append(True)  # an error can't have complied
                injection_resisted = True
            if expected_source:
                source_accuracy_flags.append(False)
                source_correct = False
            if chunk_keywords:
                precision, recall, rr = 0.0, 0.0, 0.0
                precision_flags.append(precision)
                recall_flags.append(recall)
                reciprocal_ranks.append(rr)

        status = "OK" if error is None else f"ERROR: {error}"
        print(f"[{case_type:11s}] {expected_action:>13s} -> {plan.action:<13s} | {query[:70]!r} | {status}")

        entries_out.append(
            {
                "query": entry["query"],
                "case_type": case_type,
                "expected_action": expected_action,
                "predicted_action": plan.action,
                "document_id_correct": document_id_correct,
                "tool_used": tool_used,
                "steps_taken": steps_taken,
                "answer": answer,
                "answer_source": answer_source,
                "expected_source": expected_source,
                "source_correct": source_correct,
                "precision_at_5": precision,
                "recall_at_5": recall,
                "reciprocal_rank": rr,
                "error": error,
                "task_success": task_success,
                "grounded": grounded,
                "injection_resisted": injection_resisted,
            }
        )

    planner_report = classification_report(y_true, y_pred)
    matrix = confusion_matrix(y_true, y_pred)
    tool_arg_accuracy = (
        sum(tool_arg_accuracy_flags) / len(tool_arg_accuracy_flags)
        if tool_arg_accuracy_flags
        else None
    )

    task_success_rate = (
        sum(task_success_flags) / len(task_success_flags) if task_success_flags else None
    )
    groundedness_proxy = (
        sum(grounded_flags) / len(grounded_flags) if grounded_flags else None
    )
    injection_resistance = (
        sum(injection_flags) / len(injection_flags) if injection_flags else None
    )
    source_accuracy = (
        sum(source_accuracy_flags) / len(source_accuracy_flags) if source_accuracy_flags else None
    )
    precision_at_5 = sum(precision_flags) / len(precision_flags) if precision_flags else None
    recall_at_5 = sum(recall_flags) / len(recall_flags) if recall_flags else None
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None

    report = {
        "dataset": dataset_path.name,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "llm_provider": settings.llm_provider,
        "fallback_llm_provider": settings.fallback_llm_provider,
        "prompt_version": PROMPT_VERSION,
        "hybrid_search_enabled": settings.hybrid_search_enabled,
        "reranking_enabled": settings.reranking_enabled,
        "document_id_used": document_id,
        "n_entries": len(dataset),
        "case_type_counts": dict(Counter(entry["case_type"] for entry in dataset)),
        "planner": {
            "confusion_matrix": matrix,
            **planner_report,
        },
        "tool_arg_accuracy": round(tool_arg_accuracy, 4) if tool_arg_accuracy is not None else None,
        "tool_arg_accuracy_n": len(tool_arg_accuracy_flags),
        "task_success_rate": round(task_success_rate, 4) if task_success_rate is not None else None,
        "task_success_n": len(task_success_flags),
        "groundedness_proxy": round(groundedness_proxy, 4) if groundedness_proxy is not None else None,
        "groundedness_n": len(grounded_flags),
        "injection_resistance": round(injection_resistance, 4) if injection_resistance is not None else None,
        "injection_resistance_n": len(injection_flags),
        "source_accuracy": round(source_accuracy, 4) if source_accuracy is not None else None,
        "source_accuracy_n": len(source_accuracy_flags),
        "precision_at_5": round(precision_at_5, 4) if precision_at_5 is not None else None,
        "precision_at_5_n": len(precision_flags),
        "recall_at_5": round(recall_at_5, 4) if recall_at_5 is not None else None,
        "recall_at_5_n": len(recall_flags),
        "mrr": round(mrr, 4) if mrr is not None else None,
        "mrr_n": len(reciprocal_ranks),
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

    def fmt(value, n):
        return f"{value:.4f} (n={n})" if value is not None else f"n/a (n={n})"

    print(
        f"\nTool-argument accuracy (summarize's document_id): "
        f"{fmt(report['tool_arg_accuracy'], report['tool_arg_accuracy_n'])}"
    )

    print("\n" + "=" * 70)
    print("ANSWER-QUALITY METRICS")
    print("=" * 70)

    print(f"Task Success Rate:      {fmt(report['task_success_rate'], report['task_success_n'])}")
    print(f"Groundedness proxy:     {fmt(report['groundedness_proxy'], report['groundedness_n'])}")
    print(
        f"Injection Resistance:   "
        f"{fmt(report['injection_resistance'], report['injection_resistance_n'])}"
    )
    print(f"Source Accuracy:        {fmt(report['source_accuracy'], report['source_accuracy_n'])}")

    print("\n" + "=" * 70)
    print(
        f"RETRIEVAL QUALITY METRICS  (hybrid_search_enabled="
        f"{report['hybrid_search_enabled']}, reranking_enabled={report['reranking_enabled']})"
    )
    print("=" * 70)
    print(f"Precision@5:            {fmt(report['precision_at_5'], report['precision_at_5_n'])}")
    print(f"Recall@5:               {fmt(report['recall_at_5'], report['recall_at_5_n'])}")
    print(f"MRR:                    {fmt(report['mrr'], report['mrr_n'])}")
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="dataset_v1.json",
        help="Dataset filename inside backend/eval/ (default: dataset_v1.json).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help=(
            "Seconds to sleep between dataset entries, to stay under an API rate "
            "limit (e.g. 15 for a 5-requests/minute free tier). Default: 0 (no delay)."
        ),
    )
    args = parser.parse_args()

    dataset_path = Path(__file__).parent / args.dataset
    if not dataset_path.is_file():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    report = run(dataset_path, delay=args.delay)
    print_report(report)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = results_dir / f"{timestamp}.json"
    results_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Full results written to {results_path}")


if __name__ == "__main__":
    main()
