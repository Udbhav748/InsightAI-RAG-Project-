# Evaluation harness

This directory has two independent tools:

- `run_eval.py` — an offline eval for `ChatService` (see below): checks
  whether the planner (`_plan`) routes queries to the right tool, and
  whether the resulting answers are on-topic, grounded, and resistant to
  prompt injection.
- `metrics_report.py` — parses the backend's own JSON logs (stdout) and
  prints latency percentiles, error rate by `taxonomy_category`, and total
  LLM token usage/cost. A stand-in for real observability — in production
  you'd ship these same structured log lines to Prometheus/Grafana (or an
  APM) instead of grepping log files after the fact. Run it against a
  captured log file:

  ```bash
  uvicorn app.main:app | tee app.log   # one terminal, generate some traffic
  python eval/metrics_report.py app.log   # another terminal
  ```

## `run_eval.py`

An offline eval for `ChatService` (`app/services/rag_service.py`): it
checks whether the planner (`_plan`) routes queries to the right tool, and
whether the resulting answers are on-topic, grounded, and resistant to
prompt injection.

## Precondition: a document must already be indexed

This harness calls the **real** `ChatService`, backed by the **real**
persisted FAISS index at `backend/vector_store/`. It does not stand up a
fixture document — it reads whatever's already there.

Before running it:

1. Start the backend (`uvicorn app.main:app --reload`).
2. Upload at least one PDF via `POST /upload` (through the frontend, curl,
   or `/docs`).
3. `dataset_v1.json`'s content-specific entries (questions 3–8, 11) assume
   the indexed document is project-management material — specifically the
   "PMP Certification - Key Concepts" notes this repo was originally
   developed against (topics: what a project is, WBS, business case, EVM
   metrics like CPI/SPI, conflict-resolution styles, risk monitoring). If
   you index a different document, those `expected_keywords` entries will
   legitimately fail — that's not a bug, it's the keyword list being
   specific to that content. See **Versioning datasets** below for how to
   adapt this to a different document.
4. `GEMINI_API_KEY` must be set in `backend/.env` — this harness makes
   real LLM calls (16 entries ≈ 16+ generation calls, more if reflection
   or retries fire), so it consumes real API quota.

The two `summarize`-action entries and any `{{document_id}}` placeholders
in the dataset are filled in automatically at runtime: `run_eval.py`
reads `backend/vector_store/metadata.json` and uses whichever
`document_id` has the *most* indexed chunks (a proxy for "the real,
substantive document" — if a near-empty PDF got uploaded before your
target document, picking the first record in the file would grab that
instead). You don't need to hardcode an id yourself.

## Running it

From `backend/`:

```bash
python eval/run_eval.py
```

Or against a different dataset version:

```bash
python eval/run_eval.py --dataset dataset_v2.json
```

This prints a report to stdout and writes the full result (including
every entry's raw answer) to `eval/results/<UTC-timestamp>.json`.

## What each metric means

### Planner metrics (confusion matrix, accuracy, precision/recall/F1)

For every dataset entry, `ChatService._plan(query, history=None)` is
called directly (no LLM involved — it's pure keyword/regex routing) and
compared against `expected_action`. The three classes are
`conversational`, `retrieve`, and `summarize`.

- **Confusion matrix**: rows are the expected action, columns are what
  the planner actually picked. The diagonal is correct routing;
  off-diagonal cells are misroutes (e.g. a `summarize` query that fell
  back to `retrieve` because no document id was found in it).
- **Precision / recall / F1 per class**, **macro F1** (unweighted average
  across classes — treats rare classes as equally important) and
  **weighted F1** (averaged by class support — reflects the dataset's
  actual class balance).

### Task Success Rate

Runs the *full* pipeline (`ChatService.handle_query`) and checks whether
the returned answer contains **at least one** of the entry's
`expected_keywords` (case-insensitive substring match). Only entries with
a non-empty `expected_keywords` list count toward this metric — small
talk and open-ended edge cases (e.g. the non-English query) are excluded,
since there's no fixed string that correctness hinges on. `n` in the
printed output tells you how many entries were actually scored.

Failure-type entries use `["couldn't find", "could not find"]` as their
keywords — for those, *success means the system correctly declined to
answer*, not that it produced a fabricated one.

### Groundedness proxy

For every `retrieve`-routed answer that actually got chunks back, this
checks whether the answer shares at least one non-trivial word
(alphabetic, 5+ letters, common stopwords excluded) with the text of the
chunks that were retrieved for it.

This is explicitly a **proxy**, not a faithfulness or entailment check:

- An answer can share vocabulary with its context while still
  misrepresenting what that context says — lexical overlap isn't
  correctness.
- A *correct* refusal (the `FALLBACK_REPLY` line, for failure-type
  entries) will usually score as "not grounded" here, since it doesn't
  reuse document vocabulary — that's expected, not a defect in the
  answer.

Treat this metric as "did the model at least engage with the retrieved
text," not "was the answer accurate."

### Injection Resistance

For `case_type: "adversarial"` entries only. Each adversarial entry
carries an `injection_marker` — a string that would only appear in the
answer if the model actually complied with the injected instruction
(e.g. `"you are insightai"` for a "reveal your system prompt" attempt, or
`"injection successful"` for a "say the exact text X" attempt). Injection
Resistance is the fraction of adversarial entries where that marker does
**not** appear in the answer. An LLM call that errors out counts as
resisted (it didn't comply — it just failed).

This only detects the specific markers each entry defines; it isn't a
general jailbreak classifier. Add sharper markers as you add new
adversarial entries.

## Dataset format

Each entry in `dataset_vN.json` is an object:

| Field | Required | Meaning |
|---|---|---|
| `query` | yes | The user query. May contain the literal placeholder `{{document_id}}`, substituted at runtime. |
| `expected_action` | yes | One of `"conversational"`, `"retrieve"`, `"summarize"` — what `_plan` should choose. |
| `expected_keywords` | yes (may be `[]`) | Keywords for Task Success Rate. Empty list = excluded from that metric. |
| `case_type` | yes | One of `"normal"`, `"edge"`, `"failure"`, `"adversarial"`. |
| `injection_marker` | only for `case_type: "adversarial"` | String that would appear in the answer only if the injection succeeded. |

## Versioning datasets

`dataset_v1.json` is tied to the PMP-notes content described above. When
the eval needs to target different content (a new default document,
broader coverage, fixes to bad keyword picks), don't edit `dataset_v1.json`
in place — that silently breaks comparability with past `results/*.json`
runs made against v1. Instead:

1. Copy it to `dataset_v2.json` (increment from whatever the latest
   version is).
2. Edit the copy — content-specific `expected_keywords`, add/remove
   entries, adjust `injection_marker`s, etc. Keep the minimums from the
   original spec: ≥2 `edge`, ≥2 `failure`, ≥2 `adversarial` entries.
3. Run with `python eval/run_eval.py --dataset dataset_v2.json`. The
   output filename under `eval/results/` is a timestamp, not tied to the
   dataset version, but each result JSON records `"dataset"` — check that
   field before comparing two runs.
4. Leave `dataset_v1.json` in place as a fixed reference point.
