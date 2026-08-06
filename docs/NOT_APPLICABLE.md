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
| Agent handoff accuracy | N/A | Single-agent design — one `ChatService` dispatching to three tools (retrieval, summarization, web search), not multiple cooperating agents — so there's no handoff to measure. Web search is a hand-coded score-threshold decision, not an LLM-reasoned handoff to a second agent. See `docs/ARCHITECTURE.md`'s "Framework choice" section for why. |
| Weather / SQL / email / GitHub / vision / speech tools | N/A | Out of scope for a document-QA product. The tool surface is retrieval and summarization over uploaded PDFs, plus a narrow web-search fallback for when retrieval alone doesn't confidently answer the question (`retrieval_service.py`, `summarization_service.py`, `web_search_service.py`) — not a general tool-use surface. Note: PDF text extraction (`document_service.py`) reads PyMuPDF's embedded/selectable text first and falls back to OCR (pytesseract/tesseract) only for pages with no text layer at all — see the README's Features section and Known Limitations for what that fallback does and doesn't cover. |
| Encryption at rest | N/A (future work) | Uploaded files and the FAISS index/metadata are plain files on disk (`upload_service.py`, `faiss_vector_store.py`) with no field- or disk-level encryption. |
| JWT / RBAC | N/A (future work) | Auth is a single shared `X-API-Key` secret checked by `app/core/auth.py`'s `require_api_key` — no per-user identity, tokens, or roles/permissions exist. This is implemented instead of JWT/RBAC, not a placeholder for it, at the current single-user scale. |
| Live cloud metrics (Prometheus/Grafana dashboards) | N/A | Nothing is deployed yet (`docs/OPERATIONS.md`) — there's no running instance to scrape. The closest existing tool is `backend/eval/metrics_report.py`, a local script that parses JSON logs after the fact; its own docstring calls this out as a stand-in for real observability infrastructure, not a replacement for it. |
