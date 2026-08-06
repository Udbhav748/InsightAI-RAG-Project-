# Not Applicable

Some evaluation/design-review categories don't fit this project. Each
entry below is marked N/A with a one-line reason grounded in what the
codebase actually does (or deliberately doesn't do) — see
[`docs/DESIGN_REVIEW.md`](DESIGN_REVIEW.md) and
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for the fuller picture behind
each.

| Category | Status | Why N/A |
|---|---|---|
| GPU utilization | N/A | Generation runs against the hosted Gemini API (`app/services/gemini_client.py`); the only local model is the small CPU-friendly `all-MiniLM-L6-v2` embedder (`embedding_service.py`), and `backend/Dockerfile` installs the CPU-only torch wheel specifically because no GPU is used or provisioned anywhere in this stack. |
| Agent handoff accuracy | N/A | Single-agent design — one `ChatService` dispatching to two tools, not multiple cooperating agents — so there's no handoff to measure. See `docs/ARCHITECTURE.md`'s "Framework choice" section for why. |
| Weather / SQL / email / GitHub / vision / speech tools | N/A | Out of scope for a document-QA product; the only tools are retrieval and summarization over uploaded PDFs (`retrieval_service.py`, `summarization_service.py`). Note: PDF text extraction (`document_service.py`, PyMuPDF) reads embedded/selectable text only — it is **not** OCR, so a scanned image-only PDF yields little or no text today; OCR support is listed as future work in the README. |
| Encryption at rest | N/A (future work) | Uploaded files and the FAISS index/metadata are plain files on disk (`upload_service.py`, `faiss_vector_store.py`) with no field- or disk-level encryption. |
| JWT / RBAC | N/A (future work) | Auth is a single shared `X-API-Key` secret checked by `app/core/auth.py`'s `require_api_key` — no per-user identity, tokens, or roles/permissions exist. This is implemented instead of JWT/RBAC, not a placeholder for it, at the current single-user scale. |
| Live cloud metrics (Prometheus/Grafana dashboards) | N/A | Nothing is deployed yet (`docs/OPERATIONS.md`) — there's no running instance to scrape. The closest existing tool is `backend/eval/metrics_report.py`, a local script that parses JSON logs after the fact; its own docstring calls this out as a stand-in for real observability infrastructure, not a replacement for it. |
