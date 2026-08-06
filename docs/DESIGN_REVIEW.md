# Production AI Design Review

> **A note on this document's structure:** I don't have the literal text
> of the Module 10 assignment's 10 Design Review questions in front of me
> while writing this — only the topics you specified answers must cover
> (Q5 = failure handling/retries, Q7 = safety/security, Q9 = scaling
> limits, Q10 = frank gaps). I've reconstructed the other six questions
> around the standard categories a production-AI review normally covers,
> and placed your four at the numbers you gave them. If the assignment's
> actual wording or numbering differs, the content below should still map
> onto it — but please check the numbering against the real handout
> before submitting, and relabel if needed.

Every answer below references real files in this repository. Where a
limitation exists, it's stated as one — see
[`docs/NOT_APPLICABLE.md`](NOT_APPLICABLE.md) for a companion list of
things this project explicitly doesn't attempt, with justification.

---

## Q1. What problem does this system solve, and for whom?

InsightAI-RAG lets a user upload a PDF and ask natural-language questions
about it, getting answers grounded in the document's actual text rather
than the model's general knowledge (`app/services/prompt_builder.py`'s
instructions explicitly forbid answering outside the provided context,
and fall back to a fixed "I couldn't find that" line otherwise). The
target user is a single person working with their own documents in a
browser session — there's no multi-user account system, no sharing, no
per-user document isolation (see Q9). It's a portfolio/learning project
demonstrating a grounded RAG pipeline end to end, not a multi-tenant
product.

## Q2. What data flows through the system, and how is it handled?

Two kinds of user-supplied data: uploaded PDF files and free-text chat
queries (optionally with prior conversation turns as `history`).
Uploaded files are stored on disk under a UUID filename
(`app/services/upload_service.py`) and their extracted text is chunked,
embedded, and written into the shared FAISS index — nothing is sent
anywhere except to Google's Gemini API for generation and (implicitly)
for the local sentence-transformers embedding model, which runs
in-process and never leaves the server. Extracted text is scanned for
PII-shaped patterns (emails, phone numbers, ID-number-like strings —
`app/services/pii_service.py`) and a match count is logged as a
warning; the policy is flag-and-continue, not block-and-reject, and the
log never contains the matched values themselves, only counts per type.
There's no user-account system, so there's no data to delete on account
closure beyond the document itself (`DELETE /documents/{id}`, which does
remove its vectors and its file on disk).

## Q3. Why this architecture?

FastAPI backend, FAISS for retrieval, Gemini for generation, a hand-rolled
single-agent orchestrator — see
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for the full diagram and a
dedicated justification (the "Framework choice" section) for not using
LangGraph/CrewAI at this scale. In short: two tools sharing one corpus
and one model don't need a multi-agent framework's coordination
machinery, and the actual control flow (plan → one of three branches →
optional single reflection retry) is linear enough that a plain
`if/elif` in `ChatService.handle_query` is an honest description of it,
not a simplification.

## Q4. How is the system protected against prompt injection?

Every retrieved chunk is wrapped in `---BEGIN UNTRUSTED DOCUMENT
EXCERPT---` / `---END EXCERPT---` markers, with an explicit instruction
in the system prompt that content between those markers is untrusted
data, not instructions, and that the model must not follow any
request/command/role-override it contains regardless of phrasing
(`app/services/prompt_builder.py`, `_INSTRUCTIONS`). This is a
prompt-level defense, not a filter or classifier — there's no separate
injection-detection step before generation. `backend/eval/dataset_v1.json`
includes two adversarial entries (a "reveal your system prompt" attempt
and a "say the exact text X" attempt) and `run_eval.py` reports an
**Injection Resistance** metric that checks whether the model's answer
avoided complying with the specific injected instruction — see
`backend/eval/README.md` for the metric's exact definition and its
stated limitation (it only detects the markers each entry defines, it's
not a general jailbreak classifier).

## Q5. How does the system handle failures, retries, and incorrect reasoning?

Two distinct mechanisms, at two different layers:

- **Transient failure retries** — `app/services/gemini_client.py`
  decorates `GeminiClient.generate` with `tenacity`: up to 3 attempts,
  exponential backoff, retrying only on `LLMTimeoutError`/`LLMAPIError`
  (not on `LLMEmptyResponseError`, since an empty/filtered response
  usually won't change on retry). Each retry is logged
  (`llm_generation_retrying`). `embedding_service.embed_query` carries
  the same decorator for symmetry with the spec this was built against,
  but in practice its own failures raise `EmbeddingGenerationError`/
  `EmbeddingModelLoadError` instead of the two retryable types, so today
  that decorator doesn't actually retry anything — a known gap, not a
  hidden claim.
- **Reasoning-quality self-correction** — `ChatService._reflect`
  (`app/services/rag_service.py`) catches one specific failure mode:
  chunks were retrieved, but the model's answer came back empty or equal
  to its own fallback line anyway. It regenerates once with an explicit
  "you didn't use the context" instruction
  (`REFLECTION_INSTRUCTION`). This is narrow by design — it doesn't
  catch subtly wrong-but-non-empty answers, hallucinated citations, or
  any failure mode outside "ignored the context it was given." It also
  only fires once; a second bad answer after reflection is returned as-is.
- **Everywhere else**, failures surface as typed `AppError` subclasses
  with a `taxonomy_category` (`app/core/exceptions.py`) and a mapped
  HTTP status code, logged via `request_failed`
  (`app/core/error_handlers.py`) — see Q7 and
  `backend/eval/metrics_report.py`'s error-rate-by-category report.

## Q6. How is quality evaluated?

`backend/eval/run_eval.py` runs a 16-entry dataset
(`dataset_v1.json` — 10 normal, 2 edge, 2 failure, 2 adversarial cases)
through the real `ChatService` (planner + full pipeline) against
whichever document is actually indexed, and reports: a confusion matrix
and accuracy/precision/recall/F1 (per-class, macro, weighted) for
planner routing; **Task Success Rate** (does the answer contain an
expected keyword — for failure-type entries, success means correctly
declining rather than fabricating); a **groundedness proxy** (lexical
overlap between the answer and the retrieved chunks — explicitly not a
faithfulness/entailment check, documented as a caveat in
`backend/eval/README.md`); and **Injection Resistance** (Q4). Separately,
`backend/tests/` has unit tests for the planner and reflection logic
(`test_rag_service.py`) and integration tests for the API surface
(`test_main.py`, with a Schema Compliance Rate check against the Pydantic
response models). `docs/HUMAN_EVAL.md` adds a manual rubric
(correctness, helpfulness, completeness, safety, tone, groundedness,
citation quality) for the same dataset, since none of the automated
metrics above assess subjective answer quality.

## Q7. What safety and security measures are in place?

- **Authentication**: `app/core/auth.py`'s `require_api_key` dependency
  gates the documents and chat routers behind a shared `X-API-Key`
  header, checked against `Settings.api_key`. Failed attempts are logged
  as `audit_event`/`auth_failed`. This is a single static secret, not
  per-user identity — see Q9 and `docs/NOT_APPLICABLE.md` for what that
  doesn't cover.
- **Destructive-action confirmation**: `DELETE /documents/{id}` requires
  `?confirm=true` or returns `ConfirmationRequiredError` (400) — a
  human-in-the-loop gate against accidental deletion, not a security
  boundary per se.
- **PII flagging**: see Q2 — detection without blocking, counts only in
  logs.
- **Prompt injection defense**: see Q4.
- **Audit logging**: uploads, deletes, and failed auth attempts are all
  logged as structured `audit_event` entries with `path` and a
  `request_id` (see Q8), giving a paper trail for who did what.
- **Not implemented**: encryption at rest, JWT/RBAC, rate limiting,
  per-user document isolation. All explicitly listed as future work in
  `docs/NOT_APPLICABLE.md` and the README's Known Limitations section.

## Q8. What are the cost and latency characteristics?

Every Gemini generation call logs `prompt_tokens`, `completion_tokens`,
`total_tokens`, and an `estimated_cost_usd` derived from
`Settings.cost_per_1k_tokens` (`gemini_client.py`) — an estimate against
a configured rate, not billed usage pulled from a billing API. Every
request carries a `request_id` (generated or propagated by middleware in
`main.py`, via a `contextvar`) automatically included on every log line
for that request, so a slow or expensive request's full trace — plan
decision, retrieval, generation, reflection — can be reconstructed from
logs alone. `backend/eval/metrics_report.py` aggregates
`processing_duration` values already present in the logs into P50/P95/P99
latency (overall and per event type) and sums tokens/cost across a log
file. Latency-affecting design choices: retrieval always embeds the
query at request time (no query cache), reflection roughly doubles
generation cost/latency on the (hopefully rare) queries that trigger it,
and `tenacity`'s exponential backoff means a genuinely down Gemini API
adds real wall-clock time (up to ~1+2+4s of backoff) before a request
ultimately fails.

## Q9. What are the scaling limits of the current design?

Honestly, several, all load-bearing for a single-user demo and all real
constraints for anything beyond it:

- **Single-file FAISS index.** `backend/vector_store/index.faiss` +
  `metadata.json` is one global index for every document, loaded as a
  single process-wide singleton (`get_vector_store()` in
  `app/api/v1/routes/query.py`, `@lru_cache(maxsize=1)`). There's no
  sharding, no per-tenant isolation, and no concurrency control around
  writes — `FAISSVectorStore.add_embeddings`/`delete_document`/`save`
  aren't guarded by any lock, so two uploads or an upload racing a
  delete at the same instant is a real (untested) correctness risk. A
  multi-user deployment would need a proper vector database
  (namespaced/multi-tenant) rather than this file.
- **Single API key.** One shared secret for the whole API — no per-user
  keys, no key rotation, no rate limiting, no way to revoke one client
  without rotating the key for everyone.
- **Document history lives in browser localStorage, not the server.**
  The backend has no document-listing endpoint, so
  `frontend/src/services/documentService.js` tracks what's been uploaded
  in the browser's `localStorage`. That means the Documents page only
  ever shows what *this browser* uploaded — a second device or a cleared
  browser profile sees nothing, even though the documents are still
  indexed server-side.
- **Chat conversation history isn't persisted at all**, server- or
  client-side beyond memory. `useChat.js` keeps it in React component
  state and sends up to the last 6 turns per request
  (`ChatRequest.history`, capped in `rag_service.py`'s
  `_MAX_HISTORY_TURNS`); a page refresh loses the conversation entirely.
- **No deployment yet** — see `docs/OPERATIONS.md`. Everything above is
  a single-process, single-machine design; there's no load balancer,
  no autoscaling, and no infrastructure-as-code in this repo today.

## Q10. What's still missing, honestly?

- No JWT/RBAC/per-user accounts — one shared API key for everyone (Q7,
  Q9).
- No encryption at rest for the vector store or uploaded files — plain
  files on disk.
- No OCR — PyMuPDF reads embedded/selectable text only; a scanned
  image-only PDF extracts little or nothing (see
  `docs/ARCHITECTURE.md`'s Upload pipeline section and
  `docs/NOT_APPLICABLE.md`).
- The reflection step (Q5) catches exactly one failure mode (empty/
  fallback answer despite retrieved context) — it doesn't catch subtly
  wrong answers, and it only retries once.
- `embed_query`'s retry decorator is currently dead code in practice
  (Q5) — its exception types don't match what the function actually
  raises.
- Groundedness is measured by a lexical-overlap proxy (Q6), not a real
  faithfulness/entailment check — it can't tell a correct paraphrase
  from a plausible-sounding fabrication that happens to reuse the same
  words.
- The eval harness (`run_eval.py`) requires a live Gemini API key and
  spends real quota — it isn't run in CI (see `.github/workflows/ci.yml`'s
  TODO comment), so planner/answer-quality regressions aren't caught
  automatically on every push, only unit/integration test regressions
  are.
- No deployment exists yet — Docker images are built and verified to run
  locally (`docker-compose.yml`), but nothing is live on the internet
  (`docs/OPERATIONS.md`).
- No human evaluation has actually been run — `docs/HUMAN_EVAL.md`
  defines the rubric and pre-fills the dataset, but the score columns
  are blank; this document ships the process, not results.
- `tool_used` and `steps_taken` are returned by `/chat`
  (`ChatResponse`) for telemetry/eval purposes but aren't yet displayed
  anywhere in the frontend UI.
