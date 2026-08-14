<div align="center">

# InsightAI-RAG

**Upload a PDF. Ask it questions. Get answers grounded in what it actually says.**

InsightAI-RAG is a full-stack Retrieval-Augmented Generation app: a FastAPI backend that chunks and embeds your documents into a FAISS vector index, and a React SPA for uploading files and chatting with them — with every answer traceable back to the source passage.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![FAISS](https://img.shields.io/badge/FAISS-vector%20search-4B8BBE)
![Gemini](https://img.shields.io/badge/LLM-Gemini-8E75B2)

</div>

<br>

![Home screen](docs/screenshots/home.png)

## Table of contents

- [How it works](#how-it-works)
- [Features](#features)
- [Screenshots](#screenshots)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Evaluation](#evaluation)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)
- [Future work](#future-work)
- [License](#license)

## How it works

```
                    ┌──────────────┐
   PDF upload  ───▶ │  PyMuPDF     │  extract text per page
                    └──────┬───────┘  (OCR fallback for scanned/thin-text pages)
                           ▼
                    ┌──────────────┐
                    │  Chunking    │  langchain-text-splitters
                    │  (1000 chars,│  200 char overlap
                    │   overlap)   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Embeddings  │  Sentence Transformers
                    │              │  (all-MiniLM-L6-v2)
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  FAISS index │  persisted to disk,
                    │ (IndexFlatIP)│  cosine similarity search
                    └──────────────┘
```

A document uploaded through `/upload` is chunked, embedded, and written into the same in-memory FAISS index that `/chat` queries — so a new document is searchable immediately, no reload or reindex step required.

A chat message doesn't go straight to the LLM — it goes through a small hand-rolled agent (`ChatService`, plain Python, no LangGraph/CrewAI — see `docs/ARCHITECTURE.md`'s "Framework choice" for why):

1. **Plan.** A keyword/regex planner (no LLM call) routes the query to one of three actions: `conversational` (small talk, answered directly), `summarize` (a "summarize"/"summary" keyword plus a document-id-shaped UUID in the text), or `retrieve` (the default).
2. **Retrieve.** FAISS semantic search fused with a BM25 lexical index by default (hybrid search), then an optional cross-encoder re-ranking pass over the candidate pool before narrowing to `top_k` — both config-gated and A/B'd against a semantic-only baseline (`docs/OPERATIONS.md`'s "Retrieval ablation").
3. **Grade.** The top result's score sorts retrieval into `insufficient` / `weak` / `good` — no LLM call, just a threshold check. `weak`/`insufficient` pulls in a web search fallback (off by default) *before* the first generation attempt, so the model has it alongside whatever document context came back.
4. **Generate, then correct.** Gemini (or Groq) answers from the retrieved context. If the answer comes back empty or ungrounded, the corrective loop regenerates once with an explicit "you didn't use the context" instruction, then — if still ungrounded and web search wasn't already used — escalates to a web-search-augmented regeneration. Every path is capped at 3 total `generate()` calls per request.
5. **Answer**, with per-chunk citations (and, when web search contributed, per-result citations) attached — never a bare model reply.

`POST /chat/stream` fans this same sequence out live as Server-Sent Events (plan → retrieve → grade → generate/correct → answer, token by token) instead of waiting for the final response.

**Image-based diagnosis** (`POST /chat/diagnose`) skips the planner entirely: an uploaded leaf photo goes to [LeafSense](#running-with-leafsense-image-diagnosis), a separate vision service, which returns a predicted crop/disease; that prediction becomes the query and runs through the exact same retrieve → grade → correct pipeline above.

## Features

- **Drag-and-drop PDF ingestion** — validated for type and size, chunked with configurable overlap, embedded, and indexed in one request. Pages with no extractable text layer (scanned/image-only PDFs) fall back to OCR (`document_service.py`, pytesseract/tesseract) automatically — no separate upload path or user action needed.
- **Grounded chat** — every answer is generated only from retrieved chunks, with the source document and matched excerpts shown alongside the response.
- **Streamed, visible agent progress** — `POST /chat/stream` (Server-Sent Events) fans out each pipeline stage (planning, retrieval, grading, web search, generating, reflecting) as it happens, plus the answer token-by-token, instead of one response at the end. The chat UI renders this as a live "agent trace" strip above the forming answer, collapsing into an expandable summary once done.
- **Plant disease diagnosis from a photo** — `POST /chat/diagnose` classifies an uploaded leaf image via [LeafSense](#running-with-leafsense-image-diagnosis) (a separate vision service) and runs the predicted disease through the same grounded retrieval pipeline as a text question.
- **Hybrid retrieval** — FAISS semantic search fused with a BM25 lexical index by default (`HYBRID_SEARCH_ENABLED`), plus an opt-in cross-encoder re-ranking stage (`RERANKING_ENABLED`). Both are config-gated specifically so they've been A/B'd against a semantic-only baseline — see `docs/OPERATIONS.md`'s "Retrieval ablation" for the measured Precision@5/Recall@5/MRR numbers behind the defaults.
- **Corrective RAG loop** — retrieval is graded (insufficient/weak/good) right after it runs; a weak or insufficient grade can pull in a web search fallback (off by default) alongside document context. An ungrounded answer regenerates once with an explicit "you didn't use the context" instruction, then — if still ungrounded and web search wasn't already used — escalates to one more, web-augmented regeneration; every path is capped at 3 total generation calls per request before falling back to a clear "couldn't find that" reply. See `docs/ARCHITECTURE.md`'s "Framework choice" section for how this stays plain Python rather than a graph runtime.
- **Conversational query routing** — small talk and meta-questions are handled without spending a retrieval + generation round trip on them.
- **Document management** — browse everything you've uploaded, see page/chunk counts, and delete a document (which also removes its vectors from the index).
- **Multi-modal ingestion (off by default, opt-in per deployment)** — embedded figures are extracted and persisted (`IMAGE_EXTRACTION_ENABLED`), captioned by a vision-capable Gemini call into searchable `source="image_caption"` chunks (`IMAGE_CAPTIONING_ENABLED`), tables are reduced to markdown and indexed as `source="table"` text (`TABLE_EXTRACTION_ENABLED`), and questions that score weak on retrieval can route to a vision-grounded answer over the page raster (`VISION_QA_ENABLED`). Extracted images are browsable via `GET /documents/{id}/images`, and `/health` reports which capabilities a deployment has on.
- **Light & dark themes**, keyboard-friendly chat input, and toast notifications throughout.
- **Structured JSON logging** and a typed exception hierarchy that maps domain errors (corrupted PDF, empty vector store, LLM timeout, ...) to the correct HTTP status code.

## Screenshots

<table>
<tr>
<td width="50%">

**Chat, grounded in your documents**
Every answer links back to the excerpt it came from.

![Chat](docs/screenshots/chat.png)

</td>
<td width="50%">

**Upload**
Drag, drop, done — chunked and embedded in seconds.

![Upload](docs/screenshots/upload.png)

</td>
</tr>
<tr>
<td width="50%">

**Documents**
Everything in your knowledge base, at a glance.

![Documents](docs/screenshots/documents.png)

</td>
<td width="50%">

**Settings**
Light or dark, your call.

![Settings](docs/screenshots/settings.png)

</td>
</tr>
</table>

## Tech stack

| | |
|---|---|
| **Backend** | FastAPI, Pydantic v2 (`pydantic-settings`), Uvicorn |
| **Document parsing** | PyMuPDF |
| **Chunking** | `langchain-text-splitters` |
| **Embeddings** | Sentence Transformers (`all-MiniLM-L6-v2`) |
| **Vector store** | FAISS (`IndexFlatIP`, cosine similarity) |
| **LLM** | Google Gemini (`google-genai`) |
| **Frontend** | React 18, Vite, Tailwind CSS, Framer Motion, React Router |
| **Testing** | Pytest |

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Gemini API key](https://ai.google.dev/)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # then set GEMINI_API_KEY
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000` (interactive docs at `/docs`).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # leave unset in dev (same-origin /api proxy)
npm run dev
```

The app is now running at `http://localhost:5173`.

### Running tests

```bash
cd backend
pytest
```

```bash
cd frontend
npx vitest run     # jsdom unit tests
npm run lint       # eslint
npm run build      # production build
```

### Leaf Diagnosis (optional)

`POST /chat/diagnose` lets a user upload a plant leaf photo instead of
typing a question — InsightAI calls out to LeafSense (a separate
repo/process with its own TensorFlow/Keras stack) over HTTP to classify
it, then runs the predicted disease through the normal retrieval +
grounding pipeline. This is **optional**: the rest of the app works fully
without it, and if you never hit `/chat/diagnose`, LeafSense doesn't need
to be running at all.

To enable it, run the app as documented above (backend in one terminal,
frontend in another), then start LeafSense in a **third terminal** with
its one-command launcher:

```powershell
# in the LeafSense repo (Windows)
backend/start.ps1

# in the LeafSense repo (Linux / macOS)
backend/start.sh
```

Or start all three together in one command: from this repo's root (on
Windows), `.\start-local.ps1` opens backend, frontend, and (if `../LeafSense`
is checked out alongside this repo) LeafSense each in their own console
window.

`start.ps1` and `start.sh` create a dedicated venv (`LeafSense/backend/.venv`) on first
run, install requirements, warm up the Keras graph, and serve on port **8001** —
LeafSense's own standalone default of 8000 would collide with this backend's default
port, and InsightAI's config already points at 8001.

InsightAI connects to the vision service at:

```bash
VISION_SERVICE_URL=http://127.0.0.1:8001
```

`VISION_SERVICE_TIMEOUT_SECONDS` (default `15`) and
`VISION_CONFIDENCE_THRESHOLD` (default `0.5`) are also configurable — see
Configuration below. The knowledge base covers all **38 PlantVillage disease classes**
across 12 crop collections with detailed extension guides and dosage matrices
indexed into the vector store. Real-time diagnosis results and treatment plans
stream via Server-Sent Events on `POST /chat/diagnose/stream`.

## Configuration

All backend configuration lives in `backend/.env` (see `backend/.env.example`), loaded via `pydantic-settings`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key. |
| `API_KEY` | — | **Required.** Shared secret clients must send in the `X-API-Key` header to reach the documents/chat routers — the auth path for non-browser/service clients (scripts, CI). The web frontend uses individual user login (JWT) instead; see `JWT_SECRET_KEY` below. |
| `DATABASE_URL` | — | Optional PostgreSQL connection string (e.g. `postgresql://user:pass@host:5432/db`). When set, document metadata, tenants, users, API keys, chat sessions, and usage logs are persisted in Postgres (tables auto-created at startup; Alembic migrations in `backend/alembic/`). When empty, the app falls back to the legacy in-memory/file stores — those are S3-synced on the AWS Lambda deployment (see `docs/OPERATIONS.md`), but still bound to a single execution environment for correctness (in-memory sessions) and safe concurrent writes (FAISS), enforced by `reserved_concurrent_executions = 1`. Individual user login and chat-history browsing both require this to be set — there's nowhere to persist a `User`/personal `Tenant` otherwise. |
| `JWT_SECRET_KEY` | — | Signing secret for JWTs issued by `POST /auth/signup`/`/auth/login`. Unset = user login unavailable (`AuthConfigurationError`); `X-API-Key` auth is unaffected either way. |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm for the JWT above. |
| `JWT_EXPIRY_MINUTES` | `1440` | How long an issued JWT stays valid. |
| `FRONTEND_URL` | `http://localhost:5173` | Origin allowed by CORS. |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximum accepted PDF size. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | Characters per chunk / overlap between chunks. |
| `OCR_DPI` | `200` | Rasterization DPI for OCR fallback on pages with no text layer. Higher improves accuracy at the cost of extraction time. |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | Sentence Transformers model. |
| `RETRIEVAL_TOP_K` | `5` | Chunks retrieved per query by default. |
| `RETRIEVAL_MIN_SCORE` | `0.3` | Minimum cosine similarity to keep a retrieved chunk. |
| `RETRIEVAL_GRADE_THRESHOLD` | `0.5` | Minimum top-chunk score for retrieval to grade `"good"`. Below it (but above `RETRIEVAL_MIN_SCORE`), retrieval grades `"weak"` — the corrective loop's trigger for the web search fallback below. |
| `WEB_SEARCH_ENABLED` | `false` | Enables the web search fallback for `"weak"`/`"insufficient"` retrieval grades. Off by default. |
| `HYBRID_SEARCH_ENABLED` | `true` | Fuses FAISS semantic search with a BM25 lexical index instead of semantic search alone. On by default — a measured, no-downside win; see `docs/OPERATIONS.md`'s "Retrieval ablation." |
| `RERANKING_ENABLED` | `false` | Re-scores the retrieval candidate pool with a cross-encoder before returning the top results. Off by default — a real but thinly-evidenced (n=7) gain against a real per-request cost; see the same ablation section. |
| `WEB_SEARCH_RESULT_COUNT` | `3` | Web results fetched when the fallback fires. |
| `WEB_SEARCH_TIMEOUT_SECONDS` | `10` | Timeout for the web search call. |
| `GEMINI_MODEL_NAME` | `gemini-3.5-flash` | Gemini model used for answer generation. |
| `GEMINI_TIMEOUT_SECONDS` | `30` | Timeout for Gemini API calls. |
| `COST_PER_1K_TOKENS` | `0.00025` | Estimated USD cost per 1,000 tokens for Gemini, used only to log a rough per-generation cost estimate — not billed usage. |
| `LLM_PROVIDER` | `gemini` | Which provider `/chat` and `/summarize` use: `gemini` or `groq`. Both implement the same `LLMClient` interface (see `services/llm_provider.py`). |
| `FALLBACK_LLM_PROVIDER` | — | Optional. If set to the other provider, `FallbackLLMClient` retries against it after the primary's own retries are exhausted. |
| `GROQ_API_KEY` | — | Required only if `LLM_PROVIDER` or `FALLBACK_LLM_PROVIDER` is `groq`. |
| `GROQ_MODEL_NAME` | `llama-3.3-70b-versatile` | Groq model used for text generation. |
| `GROQ_TIMEOUT_SECONDS` | `30` | Timeout for Groq API calls. |
| `GROQ_COST_PER_1K_TOKENS` | `0.0006` | Estimated USD cost per 1,000 tokens for Groq. |
| `VISION_SERVICE_URL` | `http://127.0.0.1:8001` | Base URL of the LeafSense vision service (separate repo/process). Not LeafSense's own default of `8000` — that collides with this backend's own default port. |
| `VISION_SERVICE_TIMEOUT_SECONDS` | `15` | Timeout for calls to the vision service. |
| `VISION_CONFIDENCE_THRESHOLD` | `0.5` | Below this confidence, a diagnosis is flagged `low_confidence: true` rather than presented as certain. |
| `IMAGE_EXTRACTION_ENABLED` | `false` | Extracts embedded figures (and full-page rasters of low-text pages) from uploaded PDFs and persists the bytes under `IMAGE_STORAGE_DIR_NAME`. |
| `IMAGE_CAPTIONING_ENABLED` | `false` | Captions each extracted image with a vision-capable Gemini call and indexes the caption as a searchable chunk (`source="image_caption"`, citable as "a figure on page N"). Requires `IMAGE_EXTRACTION_ENABLED` and a configured `GEMINI_API_KEY` — with it off (the default), uploads never build an LLM client at all. |
| `TABLE_EXTRACTION_ENABLED` | `false` | Detects ruled-line tables and indexes each as markdown text chunks (`source="table"`), so tables are searchable exactly like body text. |
| `VISION_QA_ENABLED` | `false` | When a question's retrieval grades weak/insufficient, sends the relevant page raster(s) to the vision-capable Gemini model and answers from the image directly (covers scanned/image-only pages). Requires `IMAGE_EXTRACTION_ENABLED`. |
| `IMAGE_STORAGE_DIR_NAME` | `extracted_images` | Directory (under the data dir) where extracted image bytes and the per-document listing manifest live. |
| `IMAGE_MIN_SIDE_PX` | `50` | Images smaller than this on either side are skipped (icons, dividers, noise). |
| `IMAGE_MAX_COUNT_PER_DOCUMENT` | `50` | Cap on extracted image records per document. |
| `IMAGE_CAPTION_MAX_CHARS` | `600` | Captions are truncated to this many characters. |
| `VISION_QA_MAX_PAGES` | `3` | Max page rasters sent to the vision model per vision-QA request. |
| `TABLE_MAX_COUNT_PER_DOCUMENT` | `50` | Cap on tables extracted per document. |

The frontend reads from `frontend/.env`:

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` (dev proxy) | Backend API origin. Leave **unset** in dev — API calls go same-origin through Vite's `/api` proxy (`vite.config.js`), so there's no CORS and no need for the browser to reach the backend host directly (works from localhost and LAN IPs). Set it to the real backend origin only when building for production. |

No API key needed here — the web app authenticates via individual user
login (sign up / log in), which attaches a JWT to every request
automatically (`services/api.js`).

## API reference

Every endpoint except `/health`, `/metrics`, and `/auth/signup`/`/auth/login`
requires authentication — either an `X-API-Key` header matching the
backend's `API_KEY` setting, or an `Authorization: Bearer <jwt>` header
from `POST /auth/login`/`/auth/signup`. A missing or invalid credential
returns `401`.

¹ `/metrics` is unauthenticated by default like `/health` (metrics carry
no payload data); set `METRICS_BEARER_TOKEN` to require an
`Authorization: Bearer <token>` header from scrapers.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Liveness + readiness: LLM provider config (booleans, never a key) and enabled multi-modal capabilities. |
| `GET` | `/metrics` | —¹ | Live metrics in Prometheus text exposition format — request latency (p50/p95/p99), tool and LLM call counts, tokens/cost, loop-capped rate, retrieval timeouts. See `backend/monitoring/README.md`. |
| `POST` | `/auth/signup` | — | Create an account (email, password, consent) — returns a JWT. |
| `POST` | `/auth/login` | — | Log in — returns a JWT. |
| `GET` | `/auth/me` | required | Current caller's identity (email, tenant, role). |
| `POST` | `/upload` | required | Upload a PDF — extracts, chunks, embeds, and indexes it. |
| `DELETE` | `/documents/{document_id}?confirm=true` | required | Remove a document and its vectors from the index. |
| `GET` | `/documents/{document_id}/images` | required | List images extracted from a document (metadata + a `url` per image) — multi-modal RAG. |
| `GET` | `/documents/{document_id}/images/{image_id}` | required | Fetch one extracted image's bytes, served inline with its MIME type. |
| `POST` | `/chat` | required | Ask a question; returns an answer grounded in retrieved chunks. |
| `POST` | `/chat/stream` | required | Same as `/chat`, but streamed as Server-Sent Events — pipeline progress and the answer as it's generated, instead of one response at the end. |
| `POST` | `/chat/diagnose` | required | Upload a plant leaf photo; classifies it via LeafSense, then returns a grounded, cited answer for the predicted disease. |
| `POST` | `/chat/feedback` | required | Record a thumbs up/down (and optional comment) on a previous answer. |
| `GET` | `/chat/sessions` | required | List the caller's own past conversations (title, timestamps). Requires `DATABASE_URL`. |
| `GET` | `/chat/sessions/{session_id}` | required | Full turn history for one session — how the frontend resumes a past conversation. |
| `DELETE` | `/chat/sessions/{session_id}` | required | Delete one conversation. |

**`DELETE /documents/{document_id}`** requires the `confirm=true` query
parameter as an explicit confirmation step — omitting it returns `400`
(`Confirmation Required`) instead of deleting.

**`GET /health`** reports more than liveness — deployment readiness at a
glance:

```json
{
  "status": "ok",
  "llm": {
    "provider": "gemini",
    "provider_configured": true,
    "fallback_provider": "groq",
    "fallback_configured": false,
    "model_routing_enabled": false
  },
  "multimodal": {
    "image_extraction_enabled": false,
    "image_captioning_enabled": false,
    "table_extraction_enabled": false,
    "vision_qa_enabled": false,
    "ocr_available": true
  }
}
```

`provider_configured`/`fallback_configured` are booleans, never the key
itself — `/health` is unauthenticated. `"database": "connected"` is added
when `DATABASE_URL` is set. The frontend surfaces this on the Settings
page's "System status" card.

**`GET /documents/{document_id}/images`** returns the images extracted at
ingestion (read from a per-document manifest, never a re-extraction of
the PDF):

```json
{
  "document_id": "ae845151-86b1-41e8-a63b-69289b88c67a",
  "total": 2,
  "images": [
    {
      "image_id": "ae845151-86b1-41e8-a63b-69289b88c67a_img_4",
      "document_id": "ae845151-86b1-41e8-a63b-69289b88c67a",
      "page_number": 3,
      "content_type": "figure",
      "mime_type": "image/png",
      "width": 640,
      "height": 480,
      "byte_size": 23104,
      "url": "/documents/ae845151-86b1-41e8-a63b-69289b88c67a/images/ae845151-86b1-41e8-a63b-69289b88c67a_img_4"
    }
  ]
}
```

`content_type` is `"figure"` (an embedded image) or `"page"` (a
rasterized full-page render of a low-text page, used by vision QA).
`GET /documents/{document_id}/images/{image_id}` serves the bytes inline
with the image's MIME type; it 404s for an unknown document, unknown
image, or missing file. Both endpoints are tenant-scoped like the rest of
the documents router.

**`POST /chat`** request body:

```json
{
  "query": "What is a project according to the PMP document?",
  "top_k": 5,
  "min_score": 0.3,
  "history": [
    { "role": "user", "content": "What is a project?" },
    { "role": "assistant", "content": "A temporary endeavor..." }
  ]
}
```

`history` is optional — prior conversation turns, oldest first, each
`{ "role": "user"|"assistant", "content": string }`. Only the most recent
6 are used.

response:

```json
{
  "answer": "A project is a temporary endeavor undertaken to create a unique product, service, or result...",
  "retrieved_chunks": [
    { "chunk_id": "...", "document_id": "...", "text": "...", "score": 0.65, "metadata": { "...": "..." } }
  ],
  "sources": [
    {
      "document_id": "ae845151-86b1-41e8-a63b-69289b88c67a",
      "chunk_id": "ae845151-86b1-41e8-a63b-69289b88c67a-0",
      "excerpt": "A project is a temporary endeavor undertaken to create a unique product, service, or result. Projects have a defined beginning and end...",
      "url": null
    }
  ],
  "processing_time": 18.24,
  "tool_used": "retrieval",
  "steps_taken": 4,
  "answer_source": "documents"
}
```

`tool_used` is one of `"retrieval"`, `"summarization"`, `"diagnose"`
(image-based queries via `/chat/diagnose`), `"web_search"` (the
corrective loop's web fallback fired and its results made it into the
final answer, on either a text or image query), or `"none"` (small-talk
queries answered without touching the document index or the LLM).
`steps_taken` counts the agent's
internal steps for that request — planning, retrieval, retrieval grading,
generation, plus one more per regeneration (reflection retry, web search
fetch, web-augmented regeneration) that actually fired — see
`docs/ARCHITECTURE.md`. `answer_source` is `"documents"`, `"web"`, or
`"mixed"`, based on which context actually made it into the final prompt.

`sources` is chunk-level, not document-level: one entry per retrieved
chunk (or web result) the answer was built from, each with its own
`chunk_id` and a `~200`-character `excerpt`, so a citation points at the
specific passage rather than just "this document contributed somehow."
`retrieved_chunks` carries the full document chunks (text, score,
metadata) for callers that need it; `sources` is the trimmed-down shape
the frontend renders as citations, and is the only place web citations
appear (they're not part of `retrieved_chunks`). A web-sourced entry
looks like `{"document_id": "web", "chunk_id": "<url>", "excerpt": "...",
"url": "<url>"}` — `url` is `null` for document citations and set only
for web ones.

**`POST /chat/stream`** — same request body as `POST /chat` (above), same
auth, same underlying pipeline. Instead of one JSON response, it returns
`text/event-stream`: a sequence of SSE `data:` lines, each a JSON object
with a `type`:

- `{"type": "trace", "stage": "planning"|"retrieval"|"grading"|"web_search"|"generating"|"reflecting", "detail": {...}}`
  — emitted as the pipeline progresses through each stage. `detail`'s
  shape depends on the stage, e.g. `{"chunk_count": 5}` for `retrieval`,
  `{"grade": "good"}` for `grading`. A `"reflecting"` stage means the
  corrective loop is discarding the current answer attempt and
  regenerating from scratch — any `answer_chunk` text streamed before it
  belongs to that discarded attempt, not a continuation of it.
- `{"type": "answer_chunk", "text": "..."}` — a piece of the answer, in
  order, as the LLM generates it. Already filtered so the model's own
  "Sources:" citation list (see `tool_used`/`sources` above) never
  reaches the client, the same way the non-streaming path strips it.
- `{"type": "error", "detail": {"error_type": "...", "message": "...", "status_code": 404}}`
  — emitted instead of `"done"` if the pipeline fails partway. SSE
  responses commit to a `200` status as soon as streaming starts, so a
  failure can't become an HTTP error status the way it would on
  `POST /chat`; this is how it's surfaced instead.
- exactly one final `{"type": "done", "payload": {...}}` on success —
  `payload` is the identical `ChatResponse` shape `POST /chat` returns.

`EventSource` (the browser's built-in SSE client) can't send an
`Authorization` header or a POST body, so the frontend consumes this
with `fetch` + a manually-parsed `ReadableStream` instead (see
`frontend/src/services/chatService.js`'s `streamChatMessage`).

**`POST /chat/diagnose`** — `multipart/form-data`, not JSON (FastAPI
resolves a request body as either JSON or multipart per the endpoint's
declared parameters, not per-request, so this couldn't share `/chat`'s
JSON body without breaking every existing text-only caller):

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | file | yes | The leaf photo. |
| `query` | text | no | Optional accompanying question, e.g. "is this from poor fertilization?" — folded into the retrieval query alongside the predicted disease. |

Requires LeafSense to be running and reachable at `VISION_SERVICE_URL`
(see "Running with LeafSense" above); returns `502` if it isn't.

response — the same `ChatResponse` shape as `/chat`, plus a `diagnosis` field:

```json
{
  "answer": "These symptoms indicate Bacterial Spot... nitrogen deficiency symptoms concentrate along the midrib.",
  "retrieved_chunks": [ { "...": "..." } ],
  "sources": [ { "...": "..." } ],
  "processing_time": 4.1,
  "tool_used": "diagnose",
  "steps_taken": 5,
  "answer_source": "documents",
  "diagnosis": {
    "raw_class": "Peach___Bacterial_spot",
    "crop": "peach",
    "disease": "bacterial spot",
    "confidence": 0.94,
    "low_confidence": false
  }
}
```

`diagnosis` is `null` on every other endpoint's response — it's only
populated for `/chat/diagnose`. `low_confidence` is `true` below
`VISION_CONFIDENCE_THRESHOLD`; the answer is still generated (a low-
confidence prediction is a flag for the caller to surface, not a refusal
to answer).

**`POST /chat/feedback`** request body:

```json
{ "message_id": "msg-12-1733500000000", "rating": "up", "comment": null }
```

`message_id` is an opaque client-generated identifier (the frontend's
own message id — the backend has no server-side concept of a message,
since conversations aren't persisted, see Known Limitations). `rating`
must be `"up"` or `"down"`; anything else returns `422`. `comment` is
optional free text. Response: `{ "status": "recorded" }`. Each event is
appended as a JSON line to `backend/feedback/feedback.jsonl` and logged
as an `audit_event`; `eval/metrics_report.py` reads that file to report
an Acceptance Rate (see Evaluation below).

Every response also carries an `X-Request-ID` header (generated, or
echoed back if you send one) for correlating a request against the
backend's structured logs.

Full interactive documentation (generated by FastAPI) is available at `/docs` while the backend is running.

## Evaluation

Hand-run the demo scenarios in
[`docs/demo/DEMO.md`](docs/demo/DEMO.md) — one successful, one failing,
and one recovery path per capability. Automated evaluation is covered
separately: see [`backend/eval/README.md`](backend/eval/README.md) for
the offline harness (`run_eval.py` + the `regression_check.py` CI gate),
[`docs/HUMAN_EVAL.md`](docs/HUMAN_EVAL.md) for the 7-dimension rubric,
and [`docs/CHECKLIST.md`](docs/CHECKLIST.md) for the full production
checklist status.

`backend/eval/` has three independent tools:

- **`run_eval.py`** — runs a dataset (`dataset_v1.json` by default, 16
  entries; `dataset_v2.json` adds 2 web-findable entries for the
  corrective loop's fallback) through the real `ChatService` and reports
  planner routing accuracy (confusion matrix, precision/recall/F1), Task
  Success Rate, a groundedness proxy, Injection Resistance, and — for
  entries with an `expected_source` — **Source Accuracy** (did
  `answer_source` match?). Requires a live `GEMINI_API_KEY` and at least
  one indexed document; Source Accuracy on `dataset_v2.json`'s web
  entries additionally needs `WEB_SEARCH_ENABLED=true`.
- **`metrics_report.py`** — parses the backend's own JSON logs into
  latency percentiles, error rate by taxonomy category, and total
  token/cost usage, and reads `backend/feedback/feedback.jsonl` to report
  **Acceptance Rate** (thumbs-up ÷ total feedback from `POST
  /chat/feedback`) — the LLMOps acceptance-rate metric. A local stand-in
  for real observability, not a replacement for it.
- A manual rubric — [`docs/HUMAN_EVAL.md`](docs/HUMAN_EVAL.md) defines a
  1-5 scoring rubric (correctness, helpfulness, completeness, safety,
  tone, groundedness, citation quality) over the same dataset, for the
  subjective quality the automated metrics above don't capture.

See `backend/eval/README.md` for exact usage, metric definitions, and the
dataset versioning convention, and
[`docs/DESIGN_REVIEW.md`](docs/DESIGN_REVIEW.md) (Q6) for how this fits
into the overall evaluation approach.

## Project structure

```
InsightAI-RAG/
├── backend/
│   └── app/
│       ├── api/v1/routes/     # health, documents, query
│       ├── core/              # config, logging, exceptions, error handlers
│       ├── models/            # Pydantic schemas
│       └── services/          # chunking, embedding, FAISS store, RAG pipeline, Gemini client, multi-modal (images/captions/tables/vision QA)
└── frontend/
    └── src/
        ├── pages/              # Home, Upload, Chat, Documents, Settings
        ├── components/         # chat/, upload/, layout/, ui/
        ├── hooks/              # useChat, useUpload, useTheme, useToast
        └── services/           # api client, chat/document services
```

## Known limitations

- **Single, unsharded FAISS index.** One `backend/vector_store/index.faiss`
  file serves every document, loaded as a single process-wide instance —
  no per-tenant isolation. Concurrent writes are guarded by a `threading.Lock`
  in `FAISSVectorStore` (covers both async `/upload` and sync `DELETE` routes),
  so index/metadata corruption from concurrent writers is prevented.
- **Two auth paths: API keys for service clients, JWT login for the web
  app.** Individual user accounts (`POST /auth/signup`/`/auth/login`) now
  exist for the frontend — each user gets a private tenant, so documents
  and chat history are scoped per-person, not shared across everyone
  holding one API key. No key rotation API, no expiration, no revocation
  without `.env` edit + restart for the API-key side; no password reset
  or refresh-token flow yet for the JWT side (a token is valid for
  `JWT_EXPIRY_MINUTES`, 24h by default, then the user logs in again).
  Basic rate limiting (60 req/min per identity, in-memory sliding window)
  applies to both paths.
- **Document history is per-browser, not server-side.** `GET /documents`
  exists and is tenant/user-scoped, but the Documents page still reads
  `localStorage` rather than calling it — a different browser or device
  shows nothing even though the documents are indexed server-side.
- **Chat history is server-side per `session_id`, bounded by LRU — and
  now browsable, not just an internal store.** In-memory (or Postgres,
  when `DATABASE_URL` is set) store capped at 1000 sessions with LRU
  eviction; each session's history capped at 50 turns, no TTL. When
  Postgres is enabled, `GET /chat/sessions` lists a user's past
  conversations and `GET /chat/sessions/{id}` resumes one (History page)
  — with the DB disabled, sessions still work for the active conversation
  but there's nothing to list.
- **OCR is a best-effort fallback, not equivalent to real text.** It only
  runs on pages with no extractable text layer at all — it doesn't
  improve or re-check pages PyMuPDF already got text from. Accuracy
  depends on scan quality (skew, resolution, handwriting), and it
  requires the `tesseract` system binary (installed in
  `backend/Dockerfile`; not a pip package) — if that binary is missing or
  broken, ingestion degrades to the pre-OCR behavior (page skipped,
  logged as a warning) rather than failing the upload.
- **The corrective loop catches one failure mode.** `ChatService._correct`
  only regenerates when chunks/web-results were available but the answer
  came back empty/fallback — it doesn't catch subtly wrong answers, only
  the "context existed but got ignored" pattern.
- **Extracted-image listing reads a per-document manifest, not the DB.**
  `GET /documents/{id}/images` lists what was persisted at ingestion from
  `{document_id}_images.json` in the image storage dir; documents ingested
  before manifests existed (or with a corrupt/unreadable manifest) list as
  empty even if their bytes are still on disk. Listing is best-effort —
  it never re-extracts the PDF and never fails the request.
- **Retrieval grading is a score threshold, not a semantic judgment.**
  `_grade_retrieval` compares the top chunk's similarity score against
  `RETRIEVAL_GRADE_THRESHOLD` — a chunk can score high while being
  off-topic, or score just under the threshold while actually answering
  the question. It's a cheap proxy for "is this confidently on-topic,"
  not a real relevance check.
- **Web search is off by default and fragile when on.** `WEB_SEARCH_ENABLED`
  defaults to `false`. When enabled, `duckduckgo-search` is an unofficial
  scraper with no API key or SLA — it's known to silently rate-limit or
  return zero results from cloud/data-center IPs (bot detection), with no
  exception raised. `ChatService` treats that identically to "genuinely no
  web results" and falls through to the normal fallback reply, so this
  degrades gracefully rather than erroring — but it means the fallback
  can be quietly unavailable depending on where the backend runs.
- **Groundedness is measured by a lexical-overlap proxy**, not a real
  faithfulness check (see `backend/eval/README.md`).
- **Provider fallback is single-hop.** `FallbackLLMClient` tries the
  primary provider (with its own internal retries), then the fallback
  provider once — if both are down, the request fails. There's no
  health-based routing or automatic recovery back to the primary.
- **No live cloud deployment currently.** The app has run on Render/Vercel
  historically (see `docs/OPERATIONS.md` "Deploying to Render") and is
  self-hostable via Docker Compose, including a production EC2 path
  (`docker-compose.prod.yml`, `docker-compose.caddy.yml` — see
  `docs/OPERATIONS.md` "Deploying to EC2"), where the named Docker volumes
  give real persistent storage with no ephemeral-filesystem workaround
  needed. `demo_seed_service.py`'s auto-seed-on-empty-store behavior still
  runs harmlessly on first boot — a no-op once the store has real data. If
  a `DATABASE_URL` is configured, document metadata, sessions, and usage
  logs also persist in Postgres. An optional S3-sync integration
  (`backend/app/services/s3_sync_service.py`) exists in the codebase for a
  future ephemeral-filesystem deployment target but isn't exercised by any
  current deployment path.

See [`docs/DESIGN_REVIEW.md`](docs/DESIGN_REVIEW.md) and
[`docs/NOT_APPLICABLE.md`](docs/NOT_APPLICABLE.md) for the fuller
reasoning behind these, plus what's explicitly out of scope
(non-document tool integrations, live metrics dashboards) and why.

## Future work

- [ ] Persistent, server-side document history in the *frontend* (backend has `GET /documents` + optional Postgres metadata; the Documents page still tracks uploads per-browser in `localStorage`)
- [ ] Multi-document collections / workspaces
- [ ] Support for additional file types beyond PDF (currently PDF-only; scanned/image-only PDFs are handled via OCR, see Features)
- [x] Per-user authentication (JWT) alongside the existing shared/per-client API key — self-serve signup/login, each user gets a private tenant (see `docs/CHECKLIST.md` §13, `docs/NOT_APPLICABLE.md`'s JWT row); API keys remain for non-browser/service clients, not replaced
- [x] Chat history browsing — `GET /chat/sessions` (list) and `GET /chat/sessions/{id}` (resume), a History page in the frontend; requires `DATABASE_URL` (session listing needs durable storage the in-memory store can't provide)
- [x] RBAC — minimal admin/member role gates on document deletion and cross-tenant document listing (see `docs/CHECKLIST.md` §13); not a general permission/scope system
- [x] Human approval — deployment-toggleable approval gates on web search and document deletion (see `docs/CHECKLIST.md` §1, §13); not a general approval queue
- [x] Encryption at rest for the vector store and uploaded files — S3 default SSE + Lambda's default KMS-encrypted environment variables on AWS (see `docs/CHECKLIST.md` §13); application-level/field-level encryption remains open
- [x] Multi-modal RAG — image extraction (`GET /documents/{id}/images` listing), Gemini figure captioning into searchable chunks, table extraction to markdown, and vision QA over page rasters; all config-gated and off by default (see Features/Configuration)
- [ ] A multi-tenant / shardable vector store, replacing the single FAISS file

## License

MIT © [Udbhav Narawat](LICENSE)
