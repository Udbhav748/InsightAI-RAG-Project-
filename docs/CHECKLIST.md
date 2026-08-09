# Production Checklist — Status

A living map of the strict production checklist (Agentic AI, LLMOps, Cloud
Deployment, Privacy) against what's actually implemented in this repo.
Statuses are updated as gaps are closed. Evidence is `file:line` where
practical.

Status legend:

- ✅ Implemented and verified (tests or measured)
- ⚠️ Partial — exists but incomplete against the checklist's ask
- ❌ Missing
- N/A Deliberately out of scope (see `docs/NOT_APPLICABLE.md`)

---

## 1. Agentic AI Foundations

| Item | Status | Evidence / notes |
|---|---|---|
| Has a planner | ✅ | `ChatService._plan`, `backend/app/services/rag_service.py:311-326` (keyword/regex, no LLM). Actions: `conversational`, `summarize`, `retrieve`, `diagnose`. |
| Has at least two tools | ✅ | Retrieval, summarization, web search, vision — see §3. |
| Memory | ✅ | Session store, in-memory + optional Postgres, `backend/app/services/session_store.py:158-183`, `postgres_session_store.py`; last-6-turns into prompt, `rag_service.py:145`; frontend `session_id` in `localStorage`, `frontend/src/hooks/useChat.js:33-40`. |
| Retry | ✅ | tenacity on LLM + embedding, `gemini_client.py:60-66`, `groq_client.py:60-66`, `embedding_service.py:91-97`. Streaming generation is deliberately not retried (`gemini_client.py:118-126`). Web search now retries transient failures too (`web_search_service.py:44-53`). |
| Reflection | ✅ | Corrective loop `_correct`, `rag_service.py:447-523`; `REFLECTION_INSTRUCTION`, `prompt_builder.py:55-59`; capped at `_MAX_LLM_CALLS=3` (`rag_service.py:58`). |
| Human approval | ⚠️ | Human-in-the-loop gate on the web-search tool (the agent's only outbound side-effect): with `Settings.web_search_requires_approval`, web search only fires when the client sends `confirm_web_search=true`; skipped requests log `web_search_skipped_pending_approval` (`rag_service.py:_search_web`, `schemas.py:ChatRequest`). Default off — a deployment policy, not assumed behavior. |
| Structured output | ⚠️ | Pydantic request/response schemas (`schemas.py`) + **JSON-mode LLM output**: `generate_structured()` via `response_mime_type`/`response_format` (gemini/groq clients), `build_structured_prompt`, validated against `StructuredAnswer` by `structured_output.py`, with free-text fallback. Gated on `Settings.structured_output_enabled` + `ChatRequest.structured_response` — off by default. |
| Error handling | ✅ | `AppError` taxonomy + one global handler, `app/core/exceptions.py`, `error_handlers.py:26-61`. |
| Logging | ✅ | Structured JSON + `request_id` on every line, `app/core/logging.py:17-40`, `main.py:51-68`. |

### Metrics

| Metric | Status | Evidence |
|---|---|---|
| Tool Selection Accuracy | ✅ | Planner confusion matrix + per-class P/R/F1 + Plan-Execution Consistency (decided action vs tool that ran), `run_eval.py`. |
| Task Success Rate | ✅ | Keyword-based, `run_eval.py:448-449,559-561`. |
| Step Efficiency | ✅ | `avg_step_efficiency` = min(expected/actual steps) + avg steps, `run_eval.py` (`EXPECTED_MIN_STEPS`). |
| Tool Success Rate | ✅ | Per-tool successes/attempts, `run_eval.py` `tool_success_rate` (offline) + runtime `tool_invocation` events (`tool_registry.py` `@track_tool`) aggregated by `monitoring/log_aggregate.py`; `--min-tool-success-rate` alert threshold. |
| Loop Rate | ⚠️ | `loop_capped` counted in `metrics_report.py:116-157`; no per-request loop-count metric. |

---

## 2. LangChain, LangGraph & CrewAI

Approach: **map existing hand-rolled code to the framework concepts** — no
framework rewrite (justified in `docs/ARCHITECTURE.md` "Framework choice").

| Concept | Status | Mapping |
|---|---|---|
| LangChain components | ✅ | `RecursiveCharacterTextSplitter` used for chunking, `chunking_service.py:24-32`. |
| LangChain chains | ✅ | Pipeline = deterministic chain (validate→extract→chunk→embed→index; plan→retrieve→grade→generate→correct). |
| LangChain agents / tools | ✅ | Tool callables + formal Pydantic tool I/O schemas + `@track_tool` invocation tracking, `app/services/tool_registry.py`. |
| LangChain memory | ✅ | Session store maps to LangChain `ConversationBufferWindowMemory` (bounded last-6-turns). |
| LangGraph nodes | ⚠️ | Pipeline stages are plain functions; a graph node map is documented in `ARCHITECTURE.md` diagram, not code. |
| LangGraph edges / state | ⚠️ | Implicit — `PlanDecision` dataclass (`rag_service.py:266-269`) + request-scoped state; no explicit graph state object. |
| LangGraph workflow | ⚠️ | `handle_query`/`stream_query` mirror the workflow; not expressed as a graph runtime. |
| LangGraph conditional routing | ⚠️ | `_grade_retrieval` branches (`rag_service.py:396-422`) = the `good/weak/insufficient` conditional edge. |
| CrewAI role | ✅ | `AGENT_ROLE` constant, `prompt_builder.py` (CrewAI-style role/goal/backstory spec) |
| CrewAI goal | ✅ | `AGENT_GOAL` constant, `prompt_builder.py` |
| CrewAI backstory | ✅ | `AGENT_BACKSTORY` constant, `prompt_builder.py` |
| CrewAI task | ✅ | Prompt template + task framing per tool (`_INSTRUCTIONS`, `_WEB_RESULTS_INSTRUCTION`). |
| Agent collaboration | ❌ | Single agent; no collaboration. N/A per `NOT_APPLICABLE.md`. |

### Implementation checklist

| Item | Status |
|---|---|
| Tool abstraction | ⚠️ — tools are plain functions behind `VectorStore`/`LLMClient` interfaces; no shared tool envelope |
| Prompt templates | ✅ — `prompt_builder.py` |
| State management | ⚠️ — request-scoped, no explicit state object |
| Retry | ✅ — LLM/embedding only (§1) |
| Conditional routing | ✅ — planner + retrieval grading |
| Human node | ⚠️ — `confirm_web_search` approval gate on the web-search tool (off by default); no full per-action approval queue |
| Parallel execution | ⚠️ — none in chat path; ingestion embeds in batch (`embedding_service.py:126`) |
| Multi-agent design | ❌ — single agent, N/A |

### Metrics

| Metric | Status |
|---|---|
| Workflow Completion Rate | ⚠️ — derivable from `chat_query_handled` vs `request_failed`, not reported as such |
| Agent Handoff Accuracy | N/A — single agent (`NOT_APPLICABLE.md`) |
| Node Success Rate | ⚠️ — per-stage error taxonomy exists, no per-stage success aggregation |
| Average Node Latency | ⚠️ — per-event latency in `metrics_report.py:67-94` |
| Agent Idle Time | N/A — single request-scoped agent |

---

## 3. Practical Agent Integration

### Tools / capabilities

| Tool | Status | Evidence |
|---|---|---|
| RAG | ✅ | §4 |
| PDF | ✅ | `document_service.py` (PyMuPDF) |
| OCR | ✅ | pytesseract fallback, `document_service.py` |
| Vision | ✅ | `vision_client.py` → LeafSense HTTP |
| API | ✅ | LeafSense HTTP client + FastAPI routes |
| Calculator / Weather / SQL / Email / GitHub / Speech | N/A | Out of scope, `NOT_APPLICABLE.md` |

### Tool checklist

| Item | Status | Evidence / notes |
|---|---|---|
| Every tool documented | ✅ | README + `docs/ARCHITECTURE.md` components |
| Input schema | ✅ | Formal per-tool Pydantic input schemas + runtime validation, `app/services/tool_registry.py` (`RetrievalInput`, `SummarizationInput`, `WebSearchInput`, `DiagnoseInput`); invalid args raise `ToolInputError` (422). |
| Output schema | ✅ | Per-tool output schemas declared in `tool_registry.py` (`RetrievalOutput`, `SummarizationOutput`, `WebSearchOutput`, `DiagnoseOutput`) alongside the typed domain models (`RetrievedChunk`/`WebSearchResult`/`VisionPrediction`). |
| Retry | ✅ | LLM/embedding tenacity + web-search now retries transient failures (`web_search_service.py:44-53`); vision/retrieval fail fast by design (documented). |
| Timeout | ⚠️ | Web 10s (`config.py:151`), vision 15s (`config.py:209`), LLM 30s; retrieval has none |
| Authentication | ⚠️ | Inbound API keys ✅; outbound vision call to LeafSense is **unauthenticated** (`vision_client.py:91-95`) |
| Cost tracking | ✅ | Per-LLM-call cost (`gemini_client.py`/`groq_client.py`) + **per-request rollup** in `chat_query_handled` via `app/core/usage_tracking.py` (`llm_calls`, `total_tokens`, `estimated_cost_usd`). |
| Latency measurement | ✅ | `processing_duration` logged per tool + `tool_invocation` events with `latency_ms` |
| Security / input validation | ✅ | Request schemas + validation_service for uploads |
| Input validation | ✅ | `validation_service.py`, Pydantic request models + tool-registry schemas |

### Metrics

| Metric | Status |
|---|---|
| API Success Rate | ⚠️ | Implicit in error taxonomy; per-tool success rate now logged via `tool_invocation` events |
| Retry Success Rate | ❌ | Not measured |
| Timeout Rate | ⚠️ | Timeouts logged; no rate aggregated |
| Argument Accuracy | ⚠️ | Summarize `document_id` only (`run_eval.py:410-420`) |

---

## 4. Retrieval-Augmented Generation — RAG

### Architecture

Question → Embedding (`embedding_service.py`) → Vector search (`faiss_vector_store.py` +
`hybrid_search.py`) → Top-K (`retrieval_service.py`) → Prompt with evidence
(`prompt_builder.py`) → LLM answer (`gemini_client.py`/`groq_client.py`).

### Checklist

| Item | Status | Evidence |
|---|---|---|
| Chunking | ✅ | `RecursiveCharacterTextSplitter`, 1000/200, `chunking_service.py:24-32` |
| Metadata | ✅ | `{document_id, chunk_index, total_chunks, source}` per chunk, `chunking_service.py:34-47` |
| Embedding | ✅ | `all-MiniLM-L6-v2`, L2-normalized, `embedding_service.py` |
| Vector database | ✅ | FAISS `IndexFlatIP` + positional `metadata.json`, `faiss_vector_store.py` |
| Citation | ✅ | Untrusted-excerpt markers + inline sources instruction, `prompt_builder.py` |
| Source display | ✅ | `ChatResponse.sources`, `schemas.py:45-52,67-68`; `SourceReferences.jsx` |
| Hybrid search | ✅ | BM25 + FAISS fusion 0.6/0.4, `hybrid_search.py` |
| Re-ranking | ✅ | Opt-in cross-encoder, `reranking_service.py` |

### Metrics

| Metric | Status | Evidence |
|---|---|---|
| Precision@K | ✅ | `precision_at_k`, `run_eval.py:151-177` (k=5) |
| Recall@K | ✅ | `recall_at_k`, same |
| Hit Rate@K | ✅ | `hit_at_k` (binary "any relevant in top-k"), `run_eval.py` |
| Mean Reciprocal Rank | ✅ | `reciprocal_rank`, same |
| Groundedness | ✅ | Lexical `is_grounded` (`run_eval.py:118-131`) + LLM-as-judge entailment (`235-265`) |
| Citation Accuracy | ✅ | `citation_supported`, `run_eval.py:180-191` |

---

## 5. Structured Outputs

| Item | Status | Evidence |
|---|---|---|
| JSON output | ⚠️ | `generate_structured()` uses `response_mime_type="application/json"` (gemini_client.py) / `response_format={"type":"json_object"}` (groq_client.py); `StructuredAnswer` validated by `structured_output.py`. Gated off by default (`structured_output_enabled`). |
| Validation | ✅ | Pydantic request/response models, `schemas.py` |
| Pydantic model | ✅ | `schemas.py`, `models/document.py`, `models/db_models.py` |
| Required fields | ✅ | Pydantic required fields + FastAPI 422s |
| Error messages | ✅ | `AppError.detail` + handler mapping |
| Schema Compliance Rate | ⚠️ | Measured on the ChatResponse wire contract (all required fields populated), `run_eval.py` `check_response_schema`; LLM JSON-mode compliance is gate-off pending (Structured-output work package, feature-complete but not default-on). |
| Field Accuracy | ⚠️ | Fraction of ChatResponse field checks passing across entries, `run_eval.py`; LLM-output field accuracy via `StructuredAnswer` validation (off by default). |

---

## 6. Classification Evaluation

| Item | Status | Evidence |
|---|---|---|
| Confusion matrix | ✅ | Planner, `run_eval.py:294-298` |
| Accuracy | ✅ | `run_eval.py:301-330` |
| Precision | ✅ | Same |
| Recall | ✅ | Same |
| Specificity | ✅ | Per-class specificity in `classification_report`, `run_eval.py` |
| F1 Score | ✅ | Macro + weighted, same |
| Macro average | ✅ | Same |
| Weighted average | ✅ | Same |
| TP/FP/TN/FN surfaced | ⚠️ | Computed internally for the matrix, not reported per-class |

---

## 7. Agent Evaluation

| Item | Status | Evidence |
|---|---|---|
| Tool selection verified | ✅ | `expected_action` vs `plan.action`, `run_eval.py:406-420` |
| Tool arguments verified | ⚠️ | Only summarize `document_id`; no generic arg check |
| Planning (action sequence) verified | ✅ | `plan_execution_consistent` (decided action vs executed tool), `run_eval.py` |
| Memory verified | ✅ | `memory_recall_rate` + dataset `history`/`expected_memory_keywords` entries, `run_eval.py` |
| Hallucination detected | ⚠️ | Groundedness proxies; no explicit hallucination detector |
| Grounding verified | ✅ | Lexical + LLM-judge groundedness |
| Task success verified | ✅ | Keyword match, `run_eval.py:448-449` |
| Human approval enforced | ⚠️ | `confirm_web_search` gate on the web-search tool (`web_search_requires_approval`); off by default |
| Task Success Rate | ✅ | |
| Tool Selection Accuracy | ✅ | |
| Average Steps | ✅ | `metrics_report.py:116-157` + `avg_steps_taken`, `run_eval.py` |
| Loop Count | ✅ | `loop_capped` reporting |
| Completion Time | ⚠️ | `processing_duration` logged; no dedicated completion-time metric |

---

## 8. Human Evaluation

| Item | Status | Evidence |
|---|---|---|
| Correctness / Helpfulness / Completeness / Safety / Tone / Groundedness / Citation Quality | ✅ | 7-dimension 1–5 rubric, `docs/HUMAN_EVAL.md:15-39` |
| 1–5 rating scale | ✅ | Anchored per score |
| Likert scale | ✅ | 1–5 Likert-style |
| Inter-Annotator Agreement | ❌ | Not computed — one reviewer available (documented, `HUMAN_EVAL.md:41-51`) |

---

## 9. Debugging

| Item | Status | Evidence |
|---|---|---|
| Trace (every step of one request) | ✅ | SSE `trace` events (`rag_service.py:720-887`) + `trace_event_emitted` logs (`235-243`) |
| Prompt recorded (exact + version) | ⚠️ | `prompt_version` logged (`rag_service.py:339-349`); prompt **content not captured** |
| Tool logs (names, args, outputs, failures) | ⚠️ | Tool names ✅ (`tool_used`); args/outputs ❌ |
| Token logs | ✅ | `llm_generation_completed` fields, `gemini_client.py:93-114` |
| Error logs | ✅ | `request_failed`/`unhandled_exception`, `error_handlers.py` |
| Stack trace | ✅ | `exc_info` on unhandled, `error_handlers.py:50-53` |
| Root cause identified | ⚠️ | `taxonomy_category` narrows it; no explicit root-cause attribution |

### Error taxonomy

| Category | Status |
|---|---|
| input / tool / retriever / prompt / reasoning / output / deployment | ✅ Exceptions exist |
| intent / planner / memory | ⚠️ Declared in vocabulary (`exceptions.py:3-11`) but no exceptions use them |

---

## 10. Observability

| Item | Status | Evidence |
|---|---|---|
| Tracing | ✅ | SSE trace + request_id |
| Logging | ✅ | Structured JSON stdout |
| Metrics | ⚠️ | Offline `metrics_report.py` + `monitoring/log_aggregate.py` rollup; no live metrics |
| Alerts | ⚠️ | Threshold breaches via `log_aggregate.py` exit code; no push/webhook |
| Dashboards | ❌ | None |
| Prompt logs | ⚠️ | Version only, not content |
| Tool logs | ✅ | Names + latency |
| Token usage | ✅ | Per generation |
| Latency | ✅ | P50/P95/P99 in `metrics_report.py:67-94`; live probe latency in `monitoring/uptime_check.py` |
| Errors | ✅ | By taxonomy category |
| Cost | ✅ | `estimated_cost_usd` per generation; summed in `metrics_report.py:160-180` |
| User feedback | ✅ | Thumbs + comment endpoint |
| P50/P95/P99 latency | ✅ | |
| Error Rate | ✅ | `report_error_rate_by_category` |
| Availability | ⚠️ | Probe script `monitoring/uptime_check.py` + 15-min `monitoring.yml` schedule; point-in-time only, no durable SLO |

---

## 11. LLMOps

| Item | Status | Evidence |
|---|---|---|
| Prompt version | ✅ | `PROMPT_VERSION = "v1"`, `prompt_builder.py:15` |
| Dataset version | ✅ | `dataset_vN.json` files + `dataset_version` recorded per run, `run_eval.py` |
| Model version | ✅ | `llm_model_name` + `reranking_model_name` + `embedding_model_name` recorded per run, `run_eval.py` |
| Evaluation pipeline | ✅ | Harness + manual `eval.yml`; now includes regression gate |
| A/B testing | ⚠️ | Manual offline before/after runs, `OPERATIONS.md:8-54` |
| Rollback | ✅ | Documented procedure, exercised on `v0.1.0`, `OPERATIONS.md` |
| Monitoring | ⚠️ | Stand-in `metrics_report.py` + `monitoring/log_aggregate.py` (windowed thresholds); no hosted stack |
| Regression Rate | ✅ | `regression_check.py` gate wired into `eval.yml` (compares vs `baselines/v2_groq.json`) |
| Acceptance Rate | ✅ | Thumbs-up ratio, `metrics_report.py:183-208` |
| Failure Rate | ⚠️ | Error rate by category, not a single failure-rate metric |
| Deployment Frequency | ⚠️ | Auto-deploy on push; no metric |

---

## 12. Cloud Deployment

| Item | Status | Evidence |
|---|---|---|
| FastAPI | ✅ | `app/main.py` |
| Docker | ✅ | `backend/Dockerfile` |
| AWS / EC2 / Lambda / Bedrock / SageMaker / Vertex AI / Azure AI / GPU | N/A | Render + Vercel, `NOT_APPLICABLE.md` |
| HTTPS | ✅ | Platform-provided (Render/Vercel) |
| Secrets | ✅ | Env vars, gitignored `.env`, `.env.example` template |
| Load balancer | ❌ | Single instance, no LB |
| Autoscaling | ❌ | None (free tier) |
| Monitoring | ⚠️ | Stand-in `metrics_report.py` + `monitoring/*.py` scripts, `monitoring.yml` uptime schedule |
| Centralized logging | ⚠️ | Stdout JSON only; `log_aggregate.py` rolls up captured logs on demand |
| Requests per second | ⚠️ | Not measured |
| Latency | ✅ | P50/P95/P99 offline |
| Availability | ⚠️ | `monitoring/uptime_check.py` probes + scheduled `monitoring.yml`; point-in-time |
| Cost per hour | ⚠️ | Not measured |
| CPU/GPU/Memory utilisation | ❌ | Not measured |

---

## 13. Privacy, Security & Responsible AI

| Item | Status | Evidence |
|---|---|---|
| PII | ✅ | Regex detection (email/phone/id), flag-and-continue, `pii_service.py`; recall evals |
| GDPR / DPDP / HIPAA | ⚠️ | No formal compliance assessment doc |
| RBAC | ❌ | Per-client keys only; no roles/users |
| Encryption | ⚠️ | Transport HTTPS platform-level; at-rest platform disk encryption only |
| Consent | ❌ | No consent mechanism |
| Secrets | ✅ | Env vars, gitignored |
| Prompt injection | ✅ | Untrusted-excerpt markers + eval resistance metrics |
| Jailbreak | ⚠️ | Covered via injection markers in eval, no dedicated jailbreak suite |
| Authentication | ✅ | `X-API-Key`, SHA-256 hashed, per-client |
| Authorization | ⚠️ | Per-client only, no RBAC |
| PII detection | ✅ | |
| Secret management | ✅ | |
| Human approval | ❌ | See §1 |
| Audit logs | ✅ | `audit_event` lines + `usage_logs` table |
| PII Recall | ✅ | `eval/pii_recall_check.py` |
| Unauthorized Access Rate | ✅ | Auth + rate-limit unit tests (`tests/test_security.py`); desired value zero |
| Prompt Injection Success Rate | ⚠️ | Eval-resistance computed + prompt-builder unit tests (`tests/test_security.py`); no live adversarial suite |
| False Refusal Rate | ✅ | `run_eval.py:468-469` |
| Data Leak Rate | ✅ | `run_eval.py:471-473` |

---

## 14. Production Readiness

### Architecture

| Item | Status |
|---|---|
| Diagram | ✅ `docs/ARCHITECTURE.md` |
| Components | ✅ |
| Workflow | ✅ |
| Agent (autonomous goal) | ✅ Formal spec (`AGENT_ROLE`/`AGENT_GOAL`/`AGENT_BACKSTORY`), `prompt_builder.py` |
| Planner (selects steps) | ✅ `_plan` |
| Tools (documented capabilities) | ✅ README + ARCHITECTURE |
| Memory (what/how long) | ✅ session store (bounded, LRU) |
| RAG (why retrieval necessary) | ✅ `NOT_APPLICABLE.md` + ARCHITECTURE |

### Evaluation / Debugging / Deployment / Security / Reliability / Cost / Documentation

| Area | Item | Status |
|---|---|---|
| Evaluation | Dataset (normal/edge/failure/adversarial) | ✅ `dataset_v1/v2.json` include all four case types |
| Evaluation | Metrics by cost of failure | ⚠️ Metrics exist; selection rationale partial |
| Evaluation | Human eval rubrics | ✅ `HUMAN_EVAL.md` |
| Debugging | Logs / Traces / Errors | ✅ / ✅ / ✅ |
| Deployment | Docker / Cloud / Monitoring | ✅ / ✅ / ⚠️ |
| Monitoring | Uptime probe / Log rollup / Alerts | ✅ / ✅ / ⚠️ |
| Security | Auth / Authorization / Secrets / Encryption | ✅ / ⚠️ / ✅ / ⚠️ |
| Reliability | Retry / Timeout / Fallback / Cache | ✅ / ✅ / ✅ / ✅ |
| Cost | Tokens / Latency / Model routing / Cache | ✅ / ✅ / ⚠️ / ✅ |
| Docs | README / API / Architecture / Demo / Future work | ✅ / ✅ / ✅ / ✅ / ✅ |

### Final 10-question design review

| Question | Status |
|---|---|
| Why does this need an LLM? | ✅ `docs/DESIGN_REVIEW.md` |
| What decisions are delegated to the LLM? | ✅ |
| Five most likely failure modes | ✅ |
| How will each failure be detected? | ✅ |
| How will the system recover? | ✅ |
| How do you know the new version is better? | ✅ |
| How will user data and secrets be protected? | ✅ |
| Cost per successful task | ✅ (~$0.0006, `DESIGN_REVIEW.md:237-277`) |
| What breaks from 10 → 1M users? | ✅ |
| Would you trust it as a customer? | ✅ |

### Cost metric

| Metric | Status |
|---|---|
| Cost per Successful Task = Total System Cost ÷ Successful Tasks | ⚠️ Manual derivation in `DESIGN_REVIEW.md`; per-request `estimated_cost_usd` now automated in `chat_query_handled` (`usage_tracking.py`), so the rollup is computable from logs — but not yet emitted as a single metric. |

---

## Known doc drift (not checklist items, but affect accuracy of this file)

- *(fixed)* bcrypt → SHA-256: `config.py:56`, `.env.example:21`, `ARCHITECTURE.md`, `DESIGN_REVIEW.md`, `NOT_APPLICABLE.md` all corrected (code uses SHA-256, `auth.py:82`).
- *(fixed)* Deployment status: README + `NOT_APPLICABLE.md:17` now state the live-but-ephemeral free-tier reality (`OPERATIONS.md:561` / `DESIGN_REVIEW.md:322`).

## Work queue (as decided)

Order chosen: **Metrics+eval → LLMOps+CI → Docs+drift → Monitoring → Tool hardening → Human approval + structured output.**

- ✅ Metrics + eval expansion
- ✅ LLMOps + CI gates (eval regression gate in `eval.yml`, security unit tests)
- ✅ Docs + drift fixes (bcrypt, deployment status, agent spec, `docs/demo/DEMO.md`)
- ✅ Monitoring scaffold (`monitoring/uptime_check.py`, `monitoring/log_aggregate.py`, `monitoring.yml`)
- ✅ Tool hardening (`app/services/tool_registry.py` formal I/O schemas + `@track_tool` success-rate logging; web-search retry; per-request cost rollup via `app/core/usage_tracking.py`; `tests/test_tool_registry.py`)
- ✅ Human approval + structured output (`confirm_web_search` gate; `generate_structured` JSON-mode + `StructuredAnswer` validation with free-text fallback; `tests/test_human_approval_structured_output.py`) — both config-gated off by default
- ⏭ Final status pass + commit (user review: pytest, live eval + regression gate, then commit)
