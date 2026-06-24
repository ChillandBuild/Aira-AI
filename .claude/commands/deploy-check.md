---
name: deploy-check
description: Production health check — backend /health, scheduler jobs, latest Render deploy, keep-alive cron
---

When this skill is invoked, do the following in order. Report each step as a one-line PASS/WARN/FAIL.

## Step 1 — Backend liveness
`curl -s -o /dev/null -w "%{http_code}" --max-time 120 https://aira-ai-5tfr.onrender.com/health`
- 200 → PASS. Non-200 / timeout → FAIL (Render free tier may be cold-starting; retry once).

## Step 2 — Scheduler health
Fetch the operator scheduler-health view (`GET /api/v1/operator/scheduler-health`) or query `scheduler_runs`.
Verify all 10 jobs have run within their interval + grace:
- 1-min jobs: `scheduled-broadcasts`, `reengagement-rules`, `callback-reassignment`
- `assignment-sweep` (2m), `broadcast-retries` (5m), `recycle-contacts` (30m)
- `engagement-decay` (6h), `token-health-check` (24h), `number-quality-sync` (24h)
- `caller coaching digest` (daily 13:00)
- Any job with no recent run or a logged error → WARN with the job id + last_run + error.

## Step 3 — Latest Render deploy
Use the Render MCP (`list_deploys` for service `aira-ai-backend`).
- Latest deploy `live` → PASS. `build_failed` / `update_failed` → FAIL with the deploy id.

## Step 4 — Keep-alive cron
Confirm `.github/workflows/keep-alive.yml` cron is `*/14 * * * *` and the last GH Actions run succeeded (`gh run list --workflow keep-alive.yml --limit 1`).
- Success → PASS. Failing → WARN (backend will cold-start, but app still works).

## Step 5 — Summary
One table: step / status / detail. End with overall verdict (HEALTHY / DEGRADED / DOWN). No trailing prose.
