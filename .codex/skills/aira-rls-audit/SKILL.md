---
name: aira-rls-audit
description: Multi-tenant isolation and Supabase RLS audit for Aira. Use when the user says "rls-audit", "/rls-audit", "aira-rls-audit", asks to audit tenant isolation, check RLS coverage, scan backend routes for tenant_id filters, or verify cross-tenant data safety.
---

# Aira RLS Audit

Use this with the Supabase skill/tools when database verification is needed. This is the Codex version of `.claude/commands/rls-audit.md`.

## Step 1: App-Layer Isolation Scan

Scan `backend/app/routes/` first. Prioritize:

- `webhook.py`
- `bookings.py`
- Any endpoint that fetches records by ID with `maybe_single()`
- Public webhook/payment routes

Look for:

- Endpoints missing `Depends(get_tenant_and_role)` or `get_tenant_id`.
- Supabase `.table(...)` reads missing `.eq("tenant_id", tenant_id)`.
- Inserts missing `"tenant_id"`.
- Fetch-by-ID-only queries that could leak cross-tenant data.

Useful commands:

```powershell
rg -n "maybe_single|\\.single\\(|\\.table\\(|tenant_id|Depends\\(get_tenant|Depends\\(get_tenant_and_role|get_tenant_id" backend\app\routes
rg -n "\\.insert\\(|\\.upsert\\(" backend\app\routes
```

## Step 2: DB-Layer RLS Coverage

Verify all public tables still have RLS enabled. Prefer Supabase MCP:

- List public tables and confirm `rowsecurity = true`.
- Run Supabase security advisors.
- Flag any public table with RLS off.
- Flag security-definer functions with `anon` EXECUTE still granted.

Known orphaned or legacy tables still require RLS if present: `automations`, `automation_flow_runs`, `bot_flows`.

## Step 3: Reconcile Risk

Escalate to CRITICAL when both are true:

- A route relies only on app-layer filtering or has missing tenant filtering.
- The backing table has RLS disabled or overly permissive policies.

## Output

Group findings by severity:

```text
[CRITICAL] location - issue - fix
[HIGH] location - issue - fix
[MEDIUM] location - issue - fix
```

End with counts per severity and a ship/block verdict. Keep summaries brief and do not bury findings.
