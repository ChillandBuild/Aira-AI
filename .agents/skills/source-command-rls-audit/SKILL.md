---
name: "source-command-rls-audit"
description: "Multi-tenant isolation audit — runs the tenant-auditor agent over routes/queries, then verifies RLS coverage"
---

# source-command-rls-audit

Use this skill when the user asks to run the migrated source command `rls-audit`.

## Command Template

When this skill is invoked, do the following in order.

## Step 1 — App-layer isolation scan
Dispatch the `tenant-auditor` agent. It scans every file in `backend/app/routes/` for:
- Endpoints missing the tenant dependency (`Depends(get_tenant_and_role)` / `get_tenant_id`)
- `.table(...)` reads without `.eq("tenant_id", tenant_id)`
- `.insert({...})` missing `"tenant_id"`
- Fetch-by-ID-only queries (CRITICAL cross-tenant leak)

Highest-risk files first: `webhook.py`, `bookings.py` (public Razorpay webhook), any `maybe_single()` by ID.

## Step 2 — DB-layer RLS coverage
RLS is ENABLED on all public tables as of migration 114 (`114_rls_launch_blocker`). Verify it still holds:
- List public tables and confirm `rowsecurity = true` on each (Supabase MCP `list_tables`, or `get_advisors` for security warnings).
- Flag any table with RLS off, or any security-definer function with `anon` EXECUTE still granted.
- Note known orphaned tables (`automations`, `automation_flow_runs`, `bot_flows`) — RLS must still be on even though engine code is deleted.

## Step 3 — Reconcile
Cross-check the two layers: a route relying only on app-layer filtering AND a table with RLS off = stacked risk → escalate to CRITICAL.

## Step 4 — Report
Group findings by severity (CRITICAL / HIGH / MEDIUM). Each line:
`[SEVERITY] location — issue — fix`
End with a count per severity and a ship/block verdict. No trailing prose.
