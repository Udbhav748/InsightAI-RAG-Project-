# InsightAI-RAG: features adopted from kotaemon and onyx

## Context

Two external repos were reviewed for ideas worth pulling into
InsightAI-RAG:

| Repo | What it is | License | Scale |
|---|---|---|---|
| [Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon) | Gradio-based RAG document-QA UI, single-process Python library (`libs/kotaemon` + `libs/ktem`) | Apache-2.0 | ~26k stars |
| [onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx) | Enterprise AI/search platform — Vespa search index, Redis, MinIO, Celery workers, 50+ connectors, Next.js frontend | MIT for everything outside `ee/` directories; `ee/` is under the separate **Onyx Enterprise License**, not reusable | ~32k stars |

Both were read directly (READMEs, repo structure, and — for kotaemon —
the actual reasoning-pipeline source, `libs/ktem/ktem/reasoning/simple.py`)
rather than judged by marketing copy alone. That's why the feature list
below is short: most of both repos' headline features don't survive the
constraints.

## Hard constraints (every candidate below was filtered through these)

1. **Zero ongoing cost.** No new paid API calls, no feature that only
   works with a hosted/metered service.
2. **Freely deployable.** No new infrastructure service (search engine,
   job queue, blob store, cache) beyond what's already running
   (FastAPI, Postgres, FAISS). The whole app must still run as one
   process + one DB, deployable on a free tier.
3. **Low local storage / dependency footprint.** No new heavy model
   download, no new large native dependency. Reuse what's already
   installed (PyMuPDF, Tesseract, sentence-transformers, FAISS,
   BM25/hybrid search) wherever possible.

Anything that fails any one of these three is in the **rejected**
table, not the plan — including several of each repo's *headline*
features.

## Rejected (considered, explicitly not doing)

| Feature | Source | Why not |
|---|---|---|
| GraphRAG / nano-GraphRAG / LightRAG indexing | kotaemon | New heavy dependency + graph store; marginal value for a single-collection document app; fails constraint 3 |
| Elasticsearch / ChromaDB / Milvus / Qdrant as alternate doc/vector stores | kotaemon | We already have FAISS + BM25 hybrid search; swapping backends adds infra with no capability we're missing; fails constraint 2 |
| Unstructured / Docling / PaddleOCR as alternate parsers | kotaemon | Heavier than our existing PyMuPDF + Tesseract; no proven quality win for our doc types; fails constraint 3 |
| Mindmap generation, embedding visualization | kotaemon | Novelty features, not core to answer quality; scope discipline |
| 50+ SaaS connectors (Slack, Drive, Confluence, ...) | onyx | Completely out of scope for a personal-document RAG app |
| Vespa, Redis, MinIO, Celery background workers | onyx | Multi-service infra; directly conflicts with "one process, free-tier deployable"; fails constraint 2 |
| Voice mode, image generation | onyx | Needs either a paid API or a new heavy local model download; fails constraints 1 and 3 |
| Code execution sandbox, MCP server, coding agent | onyx | Security-sensitive, heavy, unrelated to document QA |
| SSO/SCIM, whitelabeling, advanced RBAC dashboards | onyx | Enterprise scope we don't need; also lives under `ee/` — the Enterprise License, not MIT, so not legally reusable anyway |
| "Deep Research" / agentic RAG framing | onyx | We already have this — `research_agent_enabled` + `agent_routing_enabled` in `config.py` cover multi-step planning/web research. No action needed. |

## Selected — four phases, smallest/safest first

Each phase is independently shippable: its own commit, its own pytest
run, its own live browser check (per this repo's existing convention —
see CLAUDE.md). We do not start phase *N+1* until phase *N* is verified
working. No phase requires a new paid API. Only Phase 4 requires a new
dependency at all (a small frontend-only one).

### Phase 1 — Retrieval confidence signal (smallest, zero new deps)

**From:** kotaemon's inline `"WARNING! Context relevance score is low"`
banner and its answer-confidence display (`libs/ktem/ktem/reasoning/simple.py`).

**Why it's nearly free:** `rag_service.py`'s `ChatService._grade_retrieval()`
(line ~571) **already computes** `"good"` / `"weak"` / `"insufficient"`
on every request — today it's only used internally to decide whether
the corrective loop fires. This phase just exposes a value that already
exists; no new computation, no new LLM call.

- **Backend:** add `retrieval_confidence: Literal["good", "weak", "insufficient"]`
  to `ChatResponse` (`app/models/schemas.py`), populated from the
  existing `_grade_retrieval()` return value in `rag_service.py`. Purely
  additive field — same pattern as this session's `SourceReference.content_type`/
  `page_number` addition, so it can't break existing response validation.
- **Frontend:** `ChatBubble.jsx` (or `AgentTraceStrip.jsx`, wherever fits
  the existing visual language best) renders a small inline notice when
  `retrieval_confidence !== "good"` — e.g. "Low confidence — double-check
  this against the source." Same idea as kotaemon's banner, our own
  copy/styling.
- **No `Settings` flag.** This isn't a cost or behavior change — it's
  surfacing existing internal state — so it doesn't need the
  off-by-default gating this codebase uses for paid/behavioral features.
- **Verify:** `pytest` (new assertion on the field in `test_main.py`'s
  existing chat-response schema checks); live check — ask an
  off-topic/unanswerable question in the browser, confirm the banner
  appears; ask an on-topic question, confirm it doesn't.

### Phase 2 — Persona presets (zero new deps, zero new cost)

**From:** onyx's "Custom Agents" (build an agent with its own
instructions) — concept only, not code (onyx's implementation is
wired into its Postgres-backed agent/tool system, not portable here,
and much of that surface sits close to `ee/`-adjacent enterprise
tooling anyway).

**Design constraint, stated explicitly:** a persona may only change
*tone/style*, never the grounding or citation rules in
`prompt_builder.AGENT_ROLE`/`AGENT_GOAL`/`_INSTRUCTIONS`. The whole
point of this app is answers grounded in retrieved evidence — a
persona is not allowed to be a way to quietly turn that off.

- **Backend:** a small fixed dict in `prompt_builder.py`, e.g.:
  ```python
  PERSONAS: dict[str, str] = {
      "default": "",
      "concise": "Keep answers to 2-3 sentences unless the question needs more.",
      "eli5": "Explain in plain, simple language, as if to someone new to the topic.",
  }
  ```
  appended as an extra instruction line in `build_prompt()` — never
  replacing `_INSTRUCTIONS`. `ChatRequest` gets an optional
  `persona: str | None = None` field (`app/models/schemas.py`); unset
  behaves exactly as today (100% backward compatible for existing
  callers/tests).
- **Frontend:** a small dropdown near the chat input (`Chat.jsx` /
  `ChatInput.jsx`), stored in `useChat.js` state, sent on each request.
- **Verify:** `pytest` (unit test that each persona's instruction
  actually appears in the built prompt, and that grounding instructions
  are always present regardless of persona); live check — ask the same
  question under two personas, confirm tone differs but both still cite
  sources.

### Phase 3 — Usage analytics (reuses existing data, zero new deps)

**From:** onyx's "Query History" / usage analytics for admins —
concept only. We already log every request to the `usage_logs` Postgres
table (built earlier this session for rate-limiting/audit); this phase
is purely reading data that already exists, not new tracking.

- **Backend:** new `GET /admin/usage-summary` route, `admin`-role gated
  (reuses `app/core/permissions.py`'s existing pattern — same shape as
  `DOCUMENT_DELETE`/`all_tenants` checks). Aggregates `usage_logs` by day/
  endpoint/tenant via plain SQLAlchemy — no new table.
- **Frontend:** a small panel, either a new `/admin` page or an
  extra section in `Settings.jsx` (visible only when the logged-in
  user's role is admin). Hand-rolled bars via CSS/flex — **no new chart
  library** — to keep the bundle small, per constraint 3.
- Degrades to an empty/disabled state when `DATABASE_URL` is unset,
  same convention every other DB-backed feature in this app already
  follows.
- **Verify:** `pytest` (route returns correct aggregation, 403s for
  non-admin); live check — log in as admin, confirm the panel renders
  real numbers from actual usage.

### Phase 4 — In-app PDF citation preview (the one new dependency)

**From:** kotaemon's biggest real UX win — clicking a citation opens
the source PDF with the cited passage highlighted, instead of just
showing an excerpt string.

**Why it's feasible cheaply:** `SourceReference.page_number` already
exists (added this session for the multimodal citation-labeling work).
PyMuPDF (already a dependency, no new install) can locate a snippet's
bounding box on a given page **on demand**, at request time — via
`page.search_for(text)` — so this needs **zero changes to indexing or
chunking**. No stored bbox metadata, no reprocessing of existing
documents, no risk to the existing pipeline.

- **Backend:** two new routes in `documents.py`, both tenant-scoped
  the same way the existing `GET /documents/{id}/images` route already is:
  - `GET /documents/{document_id}/file` — serves the stored PDF bytes
    (already saved to disk by `upload_service`; this route didn't
    exist before).
  - `GET /documents/{document_id}/pages/{page_number}/highlight?text=...` —
    runs `page.search_for(text)` for the cited excerpt, returns bbox
    rectangles (normalized to page width/height) for the frontend to
    draw over the rendered page.
- **Frontend:** the **one new dependency in this whole plan** —
  `pdfjs-dist` (a few MB, no lighter real alternative exists for
  in-browser PDF rendering). New `PdfPreviewModal.jsx`, opened from a
  "View in PDF" button added to `SourceReferences.jsx`'s existing
  citation cards. Citations with `page_number: null` (documents indexed
  before this session's metadata work, or non-page-anchored content)
  simply don't get the button — graceful degrade, no error state.
- **Verify:** `pytest` (new route tests: correct bytes served, 404 for
  wrong tenant, bbox search returns sane rectangles for a known
  excerpt); live check — click "View in PDF" on a real citation in the
  browser, confirm the PDF opens to the right page with a visible
  highlight over the cited text.

## What must not regress

Same convention as `docs/MULTIUSER_MULTIMODAL_PLAN.md`: every phase
here is additive. None of them touch `app/core/auth.py`,
`app/core/permissions.py`, the RBAC/tenant-scoping logic, or any
existing route's current behavior for callers who don't opt into the
new fields. The full pytest suite must stay green after every phase,
not just at the end.

## Sequencing

Strictly in order — 1 → 2 → 3 → 4. Each is a separate commit. We do not
start building phase 2 until phase 1's pytest + live-browser check both
pass. This file is the source of truth for scope; if a phase's actual
implementation needs to grow beyond what's described here, that's a
signal to stop and update this file first, not to quietly expand scope
mid-phase.
