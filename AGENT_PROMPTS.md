# Agent Implementation Prompts for 10/10 Features

This document contains detailed prompts for two agents to implement 5 features in parallel without conflicts.

---

## AGENT 1: Core Architecture & Infrastructure Agent

### Responsibilities
- Feature 1: **AgentExecutor + PlanningAgent** - Replace ChatService orchestration with ReAct loop
- Feature 3: **pgvector Migration** - Replace FAISS with pgvector for multi-tenant isolation
- Feature 5: **Nightly Eval Job** - Automated quality regression detection

### Files You Own (Exclusive Write Access)


### Feature 1: AgentExecutor + PlanningAgent (Core)

#### Objective
Replace ChatService.handle_query() hardcoded action branches with a ReAct-style AgentExecutor where an LLM planner chooses tools dynamically.

#### Implementation Steps

1. Create backend/app/services/planning_agent.py
   - PlanningAgent class with LLM-based planner outputting structured ExecutionPlan
   - PlanStep dataclass: tool, args, reason
   - ExecutionPlan dataclass: steps list, final_answer_tool
   - Defensive JSON parsing with fallback to single retrieval step
   - Uses ToolRegistry.describe_all() for tool descriptions

2. Create backend/app/services/agent_executor.py
   - AgentExecutor class with ReAct loop: Plan -> Act -> Observe -> Repeat
   - Max 5 iterations, capped at 3 LLM calls for synthesis
   - ToolContext passed to each tool execution
   - Integrates with AgentMemory for context injection
   - Returns AgentResult with answer, sources, steps_taken, tool_used, answer_source

3. Create backend/app/services/agents/ specializations
   - DocumentAnalyst: deep document QA (wraps retrieval + synthesis)
   - WebResearcher: wraps ResearchAgent for multi-step web research
   - FactChecker: cross-references claims against sources
   - Summarizer: wraps SummarizationService
   - All implement common Agent interface with run(query, context) method

4. Modify backend/app/services/rag_service.py
   - ChatService.handle_query() delegates to AgentExecutor
   - ChatService.stream_query() delegates to streaming AgentExecutor
   - Preserve all existing behavior: corrective loop, grading, streaming trace events
   - AgentExecutor handles tool selection; ChatService becomes thin orchestrator

5. Modify backend/app/api/v1/routes/query.py
   - Wire AgentExecutor in get_chat_service()
   - Inject PlanningAgent, ToolRegistry, AgentExecutor
   - Keep session management, history, authentication unchanged

### Feature 3: pgvector Migration

#### Objective
Replace FAISS single-file index with pgvector for ACID deletes, per-tenant isolation, horizontal scaling.

#### Implementation Steps

1. Modify backend/app/core/config.py
   Add settings:
   - PGVECTOR_ENABLED (bool, default False for gradual migration)
   - PGVECTOR_DIMENSIONS (int, default 384 for all-MiniLM-L6-v2)
   - PGVECTOR_TABLE_PREFIX (str, default vec_)

2. Modify backend/app/core/database.py
   - Add pgvector extension enablement in init_db()
   - Create async engine/session for vector operations
   - Add vector_store_enabled() check

3. Modify backend/app/models/db_models.py
   Add SQLAlchemy models:
   - DocumentChunk: id, document_id, tenant_id, chunk_index, text, embedding (vector), metadata (JSONB)
   - DocumentEmbedding: id, document_id, tenant_id, model_name, dimension
   - Index metadata table for tracking

4. Create backend/app/services/pgvector_store.py
   Implement VectorStore interface:
   - search(query_embedding, top_k, min_score, tenant_id, document_ids) -> list[RetrievedChunk]
   - add_chunks(chunks, embeddings, tenant_id) -> None
   - delete_document(document_id, tenant_id) -> None (DELETE with WHERE clause)
   - get_chunks_by_document(document_id, tenant_id) -> list[RetrievedChunk]
   - total_vectors(tenant_id) -> int
   - load() / persist() no-ops (DB is persistent)
   - Uses asyncpg/async SQLAlchemy for performance

5. Modify backend/app/services/vector_store.py
   - Update VectorStore abstract base class with new methods
   - Add tenant_id to all method signatures
   - Add document_ids filter to search()

6. Modify backend/app/services/faiss_vector_store.py
   - Add deprecation warnings
   - Keep functional for fallback when PGVECTOR_ENABLED=False
   - Mark for removal in future version

7. Modify dependent services
   - retrieval_service.py: use injected VectorStore (pgvector or FAISS)
   - document_processing_service.py: use VectorStore.add_chunks()
   - upload_service.py: pass tenant_id through pipeline

8. Create Alembic migration
   - backend/alembic/versions/xxxx_add_pgvector_tables.py
   - Enable pgvector extension
   - Create tables with HNSW index for performance
   - Add indexes on tenant_id, document_id

9. Update backend/requirements.txt
   - Add: pgvector, asyncpg, psycopg[pool], sqlalchemy[asyncio]

### Feature 5: Nightly Eval Job

#### Objective
Automated nightly evaluation that runs test dataset, detects regressions, posts results.

#### Implementation Steps

1. Create backend/eval/nightly_eval.py
   - NightlyEvaluator class
   - Load dataset_v2.json (includes web-findable entries)
   - Run through real ChatService (with AgentExecutor)
   - Compute metrics: Task Success Rate, Groundedness, Source Accuracy, Hallucination Rate, Injection Resistance
   - Compare against baseline thresholds (configurable)
   - Generate markdown report with diff vs previous run
   - Save report to backend/eval/reports/nightly_YYYYMMDD.md

2. Create backend/eval/scheduler.py
   - APScheduler background job
   - Runs daily at 02:00 UTC (configurable)
   - Only runs if NIGHTLY_EVAL_ENABLED=True and GEMINI_API_KEY set
   - Logs start/completion/failure to structured logs

3. Create .github/workflows/nightly-eval.yml
   - Scheduled workflow (cron: 0 2 * * *)
   - Runs on ubuntu-latest
   - Installs deps, runs nightly_eval.py
   - Uploads report as workflow artifact
   - Creates GitHub Issue on regression (title: Nightly Eval Regression YYYY-MM-DD)
   - Posts summary to Slack/Discord webhook (optional, configurable)

4. Modify backend/eval/run_eval.py
   - Add --nightly flag that outputs machine-readable JSON
   - Used by nightly_eval.py for metrics extraction

5. Add config to backend/app/core/config.py
   - NIGHTLY_EVAL_ENABLED (bool)
   - NIGHTLY_EVAL_BASELINE_TSR (float, default 0.85)
   - NIGHTLY_EVAL_BASELINE_HALLUCINATION (float, default 0.10)
   - NIGHTLY_EVAL_WEBHOOK_URL (str, optional)

### Agent 1 Boundaries (DO NOT TOUCH)
- Frontend files (frontend/**)
- CI/CD for linting (Agent 2 owns .github/workflows/ci.yml)
- Grafana/Prometheus configs (Agent 2 owns)
- Authentication routes (auth.py, user_service.py)
- Document upload validation (validation_service.py)

---

## AGENT 2: Developer Experience & Observability Agent

### Responsibilities
- Feature 2: **mypy --strict + ruff in CI** - Catch bugs before merge
- Feature 4: **Grafana Dashboards + Alerts** - Observe production reality

### Files You Own (Exclusive Write Access)


### Feature 2: mypy --strict + ruff in CI

#### Objective
Add static type checking and linting to CI pipeline to catch bugs before merge.

#### Implementation Steps

1. Create backend/pyproject.toml
   [tool.mypy]
   python_version = 3.11
   strict = true
   warn_unused_ignores = true
   warn_redundant_casts = true
   disallow_untyped_defs = true
   disallow_incomplete_defs = true
   check_untyped_defs = true
   no_implicit_optional = true
   warn_return_any = true
   warn_unused_configs = true
   ignore_missing_imports = true
   exclude = [backend/alembic/**, backend/vector_store/**, backend/uploads/**, backend/eval/**]

   [tool.ruff]
   line_length = 100
   target-version = py311
   select = [E, F, I, UP, W, PL, C4, T20, PI, PT, RUF, RET, SIM, ASYNC, ARG, PTH, ERA, LOG, NPY, TCH, TRY, DTZ, EXE, FUR, PLC, PLR, PLE, PLW, S, B, A, COM, C90, FA, PD, PGH, TID, RSE, ICN, PT, Q, RUF, RET, SIM, ASYNC, ARG, PTH, ERA, LOG, NPY, TCH, TRY, DTZ, EXE, FUR, PLC, PLR, PLE, PLW]
   ignore = [E501, D100, D101, D102, D103, D104, D105, D106, D107, ANN001, ANN002, ANN003, ANN201, ANN202, ANN204, ANN401]
   per-file-ignores = {backend/tests/** = [S101, SLF001], backend/alembic/** = [*]}

   [tool.ruff.format]
   quote-style = double
   indent-style = space

2. Create .github/workflows/lint.yml
   - name: Lint & Type Check
     on: [push, pull_request]
     jobs:
       backend-lint:
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4
           - uses: actions/setup-python@v5
             with: {python-version: 3.11}
           - run: pip install -r backend/requirements.txt
           - run: pip install mypy ruff
           - run: cd backend && mypy --strict .
           - run: cd backend && ruff check .
           - run: cd backend && ruff format --check .
       frontend-lint:
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4
           - uses: actions/setup-node@v4
             with: {node-version: 20}
           - run: cd frontend && npm ci
           - run: cd frontend && npm run lint
           - run: cd frontend && npm run typecheck

3. Modify .github/workflows/ci.yml
   - Add lint job that runs before tests
   - Fail fast on lint/type errors

4. Create frontend/eslint.config.js (flat config)
   - extends: [@react, @typescript-eslint, prettier]
   - rules: no-unused-vars: error, no-explicit-any: warn

5. Create frontend/.prettierrc
   - singleQuote: true, trailingComma: es5, printWidth: 100

6. Modify frontend/tsconfig.json
   - strict: true, noUncheckedIndexedAccess: true, exactOptionalPropertyTypes: true

7. Modify frontend/package.json
   - Add scripts: lint, lint:fix, typecheck, test, test:watch
   - Add devDeps: vitest, @testing-library/react, @testing-library/jest-dom, eslint, @typescript-eslint/parser, @typescript-eslint/eslint-plugin, prettier, eslint-config-prettier

### Feature 4: Grafana Dashboards + Alerts

#### Objective
Production-grade observability with dashboards and alerting for RAG pipeline metrics.

#### Implementation Steps

1. Create docker-compose.monitoring.yml
   - prometheus:9090, grafana:3000, alertmanager:9093
   - Volumes for prometheus data, grafana dashboards/provisioning
   - Network shared with backend

2. Create monitoring/prometheus.yml
   - scrape_configs:
     - job_name: insightai-backend
       metrics_path: /metrics
       static_configs: [{targets: [backend:8000]}]
     - job_name: node-exporter
       static_configs: [{targets: [node-exporter:9100]}]
   - rule_files: [alert_rules.yml]
   - alerting: alertmanagers: [{static_configs: [{targets: [alertmanager:9093]}]}]

3. Create monitoring/alert_rules.yml
   Groups:
   - rag_pipeline: HighLatency (p99 > 10s), HighErrorRate (> 1%), LoopCappedRate (> 5/min), RetrievalTimeoutRate (> 10%)
   - agent: HandoffFailureRate (> 2%), AgentIdleTime (> 30s avg)
   - system: HighMemoryUsage (> 85%), HighCPUUsage (> 80%), DiskSpaceLow (< 10%)
   - business: LowTaskSuccessRate (< 0.8), HighHallucinationRate (> 0.15)

4. Create monitoring/grafana/dashboards/overview.json
   - Request rate, latency p50/p95/p99, error rate by category
   - Token usage/cost per hour, active sessions, documents indexed

5. Create monitoring/grafana/dashboards/rag_pipeline.json
   - Retrieval grade distribution (good/weak/insufficient)
   - Corrective loop trigger rate, web search fallback rate
   - Steps taken distribution, tool_used breakdown
   - Groundedness score histogram, citation verification rate

6. Create monitoring/grafana/dashboards/agent_metrics.json
   - Agent handoff count by type (router->research, retrieval->research)
   - Planner accuracy (confusion matrix), research agent steps distribution
   - Tool success/failure rates, tool latency p50/p95

7. Create monitoring/grafana/dashboards/system.json
   - CPU, memory, disk, network for backend container
   - FAISS index size, vector count, PostgreSQL connections
   - Queue depths, thread pool utilization

8. Modify backend/app/core/metrics.py
   - Add Prometheus Counter, Histogram, Gauge for all above metrics
   - Use prometheus-client library
   - Export via /metrics endpoint (already exists, enhance)

9. Modify backend/app/core/logging.py
   - Ensure structured logs include metric labels (tenant_id, tool, agent, etc.)
   - Add log-based metric extraction for non-instrumented events

10. Update backend/requirements.txt
    - Add: prometheus-client, prometheus-fastapi-instrumentator, prometheus-async

### Agent 2 Boundaries (DO NOT TOUCH)
- Core agent orchestration (Agent 1 owns agent_executor.py, planning_agent.py, pgvector_store.py)
- Database models/migrations (Agent 1 owns db_models.py, alembic/)
- Evaluation infrastructure (Agent 1 owns nightly_eval.py, scheduler.py)
- ChatService internal logic (Agent 1 modifies rag_service.py)

---

## COORDINATION RULES

1. **No overlapping file writes** - Each agent only modifies files in their owned list
2. **Shared interfaces only** - Both agents may read VectorStore interface, LLMClient interface, ToolRegistry
3. **Config changes** - Agent 1 owns backend/app/core/config.py for pgvector/nightly_eval settings; Agent 2 owns for metrics/logging settings
4. **Requirements.txt** - Both may append; use separate requirement sections with comments
5. **Git workflow** - Each agent works on separate branch: agent1/architecture, agent2/observability
6. **Integration point** - Agent 1's AgentExecutor exposes metrics that Agent 2's Prometheus scrapes
7. **Testing** - Write tests in backend/tests/ for your features; integration tests in backend/tests/test_integration.py

---

## DEFINITION OF DONE PER FEATURE

### Feature 1 (AgentExecutor)
- [ ] PlanningAgent outputs valid ExecutionPlan for 10/10 test queries
- [ ] AgentExecutor completes ReAct loop without errors
- [ ] ChatService.handle_query() delegates to AgentExecutor
- [ ] Streaming (/chat/stream) works with AgentExecutor trace events
- [ ] All existing tests pass (planner routing, corrective loop, tool usage)

### Feature 3 (pgvector)
- [ ] PGVECTOR_ENABLED=True uses pgvector; False uses FAISS (no code changes elsewhere)
- [ ] delete_document() is O(1) not O(n)
- [ ] Multi-tenant isolation: tenant A cannot see tenant B chunks
- [ ] Alembic migration runs clean on fresh DB
- [ ] All retrieval tests pass with both backends

### Feature 5 (Nightly Eval)
- [ ] nightly_eval.py runs manually and produces report
- [ ] GitHub Actions workflow triggers on schedule
- [ ] Regression creates GitHub Issue with metrics diff
- [ ] Baseline thresholds configurable via .env

### Feature 2 (Lint/Typecheck)
- [ ] mypy --strict passes on backend/ (zero errors)
- [ ] ruff check passes on backend/ (zero errors)
- [ ] Frontend eslint + prettier + tsc --noEmit pass
- [ ] CI fails on any lint/type error

### Feature 4 (Grafana)
- [ ] docker-compose.monitoring.yml starts all 3 services
- [ ] Prometheus scrapes /metrics from backend
- [ ] 4 dashboards load in Grafana with real data
- [ ] Alert rules fire correctly (test with alertmanager test)
- [ ] Dashboards provisioned automatically (no manual import)
