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
  Also pushes a webhook alert on failure — see "Push alerts" below.
- `log_aggregate.py` — windowed rollup over a captured backend JSON log
  (same line format `eval/metrics_report.py` consumes): error rate (with
  breakdown by `taxonomy_category`), p50/p95/p99 latency, corrective-loop
  cap rate, **per-tool success rate** (from the `tool_invocation` events
  emitted by `app/services/tool_registry.py`'s `@track_tool`), token
  totals, and estimated cost. Fails (exit 1) if any of
  `--max-error-rate`, `--max-p95-latency-ms`, `--max-loop-capped-rate`, or
  `--min-tool-success-rate` is breached — thresholds act as the alerts stub.
  Also pushes a webhook alert on breach — see "Push alerts" below.
- `alert_webhook.py` — shared, dependency-free helper the two scripts
  above call: POSTs a Slack-compatible `{"text": ...}` payload via stdlib
  `urllib`. Best-effort — a broken or unset webhook never fails the check
  it's reporting through; the check's own exit code remains the real signal.

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

## Push alerts

Both `uptime_check.py` and `log_aggregate.py` accept `--alert-webhook-url`
(or the `ALERT_WEBHOOK_URL` env var) and POST a short text summary to it
via `alert_webhook.py` whenever they'd otherwise exit non-zero — a Slack
incoming webhook URL works directly; Discord's `/slack`-compatible
webhook endpoint and a Teams connector both accept the same `{"text":
...}` shape. Unset (the default): behavior is unchanged from before —
the job exit code / failed workflow run remains the alert surface, no
network call is made.

```bash
python monitoring/uptime_check.py --alert-webhook-url https://hooks.slack.com/services/...
python monitoring/log_aggregate.py app.log --alert-webhook-url https://hooks.slack.com/services/...
```

## CI / scheduling

- `.github/workflows/monitoring.yml` runs `uptime_check.py` against the
  deployed endpoints every 15 minutes (and on manual dispatch); a failed
  probe fails the job, and pushes to `ALERT_WEBHOOK_URL` (a repo Secret)
  if one is configured.
- For log aggregation in CI, first capture a log artifact (uvicorn stdout)
  and then run `log_aggregate.py` on it — see `.github/workflows/ci.yml`.

## Known limitations (deliberate)

- `uptime_state.json` lives on local disk / the ephemeral Actions workspace;
  trailing availability is therefore point-in-time, not a durable SLO.
- Push alerts are un-debounced: a long-lived `--loop` run that stays down
  alerts on every iteration, not just the first transition into failure.
  Not an issue for the scheduled CI run, which only checks once per
  invocation.
- Latency figures are from the probing machine's network, not server-side.
