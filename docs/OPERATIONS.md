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

## Bulk corpus ingestion

`POST /upload` goes through the frontend's 60s axios timeout (and
whatever patience sits in front of the server beyond that). OCR alone
runs roughly a second or more per page at `Settings.ocr_dpi`
(`document_service.py`) — a single 60-page scanned document can exceed
that timeout on its own, well before a real multi-document corpus would.
Don't bulk-ingest a corpus through the HTTP endpoint.

`backend/scripts/ingest_corpus.py` drives `DocumentProcessingService`
directly instead — one file at a time, from a plain Python process, no
HTTP layer or request timeout involved:

```bash
cd backend
python scripts/ingest_corpus.py path/to/corpus_dir
```

It walks `corpus_dir` recursively for `*.pdf` by default (`--pattern` and
`--no-recursive` adjust that), runs each file through the exact same
`validate_pdf_upload` + `DocumentProcessingService.process()` the HTTP
route uses — no pipeline logic duplicated — and prints per-file progress
(pages, chunks, pages OCR'd, duration) plus a final summary. One bad file
(corrupt, oversized, wrong type) is logged and skipped; it doesn't stop
the rest of the corpus.

By default it writes to the same index the running app uses
(`backend/vector_store/`). Pass `--index-path`/`--metadata-path` (both
required together) to build a separate index instead — useful for a dry
run, a scratch/experimental corpus, or comparing corpora side by side
without touching the live one. This is also the repeatable way to
rebuild the index from a known set of source PDFs whenever it's needed
— e.g. after a chunking/embedding config change, or once documents carry
shared/private metadata tags.

Each ingested file is still copied into `backend/uploads/` under a UUID
name, same as a real `/upload` (see `upload_service.py`) — ingesting a
large corpus roughly doubles its disk footprint, which is expected, not
a bug.

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
  `git tag -a v0.1.0 -m "known-good: llama-3.3-70b-versatile via Groq, PROMPT_VERSION v1"`.
  Since `PROMPT_VERSION` is a source constant (`prompt_builder.py`), not
  an env var, the tagged commit *is* the pin for prompt version — there's
  no separate config file to keep in sync with it.
- **Pin the model via config, not code.** `GEMINI_MODEL_NAME`/`GROQ_MODEL_NAME`
  (and every other tunable in `app/core/config.py`) is read from
  `backend/.env` at startup. Keep whatever `.env` values were live for a
  given tagged release recorded somewhere outside git (`.env` is
  gitignored, deliberately, since `backend/.env.example` is the tracked
  template) — a deploy runbook or your platform's secret manager, not
  the repo.
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

**This procedure has actually been exercised, not just written down.**
`v0.1.0` was tagged at `0e289c3`, checked out into an isolated
`git worktree` (so the build genuinely came from the tagged ref, not
just whatever happened to already be checked out), built into a Docker
image, and run against `eval/run_eval.py` — reproducing the same planner
accuracy (1.0), Task Success Rate (1.0), Injection Resistance (1.0),
tool-argument accuracy (1.0), and the same known Groq TPM 413 on the two
`summarize` entries as the baseline run
(`eval/results/20260807T215538Z.json`) it was compared against. The one
metric that moved (groundedness proxy: 0.8333 → 0.9167) is expected
run-to-run noise from LLM sampling on a 12-sample lexical-overlap
heuristic, not a regression — worth knowing as the expected variance
band before ever needing this procedure under real pressure.

There's no automated rollback trigger (no health-based auto-revert, no
canary) — this is a manual procedure, appropriate for the current
single-instance, not-yet-deployed scale (see next section and Q9 in
`docs/DESIGN_REVIEW.md`).

## Deploying to Render

**Backend → Render (Docker). Frontend → a static host (Vercel or
Cloudflare Pages), not a container.** `backend/Dockerfile` already builds
and runs correctly via `docker-compose.yml` (verified locally end-to-end:
healthcheck passing, `/health` and `/docs` responding) — Render deploys
that same image, not a rewrite. `frontend/Dockerfile`'s nginx stage stays
for local `docker-compose.yml` parity, but production frontend serving
moves off it: it's a static Vite build, and paying for container compute
(or routing it through `nginx`) to serve static files has no upside once a
CDN-backed static host does it for free with less to maintain.

Render over Cloud Run: **Cloud Run requires a GCP billing account (a
payment method on file) even to use its free-tier resources.** That's a
hard blocker, not a preference — Render's free tier needs no card at all.
The real cost of that choice is memory: Render's free web service instance
caps at **512MB RAM**, tight for `sentence-transformers` + `torch` + a
loaded FAISS index alongside FastAPI. See "Memory" below for how that's
handled.

### The constraint that shapes everything below: an ephemeral filesystem

Render's free tier wipes the entire local filesystem on every spin-down —
not just on redeploy. A free service spins down after **15 minutes of no
traffic** and spinning back up is a full rebuild, not a resumed container
(confirmed against Render's own docs). Persistent disks exist on Render,
but only on paid tiers.

Practically: anything uploaded through `/upload` — and the FAISS index it
builds — is gone the next time the service goes idle for 15 minutes. This
isn't a corruption risk (unlike the concurrent-writer problem
`threading.Lock` in `faiss_vector_store.py` already closes) — it's that the
app's core "upload once, ask questions later" loop doesn't survive a normal
idle gap on this tier at all.

**Handled by auto-seeding a bundled demo document on cold start.**
`backend/demo_corpus/pmp_key_concepts.pdf` is baked into the image;
`app/services/demo_seed_service.py`, wired into `main.py`'s FastAPI
`lifespan` handler, ingests it automatically on startup *only if the vector
store is empty* — a genuine cold start (Render) seeds fresh, a warm process
with real data (local dev, or any platform with real persistent storage)
is untouched. This means the live demo always has something to query
against out of the box. It does **not** solve persistence for a real
uploaded document — that still won't survive an idle gap on the free tier,
which is a known, documented limitation, not something silently papered
over.

### Memory

The embedding model is pre-downloaded into the image at build time (see
the Dockerfile's `RUN python -c "from sentence_transformers import
SentenceTransformer; SentenceTransformer(...)"` step) so a cold start
doesn't also pay for a Hugging Face download on top of loading it — that
step alone measured at roughly a minute over a slow/unauthenticated
connection locally.

`render.yaml` ships with **`RERANKING_ENABLED: false`**. Before the two
fixes below, `docker run --memory=512m` against the built image locally
peaked at ~497MB (97% of the 512MB limit) and survived — but **the first
real Render deploy OOM-killed anyway** ("Ran out of memory (used over
512MB)"), confirming the local Docker Desktop VM used to build/test this
doesn't reproduce Render's actual memory accounting closely enough to
trust a locally-passing test as sufficient on its own.

Two fixes closed most of that gap, verified with a second round of the
same local test:

- **Thread pools constrained** (`Dockerfile`:
  `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS`/`MKL_NUM_THREADS=1`,
  `TOKENIZERS_PARALLELISM=false`). torch/numpy/faiss default their
  BLAS/OMP thread pool to the *visible* CPU count, which in a container
  often reflects the host's full core count rather than the fraction
  actually allocated (Render's free tier: 0.1 CPU) — each extra thread
  allocates its own buffers, real memory, not just wasted scheduling.
- **Batched embedding encoding** (`Settings.embedding_batch_size`,
  default 8, `embedding_service.py`). Encoding an entire document's
  chunks in one `encode()` call was a real, measured transient memory
  spike; smaller batches trade a little throughput for a materially
  lower peak.

Together: peak dropped from ~500MB (97.7%) to **~480MB (93.8%)** —
real headroom gained, not just theorized, though still not a
comfortable margin. **Reranking stays off**: it loads a second model (a
cross-encoder) on top of the embedding model, and there's no headroom
in that peak to absorb it. `HYBRID_SEARCH_ENABLED` stays `true` — pure
CPU (BM25), no second model (see "Retrieval ablation" above). If a real
Render deploy still OOMs after these fixes, the next lever is
`EMBEDDING_BATCH_SIZE` lower than 8, then `HYBRID_SEARCH_ENABLED=false`
as a last resort before considering a paid tier.

### Deploying

No `gcloud`-equivalent CLI needed — Render deploys straight from a
connected GitHub repo:

1. Sign up at [render.com](https://render.com) (no card required for the
   free tier).
2. **New → Blueprint**, connect the GitHub repo. Render reads `render.yaml`
   at the repo root and provisions the service it describes.
3. During the Blueprint creation flow, Render prompts for every `envVar`
   marked `sync: false` in `render.yaml`: `GEMINI_API_KEY`, `API_KEY`,
   `GROQ_API_KEY`, and `FRONTEND_URL` (leave `FRONTEND_URL` as a placeholder
   until the frontend's real URL exists — step below — then update it in
   the dashboard; CORS will reject requests from the real frontend until
   this matches exactly).
4. Deploy. Render builds `backend/Dockerfile` and serves on the URL it
   assigns (`https://insightai-rag-backend.onrender.com`-shaped).

### Deploying the frontend

Vercel or Cloudflare Pages, whichever's preferred — genuinely
interchangeable for a static Vite build, and neither needs a
platform-specific config file. Both auto-deploy on push via their own git
integration, no GitHub Actions step needed for this half of the app.
Build settings, identical on either platform:

- Build command: `npm run build`
- Output directory: `dist`
- Env vars (build-time — Vite inlines `VITE_*` at build time, not runtime,
  see `frontend/Dockerfile`'s existing comment on why): `VITE_API_BASE_URL`
  = the Render backend's URL, `VITE_API_KEY` = the same value as the
  backend's `API_KEY` secret.

Once the frontend has a real URL, go back to the Render dashboard and set
`FRONTEND_URL` to it — this is the CORS allowlist `main.py` checks against.

### Before making this reachable by anyone but you

`docs/OPERATIONS.md`'s A/B section above already documents hitting Gemini's
free-tier cap (20 requests/day) mid-eval-run — why `render.yaml` defaults
`LLM_PROVIDER` to `groq`. If a paid Gemini tier is available instead, switch
it back in the dashboard; either way this is a config decision already
supported today, not new engineering.

**This is not yet deployed anywhere.** The pieces above (`Dockerfile`,
`render.yaml`, `demo_seed_service.py`) are ready to run, but no Render
service has actually been created from this repo yet — there's no live URL.
Deploying is a manual step the project owner runs with their own Render
account; see `docs/DESIGN_REVIEW.md` Q9/Q10 for what's still a known
limitation regardless (single global index, no per-tenant isolation).
