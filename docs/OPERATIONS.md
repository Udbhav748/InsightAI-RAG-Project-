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

**Known gap**: `run_eval.py`'s output JSON does not itself record which
`GEMINI_MODEL_NAME` or `PROMPT_VERSION` produced it — that's implicit in
whatever you changed in step 2. To recover it after the fact, cross-reference
the run's timestamp against the backend's own logs for that window
(`generation_requested` and `llm_generation_completed` lines both carry
`prompt_version`; nothing in the current logs carries the Gemini model
name directly, though `llm_generation_completed` does log `model_name`).
Recording the variant identifier directly in the results JSON would be a
reasonable improvement to `run_eval.py`.

Because this eval calls the real Gemini API and needs a real indexed
document (`eval/README.md`'s preconditions), it isn't run in CI
(`.github/workflows/ci.yml` has a TODO noting exactly this) — A/B
comparisons are a manual, deliberate step, not something that runs on
every push.

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
