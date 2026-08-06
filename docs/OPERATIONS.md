# Operations

Procedures for comparing changes, rolling back, and deploying this app —
what actually exists to support each, and what's still manual.

## A/B testing prompt and model changes

There's no built-in A/B traffic-splitting — comparisons are done
offline, sequentially, using the eval harness:

1. **Establish a baseline.** With the current code/config, run:
   ```bash
   cd backend
   python eval/run_eval.py
   ```
   This writes `eval/results/<UTC-timestamp>.json`, capturing planner
   accuracy (confusion matrix, precision/recall/F1), Task Success Rate,
   the groundedness proxy, and Injection Resistance for the full
   `dataset_v1.json` run (see `eval/README.md` for what each metric
   means). Keep this file — rename it or note its timestamp as "baseline."

2. **Change one variant at a time:**
   - **Model variant**: change `GEMINI_MODEL_NAME` in `backend/.env`
     (e.g. try a different Gemini model) and restart the backend.
   - **Prompt variant**: edit `app/services/prompt_builder.py` and bump
     `PROMPT_VERSION` (e.g. `"v1"` → `"v2"`) alongside whatever prompt
     text changed, then restart the backend. Versioning it is what makes
     the change traceable in logs (`generation_requested`/
     `llm_generation_completed` both log `prompt_version`) — bump it for
     *any* prompt change, not just wording tweaks.

3. **Re-run the eval**: `python eval/run_eval.py` again against the
   changed backend. This writes a second, separate
   `eval/results/<timestamp>.json`.

4. **Compare the two result files directly** — `task_success_rate`,
   `groundedness_proxy`, `injection_resistance`, and the planner's
   `accuracy`/`macro_f1`/`weighted_f1` are the headline numbers; the
   `entries` array in each file has the raw per-query answers if you need
   to see *what* changed, not just the aggregate score.

Each results JSON now records `llm_provider`, `fallback_llm_provider`, and
`prompt_version` at the top level, so which variant produced a given run is
no longer something you have to reconstruct from logs — it's in the file
itself. (It still doesn't record `GEMINI_MODEL_NAME`/`GROQ_MODEL_NAME`
specifically if you change the model within a provider rather than the
provider itself; for that, cross-reference the run's timestamp against
`llm_generation_completed` log lines, which do carry `model_name`.)

Because this eval calls the real Gemini API and needs a real indexed
document (`eval/README.md`'s preconditions), it isn't run in CI
(`.github/workflows/ci.yml` has a TODO noting exactly this) — A/B
comparisons are a manual, deliberate step, not something that runs on
every push.

## Retrieval ablation

Two retrieval enhancements, `HYBRID_SEARCH_ENABLED` (FAISS semantic +
BM25 lexical, fused; **on by default**, see below) and
`RERANKING_ENABLED` (cross-encoder re-ranking of the candidate pool; off
by default) are config-gated specifically so they can be A/B'd against
each other and against a semantic-only baseline — same procedure as
above, but read `precision_at_5`/`recall_at_5`/`mrr` from the results
JSON instead (`eval/README.md`'s "Precision@5 / Recall@5 / MRR" section
has the exact definitions). These measure retrieval itself, independent
of what the LLM did with the chunks afterward, which is what makes them
the right metric for this specific comparison — Task Success Rate and
the groundedness proxy can move for reasons that have nothing to do with
retrieval quality (a different LLM sample, in particular).

**A real 3-way run** (`dataset_v2.json`, `LLM_PROVIDER=groq`,
7 content-bearing entries with `expected_chunk_keywords`; "baseline"
below means both flags off, i.e. not this project's actual default):

| Config | Precision@5 | Recall@5 | MRR | Results file |
|---|---|---|---|---|
| Baseline (both off) | 0.3143 | 0.8214 | 0.7500 | `eval/results/20260806T093248Z.json` |
| `+hybrid` | 0.3714 | 0.9643 | 0.9048 | `eval/results/20260806T093526Z.json` |
| `+hybrid+rerank` | 0.4000 | 0.9643 | 0.8095 | `eval/results/20260806T093845Z.json` |

What this run actually shows:

- **Hybrid search was a clean win on all three metrics** — BM25 catching
  exact-term matches (acronyms like "WBS"/"CPI", specific technique
  names) that a pure semantic search sometimes ranks lower than a
  looser paraphrase match. Recall@5 in particular jumped from 0.82 to
  0.96: one more of the "right" chunks made it into the top 5 per query
  on average.
- **Reranking improves Precision@5 further (0.37 → 0.40) at flat
  Recall@5 (0.96 → 0.96); the MRR delta (0.90 → 0.81) is noise, not a
  finding.** Checked directly against the raw per-entry data in
  `20260806T093526Z.json` vs. `20260806T093845Z.json`: exactly **one**
  of the 7 scored queries changed at all — the risk-monitoring edge
  case, whose first relevant chunk moved from rank 1 to rank 3 (still
  inside the top 5, just not first). `(1/1 - 1/3) / 7 ≈ 0.0952`, which
  is the entire observed MRR delta (0.0953) — one query, not a pattern,
  and at n=7 a single query is already ~14% of the sample.

  More importantly, **MRR is the wrong metric to weight for this
  system's architecture.** MRR measures how early the first relevant
  result appears — the metric that matters when a human scans a ranked
  list and clicks one link. `ChatService` doesn't do that: every
  retrieved chunk goes into the prompt as one flat context block
  (`prompt_builder.build_prompt`), so whether the relevant chunk landed
  at rank 1 or rank 3 makes no difference to what the LLM actually sees.
  What matters for this architecture is Precision@5 (how much of what's
  in context is relevant — less noise for the LLM to sift) and Recall@5
  (whether the relevant chunk made it into context *at all*). Both
  either improved or held under reranking. Read this ablation as
  **"reranking improves precision at flat recall; the rank-order
  metric it also moved on is both noise-level and the least
  decision-relevant one for how this system actually consumes
  retrieval results."**
- **Task Success Rate (0.8182) and Injection Resistance (1.0) were
  identical across all three configs**; the groundedness proxy actually
  *dipped* slightly with hybrid/rerank on (1.0 → 0.57 → 0.50). That's
  consistent with the metrics measuring different things: groundedness
  is lexical overlap between the *answer* and *whatever chunks came
  back*, and a wider/different candidate pool changes which chunks
  came back — it's not evidence retrieval got worse (Recall@5 says the
  opposite).

**Is 0.40 Precision@5 actually good? Only relative to how many relevant
chunks exist to find.** Computed directly from the indexed document's 99
chunks (`vector_store/metadata.json`), counting how many chunks actually
contain each query's `expected_chunk_keywords`:

| Query | Relevant chunks in corpus | Max achievable P@5 |
|---|---|---|
| "What is a project…" | 5 | 1.00 |
| "What is a Work Breakdown Structure?" | 1 | 0.20 |
| "What is a Business Case…" | 3 | 0.60 |
| "…CPI greater than 1…" | 3 | 0.60 |
| "…conflict resolution technique…" | 3 | 0.60 |
| "What is Earned Value Management used for?" | 36 | 1.00 |
| risk-monitoring edge case | 1 | 0.20 |
| **Mean** | **7.4** | **0.60** |

(Max achievable P@5 per query is `min(relevant_chunks, 5) / 5` — you
can't score higher than "all 5 slots relevant," and you can't clear
`relevant_chunks / 5` if fewer than 5 relevant chunks exist at all.)

The mean ceiling (0.60) is well above the measured `+hybrid+rerank`
score (0.40) — this system is **not** near a ceiling effect, there's
real precision headroom left. The variance is worth noting too: the
"Earned Value Management" query's ceiling is inflated by "measuring"/
"forecasting"/"performance" being generic project-management vocabulary
that appears in 36 of 99 chunks, not all of them really about EVM
specifically — the same keyword-substring heuristic that defines
Precision@5/Recall@5 (see `eval/README.md`) is doing the counting here
too, so it inherits the same noise for generic-word queries. WBS and the
risk-monitoring query sit at the other extreme: exactly one chunk in the
whole document is relevant, so no retrieval strategy can score above
0.20 on those specific queries no matter how good it is. Read 0.40
against 0.60, not against 1.0.

**Why hybrid search defaults on and reranking doesn't** (`app/core/config.py`):
hybrid search's improvement was unambiguous on every metric with no
added model/network dependency (BM25 is pure CPU, always available), so
it ships as the default rather than sit as an unproven opt-in. Reranking's
gain is real (flat recall, better precision) but thinner evidence (one
ablation run, n=7) against a real cost every other feature here doesn't
have: a second model loaded into memory and cross-encoder inference on
every `retrieve`-action request. That combination — genuine signal, small
n, nonzero cost — is exactly what config-gating an opt-in feature is for;
flipping it to default-on is a call worth revisiting once it's been run
against more queries or a different document.

**Why Groq, not Gemini**: the first attempt used the default
`LLM_PROVIDER=gemini` and hit the free tier's **daily** quota (20
requests/day for `gemini-3.5-flash`) partway through the very first
run — most entries after query 3 failed with `429
RESOURCE_EXHAUSTED`, and the aggregate metrics accordingly cratered
because the failure path scores those entries `0.0` rather than skipping
them (see `run_eval.py`'s except-branch). That contaminated run is not
included in the table above; it's a genuine illustration of why a clean
baseline matters before trusting an ablation number — see
`eval/results/20260806T092932Z.json` if you want to see what a
quota-exhausted run looks like. Switching to `LLM_PROVIDER=groq`
(already a supported provider, see "Comparing providers" below) gave a
clean run for all three configs; the two `summarize`-action entries still
failed on Groq's tokens-per-minute limit for the full-document prompt,
but that doesn't affect Precision@5/Recall@5/MRR, which only score
`retrieve`-action entries.

**To reproduce**: set `LLM_PROVIDER=groq` (or accept Gemini's daily cap
and spread the three runs across multiple days), then for each config,
set `HYBRID_SEARCH_ENABLED`/`RERANKING_ENABLED` in `backend/.env`,
restart the backend, and run `python eval/run_eval.py --dataset
dataset_v2.json --delay 5`.

## Comparing providers (Gemini vs. Groq)

`app/services/llm_provider.py` picks the LLM implementation from
`Settings.llm_provider` ("gemini" or "groq"); both `GeminiClient` and
`GroqClient` implement the same `LLMClient` interface, log the same event
shape (`llm_generation_completed`, now including a `"provider"` field on
both), and share the same tenacity retry policy — so they're a valid,
apples-to-apples A/B pair using the exact procedure above:

1. Run the baseline with `LLM_PROVIDER=gemini` in `backend/.env`,
   `python eval/run_eval.py`.
2. Set `LLM_PROVIDER=groq` and `GROQ_API_KEY` in `backend/.env`, restart
   the backend, re-run `python eval/run_eval.py`.
3. Compare the two results files: `task_success_rate` and
   `groundedness_proxy` for quality, `processing_duration` (from the
   backend logs, keyed by `provider`) for latency, and
   `estimated_cost_usd` (also per-`provider` in the logs) for cost —
   Groq's LPU inference and per-token pricing are expected to win on
   latency and cost; Gemini is the current default because it was the
   original, validated integration.

As above, the results JSON's `llm_provider` field records which one
produced a given run, so the two files from steps 1-2 are
self-identifying — no need to track it separately.

## Automatic provider fallback

Setting `FALLBACK_LLM_PROVIDER` to the *other* provider (e.g.
`LLM_PROVIDER=gemini`, `FALLBACK_LLM_PROVIDER=groq`) wraps the primary
client in `FallbackLLMClient` (`app/services/fallback_llm_client.py`):
if the primary provider's own retries are exhausted
(`LLMTimeoutError`/`LLMAPIError`), one attempt is made against the
fallback provider before the request fails — logged as
`llm_fallback_triggered` with both provider names. This is single-hop
only (see the README's Known Limitations): if both providers are down,
the request still fails, and there's no automatic recovery back to the
primary once it's healthy again — a request-by-request decision, not a
sticky failover state.

## Rollback plan

Nothing here is more sophisticated than git:

- **Tag known-good states.** Before a deploy, tag the commit:
  `git tag -a v0.1.0 -m "known-good: gemini-3.5-flash, PROMPT_VERSION v1"`.
  Since `PROMPT_VERSION` is a source constant (`prompt_builder.py`), not
  an env var, the tagged commit *is* the pin for prompt version — there's
  no separate config file to keep in sync with it.
- **Pin the model via config, not code.** `GEMINI_MODEL_NAME` (and every
  other tunable in `app/core/config.py`) is read from `backend/.env` at
  startup. Keep whatever `.env` values were live for a given tagged
  release recorded somewhere outside git (`.env` is gitignored,
  deliberately, since `backend/.env.example` is the tracked template) —
  a deploy runbook or your platform's secret manager, not the repo.
- **To roll back**: redeploy the tagged commit's Docker image
  (`backend/Dockerfile`, already built and verified locally — see
  `docker-compose.yml`) with the `.env`/secrets that were live for that
  tag. Because `PROMPT_VERSION` and application code move together in
  git, checking out an old tag automatically reverts prompt behavior
  alongside everything else; only the model name (env var) needs to be
  restored separately.
- **Verify the rollback** by re-running `eval/run_eval.py` against it and
  confirming the metrics land back near that tag's original
  `eval/results/*.json`.

There's no automated rollback trigger (no health-based auto-revert, no
canary) — this is a manual procedure, appropriate for the current
single-instance, not-yet-deployed scale (see next section and Q9 in
`docs/DESIGN_REVIEW.md`).

## Deployment recommendation

**Recommendation: a managed container platform — Cloud Run or Render —
over a self-managed EC2 instance.** Both `backend/Dockerfile` and
`frontend/Dockerfile` already build and run correctly via
`docker-compose.yml` (verified locally end-to-end: backend healthcheck
passing, `/health` and `/docs` responding, frontend serving the SPA with
working client-side-route fallback), so either platform could deploy the
existing images with no Dockerfile changes.

Why a managed platform over EC2, specifically for this project:

- **HTTPS out of the box.** This app currently only speaks plain HTTP
  (`uvicorn ... --host 0.0.0.0 --port 8000`, `nginx` serving port 80) —
  there's no TLS termination anywhere in the repo. Cloud Run/Render
  terminate TLS automatically; EC2 would need a reverse proxy (or ALB)
  and certificate management added and maintained.
- **Secret storage.** `backend/.env` currently holds `GEMINI_API_KEY` and
  `API_KEY` as plaintext env vars, loaded via `env_file` in
  `docker-compose.yml` — fine for local dev, not how a real deployment
  should hand out secrets. Both platforms have a managed secrets
  mechanism to replace that file; EC2 would need one wired up manually
  (Secrets Manager + IAM, at minimum).
- **Autoscaling and load balancing**, without provisioning or managing
  the underlying VMs — relevant given the single-`lru_cache`-instance
  architecture (`get_vector_store()`/`get_llm_client()` in
  `app/api/v1/routes/query.py`) doesn't need to change to run on either
  platform's scale-to-zero/scale-out model, since each instance loads its
  own copy of the (currently single, shared-file) FAISS index on
  startup — see Q9 in `docs/DESIGN_REVIEW.md` for why that's still a real
  limitation once you have more than one instance.
- **No OS/patching burden.** EC2 means owning the instance's OS updates,
  security patches, and Docker daemon maintenance; a managed platform
  doesn't.

**This is not yet deployed anywhere.** There's no live URL, no deployment
YAML/Terraform, and no CI step that deploys on merge (`.github/workflows/ci.yml`
only installs dependencies and runs `pytest`). Deploying to Cloud Run or
Render is listed here as the concrete next step, not something already
done — see `docs/DESIGN_REVIEW.md` Q9/Q10 and the README's Future Work
section.
