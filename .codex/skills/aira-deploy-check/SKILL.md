---
name: aira-deploy-check
description: Production health check for Aira. Use when the user says "deploy-check", "/deploy-check", "aira-deploy-check", asks whether production is healthy, wants backend health, scheduler health, Render deployment status, or keep-alive cron verification.
---

# Aira Deploy Check

Run a concise production health check. Prefer primary tools when available, and request approval for network commands if the sandbox blocks them.

## Checks

1. Backend liveness:
   ```powershell
   curl.exe -s -o NUL -w "%{http_code}" --max-time 120 https://aira-ai-5tfr.onrender.com/health
   ```
   `200` is PASS. Retry once on timeout or non-200.

2. Scheduler health:
   - Prefer `GET /api/v1/operator/scheduler-health` if credentials/config are available.
   - Otherwise query `scheduler_runs` through Supabase if the project is connected.
   - Verify these jobs are recent within interval plus grace:
     `scheduled-broadcasts`, `reengagement-rules`, `callback-reassignment`,
     `assignment-sweep`, `broadcast-retries`, `recycle-contacts`,
     `engagement-decay`, `token-health-check`, `number-quality-sync`,
     and caller coaching digest.

3. Latest Render deploy:
   - Use Render MCP/tools if available.
   - Check service `aira-ai-backend`.
   - Latest live deploy is PASS; build/update failure is FAIL.

4. Keep-alive cron:
   - Confirm `.github/workflows/keep-alive.yml` uses cron `*/14 * * * *`.
   - If `gh` is available and authenticated, run:
     ```powershell
     gh run list --workflow keep-alive.yml --limit 1
     ```

## Output

Return one table with `step`, `status`, and `detail`. Use only `PASS`, `WARN`, or `FAIL`. End with overall `HEALTHY`, `DEGRADED`, or `DOWN`.
