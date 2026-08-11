# InsightAI-RAG: multi-user auth, chat history, and multi-modal RAG — split across two builders

## Context

Three feature tracks, split into two independent work assignments so
Claude and DeepSeek can build in parallel without touching the same
files:

- **Claude → Tracks 1 + 2**: multi-user auth (self-serve signup, JWT
  login) and chat history per session (list/browse/resume). Smaller,
  tightly-scoped, "normal web app" changes — new models, new routes, new
  small React pages — the same shape of work already done this session
  (RBAC, permissions registry, monitoring alerts).
- **DeepSeek → Track 3**: multi-modal RAG (image extraction + captioning,
  vision-grounded QA, table extraction, eventually CLIP/audio/video).
  Heavier — new extraction pipelines, a possible new microservice,
  research-adjacent integration work.

**Why this split doesn't clash**: verified against the actual file list
below — Track 3 never touches `app/core/auth.py`, `app/core/permissions.py`,
`app/models/db_models.py`, or any session/auth route; Tracks 1+2 never
touch `document_service.py`, `gemini_client.py`, or any new
image/table/audio service. The only files both sides might append a line
to are `requirements.txt`, `docs/CHECKLIST.md`, and `README.md` — see
"Shared-file etiquette" below for the one-sentence rule that keeps that
from being a real conflict.

Hard constraint for **both** builders, confirmed explicit by the
project owner: none of this may regress what's already ✅ on
`docs/CHECKLIST.md` (RBAC, the permission registry, authentication,
secrets management, audit logs, rate limiting, tenant isolation, the
271-test pytest suite). Both parts below are additive — new capability
layered on existing primitives, never a replacement of them.

## What must not regress (applies to both builders)

| Existing ✅ checklist item | Claude's tracks | DeepSeek's track |
|---|---|---|
| Authentication (`X-API-Key`) | Extended (adds JWT as a parallel path) — unchanged for existing callers | Not touched at all |
| Authorization (`app/core/permissions.py`) | Not modified — still just reads `request.state.role` | Not touched at all |
| RBAC (`Tenant.role`, `admin_client_names`) | Unchanged mechanism, reused by the new `User`→`Tenant` link | Not touched at all |
| Secrets (SSM `SecureString`) | Extended (`JWT_SECRET_KEY` added to the existing resolved-names tuple) | Not touched unless a new microservice needs its own secret — if so, same SSM mechanism, same tuple |
| Audit logs | Extended with `user_id`/`auth_method` fields, additive | Extended with new event types (`image_extracted`, etc.) following the exact existing `audit_event`/`extra_fields` shape |
| Rate limiting | Unchanged mechanism | Not touched |
| Tenant isolation / ownership checks | Unchanged code path, reused | New image/table/audio metadata must carry the same `document_id`/`tenant_id` scoping every existing chunk already has — see DeepSeek's brief, "Rules" |
| Full pytest suite (271 passed) | Must stay green after Track 1+2 | Must stay green after Track 3 |
| **Consent** (currently ❌) | Becomes a real gap the moment signup stores an email — ships a consent checkbox in the same phase | Not applicable to this track |

## Division of labor & clash-avoidance

| | Claude | DeepSeek |
|---|---|---|
| Branch | `feature/multi-user-history` | `feature/multimodal-rag` |
| Backend files | `app/models/db_models.py` (new `User`), `app/core/auth.py` (new `require_auth`), `app/core/config.py` (JWT settings), new `app/api/v1/routes/auth.py`, new session-list routes, new `alembic/versions/0003_*.py` and `0004_*.py` | `app/services/document_service.py`, `app/services/gemini_client.py`, new `app/services/image_embedding_service.py` (Phase 5+), possibly a new standalone microservice repo/dir for CLIP/Whisper (Phase 5-6) |
| Frontend files | `contexts/AuthContext.jsx`, `pages/Login.jsx`/`Signup.jsx`, `services/api.js` (interceptor), `App.jsx` (protected routes), `hooks/useChat.js` (`loadSession`), `components/layout/Sidebar.jsx` (History nav), `services/chatService.js` | None until a phase needs a frontend affordance (e.g. "show extracted images inline") — coordinate with Claude's side at that point rather than editing shared components solo |
| Dependency on the other | None — Track 3's chunking/embedding of image/table content reuses the *existing* `tenant_id`/`document_id` scoping regardless of whether the caller authenticated via API key or the new JWT path | None — multi-user auth doesn't care what kind of content a document contains |
| Merge order | Either order works; no ordering dependency exists between the two branches | Same |

**Shared-file etiquette** (the only three files either side might touch):
- `requirements.txt` — append your own new lines at the end; never reorder or reformat existing lines.
- `docs/CHECKLIST.md` — each side only edits the rows it actually changed (Claude: Authentication/Authorization/RBAC/Consent rows in §13, plus the Architecture "Memory" row for chat history; DeepSeek: the RAG/§4 rows and Cost/Model-routing row in §14). Don't touch a row the other side owns.
- `README.md` — append to the roadmap checkbox list; don't rewrite existing checked items.

---

# PART A — Claude's scope: Tracks 1 & 2

## The key architectural insight (why this is lower-risk than it sounds)

Verified directly in the code (`app/models/db_models.py`,
`app/services/tenant_service.py`, `app/core/auth.py`): every table that
needs privacy is already scoped by `tenant_id`, and today's
`resolve_tenant()` already creates one `Tenant` per distinct
`client_name` — i.e., the existing system is already "one identity = one
tenant," not a shared-team-workspace model. "Fully private per user" (a
decision already made) is achieved by giving each signed-up **User**
their own personal `Tenant` (1:1) at signup time. That means:

- `Document.tenant_id` and `ChatSession.tenant_id` need **zero schema
  changes** for ownership/privacy.
- The permission registry needs **zero changes** — JWT login just
  becomes a second way to arrive at a `(tenant_id, role)` pair.
- `Settings.admin_client_names` keeps working unchanged.

## Track 1 — Multi-user support

Locked-in decisions: self-serve signup; fully private per user (via the
1:1 personal-tenant trick above); the web frontend migrates fully to
JWT, `X-API-Key` stays for non-browser/service clients.

**New model** (`app/models/db_models.py`): `User` — `id`, `email`
(unique, indexed), `password_hash`, `tenant_id` (FK → `tenants.id`),
`created_at`. No `role` column on `User` — role stays on `Tenant`.

**Password hashing**: `bcrypt` directly — **not** the existing SHA-256
convention (SHA-256 is correct for already-high-entropy API keys;
passwords need a slow, salted hash).

**New Alembic migration** (`0003_users.py`): creates `users`, FK to
`tenants`.

**New routes** (new `app/api/v1/routes/auth.py`):
- `POST /auth/signup` — email + password + consent checkbox → creates a
  `Tenant` (slug = a generated id, not the raw email) and a `User` row
  in one transaction, returns a JWT.
- `POST /auth/login` — email + password → `bcrypt.checkpw`, return a JWT.
- `GET /auth/me` — current user's email/tenant/role.

**New settings** (`config.py`): `jwt_secret_key` (added to
`_load_secrets_from_ssm`'s tuple), `jwt_algorithm: str = "HS256"`,
`jwt_expiry_minutes: int = 1440`.

**`app/core/auth.py`**: new `require_auth` dependency — checks
`Authorization: Bearer <jwt>` first (sets `request.state.{client_name=
email, tenant_id, role, user_id, auth_method="jwt"}`); falls through to
the existing `require_api_key` logic unchanged if absent
(`auth_method="api_key"`). Routers switch `Depends(require_api_key)` →
`Depends(require_auth)` — a superset, not a behavior change, for
existing callers.

**Frontend**: new `contexts/AuthContext.jsx` (mirrors
`ThemeProvider`/`ToastProvider`), `pages/Login.jsx`, `pages/Signup.jsx`,
a protected-route wrapper in `App.jsx`, an axios interceptor in
`services/api.js` attaching `Authorization: Bearer <token>` (token in
`localStorage`, same pattern `session_id` already uses).

## Track 2 — Chat history per session

Verified gap: `ChatSession`/`ChatTurn` are already written on every
`/chat` call, but nothing reads them back for listing — no `GET
/chat/sessions` route exists, and the frontend has no history UI at all
(only "current conversation" + "start new").

**New migration** (`0004_chat_session_title.py`): adds nullable
`ChatSession.title`, populated from the first user turn (truncated).

**New routes**:
- `GET /chat/sessions` — list the caller's own sessions
  (`request.state.tenant_id`), ordered by `last_accessed_at` desc.
- `GET /chat/sessions/{session_id}` — full turn history, with an
  ownership check mirroring `documents.py`'s cross-tenant pattern (new
  `get_session_owner()`).
- `DELETE /chat/sessions/{session_id}` — replaces today's header-based
  `DELETE /chat/session` (which has a dead-code JSON-body path that
  never actually runs) with a path param. Update the frontend's
  `deleteChatSession()` call site in the same change.

**Frontend**: new "History" nav item, a page listing sessions
(title, timestamp, delete), and `loadSession(sessionId)` in
`useChat.js` hydrating `messages` from the server — additive next to
the existing "New Chat" flow.

## Claude's verification

- New `tests/test_auth_routes.py` (signup/login/me, wrong password,
  duplicate email) + confirm `check_permission()` behaves identically
  for a JWT-authenticated admin vs an API-key-authenticated admin.
- New `tests/test_chat_sessions.py` (list, get, ownership denial for
  another user's session, delete).
- Full `pytest` must stay at 271+ passed, zero regressions.
- Playwright smoke test (same pattern used earlier this session): sign
  up, chat, refresh, confirm the conversation reappears in History.
- `docs/CHECKLIST.md`: flip **Consent** from ❌ to a real evidenced
  status once the signup consent checkbox ships.

---

# PART B — DeepSeek's brief (self-contained — hand this section to DeepSeek as-is)

## About this project

InsightAI-RAG is a full-stack RAG app: upload a PDF, it gets chunked,
embedded (Sentence Transformers `all-MiniLM-L6-v2`), and indexed into a
FAISS `IndexFlatIP` vector store; users chat with it and every answer is
grounded in retrieved passages with cited sources. Backend: FastAPI
(`backend/app/`), layered routes → services, two abstractions injected
rather than imported directly — `VectorStore` (`services/vector_store.py`,
implemented by `FAISSVectorStore`) and `LLMClient`
(`services/llm_client.py`, implemented by `GeminiClient`/`GroqClient`).
Orchestrating services depend only on these interfaces, never on a
concrete implementation — this is why you can add a new modality without
rewriting orchestration code, only extending it.

The project has an existing, proven pattern for connecting an external
ML capability as its own service: **LeafSense**
(`app/services/vision_client.py`) — a separate FastAPI + TensorFlow
process, called over plain `httpx`, with its own exception type
(`VisionServiceError`), its own timeout/retry config, and its own
`X-API-Key`-style auth. Follow this exact shape for any new microservice
you introduce (CLIP embedding service, ASR service) — own process, own
heavy deps, thin client in this repo, never import the heavy ML
library (torch, whisper, etc.) directly into this backend's own
`requirements.txt` unless it's genuinely lightweight.

## Your job: Track 3 — Multi-modal RAG

| # | Feature | Track | Effort | Notes |
|---|---|---|---|---|
| 1 | Extract embedded images from PDFs | — | S | `page.get_images()`, PyMuPDF (`fitz`) is **already installed** — no new dependency |
| 2 | Caption extracted images via Gemini vision input, index captions in the existing text vector store | A | M | Extend `gemini_client.py`'s `generate()` (or add a new method) to accept an image part alongside text — Gemini's API supports this natively |
| 3 | Vision-grounded QA on full page images (for scanned/complex layouts where OCR degrades) | A | M | Same image-input path as #2, applied to a full rasterized page instead of an extracted figure |
| 4 | CLIP image embeddings + cross-modal retrieval | B | L | New microservice, LeafSense-shaped; fuses with `hybrid_search.py`'s existing semantic+BM25 fusion as a third signal |
| 5 | Table extraction → structured Q&A | B or Python lib | M–L | Prefer `pdfplumber` (pure-Python, no native deps) over `camelot` (needs ghostscript/poppler) unless `pdfplumber`'s table detection proves insufficient |
| 6 | Audio ingestion (Whisper transcription, timestamped chunks) | B | M | New microservice or hosted ASR API; start with a hosted API before self-hosting `faster-whisper` |
| 7 | Video ingestion (audio track + keyframes) | A+B | L | Combines #2 + #6 |
| 8 | Voice input / voice output | A or B | S–M | Lowest priority — pure UX layer, doesn't gate anything else |

**Build in this order**: 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8. Phases 1-3
specifically need no new microservice and no new heavy dependency —
they're the highest-value, lowest-risk place to start.

**Track A vs B, in one sentence**: send it straight to Gemini (Track A,
cheap, no new infra) unless the capability is something Gemini's API
genuinely can't do — a real vector embedding space for image-to-image
search (Track B, needs a new service).

## Rules — read before touching anything

1. **Every new chunk/embedded object must carry the same `tenant_id`/`document_id` scoping every existing text chunk already has.** Look at `app/services/embedding_service.py` and `app/models/document.py`'s `EmbeddedChunk` for the exact shape. An image caption or table-derived text chunk is, from the vector store's point of view, just another chunk — reuse `chunking_service.py`/`embedding_service.py` rather than inventing a parallel storage path, unless the modality genuinely needs its own index (only true for #4's CLIP embeddings).
2. **Every new feature is off by default behind a `Settings` boolean**, matching every existing feature in this codebase (`web_search_enabled`, `reranking_enabled`, `model_routing_enabled`, all default `False`, documented in `backend/.env.example`). Do not make new behavior default-on.
3. **New exceptions subclass `AppError`** (`app/core/exceptions.py`) with a real `status_code` and `taxonomy_category` — do not raise bare `Exception` or introduce a new error-handling mechanism; one global handler already maps every `AppError` subclass automatically.
4. **New external service calls get retried and timed out** the same way `vision_client.py`/`web_search_service.py` already do (`tenacity`, a configurable `Settings.*_timeout_seconds`) — a hung external call must never hang the whole request indefinitely.
5. **Update `eval/dataset_v2.json` (or a new `dataset_v3.json`) with the new case type** for each phase you ship (an image-grounded question, a table-lookup question) — the existing harness (`eval/run_eval.py`, `eval/regression_check.py`) does not need new code, just new dataset entries with the right `expected_*` fields.
6. **Update `docs/CHECKLIST.md`** only in the rows you actually changed — the RAG section (§4) and the Cost/Model-routing row (§14) are yours; do not touch the Security/Authorization/RBAC rows, those belong to the parallel multi-user work.
7. **Run the full `pytest` suite before considering any phase done.** It must stay at 271+ passed — if a change you made breaks an existing test, fix the break, don't skip or delete the test.
8. **Do not touch**: `app/core/auth.py`, `app/core/permissions.py`, `app/models/db_models.py`, anything under `app/api/v1/routes/` that isn't directly about document/RAG content, or any frontend file under `frontend/src/contexts/`, `frontend/src/pages/Login.jsx`/`Signup.jsx`. These are the other builder's files, in progress on a different branch, at the same time as your work.
9. **Work on branch `feature/multimodal-rag`.** Don't merge to `main` yourself — open a PR for the project owner to review, same as every other change in this repo's history.

## Deliverables per phase (what "done" means)

- **Phase 1 (image extraction)**: `document_service.py` returns extracted images (bytes + page number + a stable id) alongside its existing text/OCR result; a unit test confirms a PDF with a known embedded image yields at least one extracted image record.
- **Phase 2 (captioning)**: each extracted image gets a Gemini-generated caption, chunked and embedded into the existing FAISS index with metadata identifying it as image-derived (so citations can say "from a figure on page N" instead of implying body text); an eval dataset entry whose only correct answer requires the image's content, not the surrounding text.
- **Phase 3 (vision QA)**: a config-gated path where, for pages that would otherwise OCR poorly (reuse the existing `ocr_min_chars_per_page` decision point), the full page image is sent to Gemini directly instead of/alongside the OCR'd text.
- **Phase 5 (tables)**: extracted tables become structured text (e.g., a markdown table or explicit "row: X, column: Y, value: Z" sentences) fed into the same chunking pipeline, with an eval entry that only a correct table lookup can answer.
- **Phase 4 (CLIP)**: a new microservice + thin client (LeafSense-shaped), a second vector index (own `image_index.faiss`/`image_metadata.json`, mirroring `faiss_vector_store.py`'s existing persistence shape), and a fusion step in retrieval reusing `hybrid_search.py`'s pattern.
- **Phase 6-7 (audio/video)**: new ingestion path (own upload route or an extended one), transcript chunked/embedded like any document; flag to the project owner if synchronous processing time becomes a real problem — that's the point where a job queue (see the Infra Components table below) stops being optional.

## Infrastructure you might need (evaluate, don't add speculatively)

| Component | When you'd actually need it |
|---|---|
| Job queue (`arq`, Celery, RQ) | Only once audio/video ingestion (Phase 6-7) makes synchronous request processing take minutes instead of seconds — flag this to the project owner rather than adding it preemptively |
| Redis | Same trigger as above, or if the CLIP/ASR microservice needs a shared cache — don't add it "just in case" |

---

## Final merge checklist (both parts)

- [ ] Both branches pass the full `pytest` suite independently (271+ passed each).
- [ ] Merging either branch first, then the other, produces no logical conflicts — only trivial line-adjacency conflicts in `requirements.txt`/`docs/CHECKLIST.md`/`README.md`, resolved by keeping both sides' additions.
- [ ] `docs/CHECKLIST.md` reviewed once more after both merge, to catch anything either side's edits made stale in a row the *other* side owns (e.g. if Track 3's new chunk type changes what "Metadata" in §4 means).
- [ ] Neither side has touched the other's "do not touch" list.
