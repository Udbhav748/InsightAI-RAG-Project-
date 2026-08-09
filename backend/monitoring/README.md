# Monitoring

A lightweight, dependency-free observability stand-in for the deployed
backend — the Render free tier ships no hosted uptime monitor, metrics, or
alerting, so these scripts close the gap cheaply. They are NOT a
replacement for Prometheus/Grafana/Loki/CloudWatch: on-demand, pull-based,
no long-term storage, no dashboards. See `docs/CHECKLIST.md` §10.

## Files

- `uptime_check.py` — availability probe for the backend (`/health`) and
  frontend. Reports reachability, HTTP status, latency, and a trailing
  availability percentage persisted in `uptime_state.json`. Exit 0 = all
  healthy, exit 1 = any target failed (so a scheduler can alert on non-zero).
- `log_aggregate.py` — windowed rollup over a captured backend JSON log
  (same line format `eval/metrics_report.py` consumes): error rate (with
  breakdown by `taxonomy_category`), p50/p95/p99 latency, corrective-loop
  cap rate, **per-tool success rate** (from the `tool_invocation` events
  emitted by `app/services/tool_registry.py`'s `@track_tool`), token
  totals, and estimated cost. Fails (exit 1) if any of
  `--max-error-rate`, `--max-p95-latency-ms`, `--max-loop-capped-rate`, or
  `--min-tool-success-rate` is breached — thresholds act as the alerts stub.

## Usage

```bash
# Availability, once (local defaults)
python monitoring/uptime_check.py

# Live deployed endpoints
BACKEND_URL=https://insightai-rag-backend.onrender.com \
FRONTEND_URL=https://insight-ai-rag-project.vercel.app \
python monitoring/uptime_check.py --json

# Log aggregation over a captured uvicorn log (see eval/metrics_report.py
# for how to capture it), with thresholds
python monitoring/log_aggregate.py app.log --max-error-rate 0.05 --max-p95-latency-ms 5000
```

## CI / scheduling

- `.github/workflows/monitoring.yml` runs `uptime_check.py` against the
  deployed endpoints every 15 minutes (and on manual dispatch); a failed
  probe fails the job.
- For log aggregation in CI, first capture a log artifact (uvicorn stdout)
  and then run `log_aggregate.py` on it — see `.github/workflows/ci.yml`.

## Known limitations (deliberate)

- `uptime_state.json` lives on local disk / the ephemeral Actions workspace;
  trailing availability is therefore point-in-time, not a durable SLO.
- No push notification path (email/Slack/webhook) — the alert surface is the
  job exit code / failed workflow run. Wiring a webhook is a follow-up.
- Latency figures are from the probing machine's network, not server-side.
