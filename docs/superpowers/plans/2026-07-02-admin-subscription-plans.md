# Admin-Customizable Subscription Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded messaging/telecalling/AI-tier plan system with a single admin-authored plan model, delete the Fleet page and "View as tenant" impersonation feature, and wire the new Subscription page + Feature Store + tenant-creation wizard to it.

**Architecture:** `plans` becomes a flat `{name, monthly_price, feature_keys[], quotas{}}` table the system admin edits from a new "Subscription" console page (replacing Fleet's sidebar slot). `tenant_subscriptions` drops its three old plan/tier fields for a single nullable `plan_id`. `resolve_entitlements()` collapses to one plan lookup. The Feature Store and onboarding wizard become plan pickers instead of a-la-carte toggles/tier pickers.

**Tech Stack:** FastAPI + Supabase (Postgres) backend (`backend/app/routes/operator.py`, `backend/app/services/entitlements.py`), Next.js 14 App Router frontend (`frontend/app/operator/(console)/...`), Python `unittest` for backend tests, `npm run typecheck` / `npm run lint` for frontend verification (no test runner exists for these specific view files).

## Global Constraints

- Backend: PEP 8, type annotations on all function signatures (per `.claude/rules/coding-style.md`).
- Backend tests follow this repo's existing convention: pure-function `unittest.TestCase` tests (no DB) or `MagicMock`-based DB fakes (see `test_metering.py`) for logic worth testing; simple CRUD routes are not separately unit-tested (matches `update_status`/`wipe_leads`/`delete_client`, none of which have dedicated tests) — only static source-text checks where wiring must be proven (see `test_operator_impersonation.py`, `test_create_client_entitlements_static.py`).
- Frontend verification is `npm run typecheck` **and** `npm run lint` — typecheck alone passes code that still fails CI (unused imports, `any`).
- No comments unless the WHY is non-obvious. No unrelated refactors.
- **Do not run `git add` or `git commit` for this work.** The user is staging and committing manually. Every task below ends with a verification step, not a commit step — stop there and move to the next task.
- Confirmed against live Supabase (project `ayftynkgmfkaqmmnlmoc`) before this plan was written: `tenant_subscriptions` has zero rows. No tenant currently references any of the 6 seed `plans` rows. This is why Task 1 deletes them outright instead of backfilling.

---

## Task 1: Database migration — new `plans` shape, single `plan_id` on subscriptions

**Files:**
- Create: `backend/supabase/migrations/127_admin_subscription_plans.sql`

**Interfaces:**
- Produces: `plans(id, name, monthly_price, feature_keys jsonb, quotas jsonb, active, created_at)` — no more `pillar`/`tier`/`ai_tier`/`included`. `tenant_subscriptions.plan_id uuid references plans(id) on delete set null` — no more `messaging_plan_id`/`telecalling_plan_id`/`ai_tier`/`custom_overrides`.

- [ ] **Step 1: Write the migration file**

```sql
-- Migration 127: Admin-customizable subscription plans (single plan per tenant)
--
-- Replaces the 6 hardcoded messaging/telecalling/ai_tier plans with a single
-- admin-authored `plans` table (name, price, feature checklist, quotas).
-- Verified against live data before writing this: `tenant_subscriptions` has
-- zero rows, so no tenant currently references any plan -- safe to drop the
-- seed rows and old columns without a data backfill.

-- tenant_subscriptions: single plan_id replaces the three old plan/tier fields
alter table tenant_subscriptions add column if not exists plan_id uuid references plans(id) on delete set null;
alter table tenant_subscriptions drop column if exists messaging_plan_id;
alter table tenant_subscriptions drop column if exists telecalling_plan_id;
alter table tenant_subscriptions drop column if exists ai_tier;
alter table tenant_subscriptions drop column if exists custom_overrides;

-- plans: delete the 6 seed rows (confirmed nothing in tenant_subscriptions
-- references them) so the table starts genuinely empty for the admin.
delete from plans;

-- plans: new shape -- a flat feature checklist + canonical usage-metric quotas
alter table plans drop column if exists pillar;
alter table plans drop column if exists tier;
alter table plans drop column if exists ai_tier;
alter table plans drop column if exists included;
alter table plans add column if not exists feature_keys jsonb not null default '[]';
alter table plans add column if not exists quotas jsonb not null default '{}';
```

- [ ] **Step 2: Apply the migration to live Supabase**

Use the Supabase MCP `apply_migration` tool against project `ayftynkgmfkaqmmnlmoc` with the SQL above (name: `admin_subscription_plans`), or run it through whatever the project's normal migration-apply process is if working outside this session.

- [ ] **Step 3: Verify the schema change**

Run against the same project (via `execute_sql` or equivalent):

```sql
select column_name, data_type from information_schema.columns where table_name = 'plans' order by ordinal_position;
select column_name, data_type from information_schema.columns where table_name = 'tenant_subscriptions' order by ordinal_position;
select count(*) from plans;
```

Expected: `plans` columns are exactly `id, name, monthly_price, feature_keys, quotas, active, created_at` (no `pillar`/`tier`/`ai_tier`/`included`); `tenant_subscriptions` has `plan_id` and no `messaging_plan_id`/`telecalling_plan_id`/`ai_tier`/`custom_overrides`; `plans` row count is `0`.

---

## Task 2: `resolve_entitlements()` — single-plan lookup

**Files:**
- Modify: `backend/app/services/entitlements.py:8-52`
- Test: `backend/tests/test_resolve_entitlements.py` (new)

**Interfaces:**
- Consumes: Postgrest-style `db.table(name).select(...).eq(...).maybe_single().execute()` chain (same `Client` interface the rest of the file already uses).
- Produces: `resolve_entitlements(db, tenant_id: str) -> dict` returning `{"features": list[str], "quotas": dict[str, int]}`. The `ai_tier` key and the `period` parameter are removed — nothing in the codebase reads either after this task (verified: only `create_client` calls this function, with no `period` arg, and nothing reads `["ai_tier"]` off its return value outside this file).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_resolve_entitlements.py`:

```python
"""
Tests for `resolve_entitlements`, which looks up a tenant's single assigned
plan and returns its feature_keys/quotas. Replaces the old
messaging-plan + telecalling-plan + ai_tier merge logic (migration 127).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import resolve_entitlements


def _single(data):
    result = MagicMock()
    result.data = data
    return result


class ResolveEntitlementsTests(unittest.TestCase):
    def _make_db(self, tenant_data, subscription_data, plan_data):
        responses = {
            "tenants": tenant_data,
            "tenant_subscriptions": subscription_data,
            "plans": plan_data,
        }

        def table(name):
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                _single(responses[name])
            return tbl

        db = MagicMock()
        db.table.side_effect = table
        return db

    def test_no_tenant_returns_empty(self):
        db = self._make_db(None, None, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_tenant_with_no_subscription_row_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, None, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_subscription_with_no_plan_id_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, {"plan_id": None}, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_assigned_plan_returns_its_features_and_quotas(self):
        db = self._make_db(
            {"id": "tenant-1"},
            {"plan_id": "plan-1"},
            {"feature_keys": ["whatsapp", "broadcast"], "quotas": {"message_sent": 1000, "ai_reply": 500}},
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result["features"], ["whatsapp", "broadcast"])
        self.assertEqual(result["quotas"], {"message_sent": 1000, "ai_reply": 500})

    def test_plan_id_pointing_at_deleted_plan_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, {"plan_id": "plan-gone"}, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_resolve_entitlements.py -v`
Expected: FAIL — `resolve_entitlements` still reads `messaging_plan_id`/`telecalling_plan_id`/`custom_overrides`, so the mocked `"plans"` table call chain (`select().eq().maybe_single()`) won't match the old code's `select().eq().maybe_single()` calls made twice per plan slot, and the returned dict will still contain `"ai_tier"`, failing the equality assertions.

- [ ] **Step 3: Rewrite `resolve_entitlements`**

Replace `backend/app/services/entitlements.py:8-52` (the whole function body, keep the `def resolve_entitlements(...)` through the closing of that function only — `check_feature_enabled`, `check_quota`, `increment_usage`, `meter` below it are untouched):

```python
def resolve_entitlements(db: Client, tenant_id: str) -> dict:
    """
    Look up the tenant's single assigned plan and return its entitlements.
    Returns {'features': list, 'quotas': dict}
    """
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        return {"features": [], "quotas": {}}

    sub_res = db.table("tenant_subscriptions").select("plan_id").eq("tenant_id", tenant_id).maybe_single().execute()
    plan_id = (sub_res.data or {}).get("plan_id")
    if not plan_id:
        return {"features": [], "quotas": {}}

    plan_res = db.table("plans").select("feature_keys, quotas").eq("id", plan_id).maybe_single().execute()
    if not plan_res.data:
        return {"features": [], "quotas": {}}

    return {
        "features": list(plan_res.data.get("feature_keys") or []),
        "quotas": dict(plan_res.data.get("quotas") or {}),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_resolve_entitlements.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the existing metering tests to confirm no regression**

Run: `cd backend && python -m pytest tests/test_metering.py -v`
Expected: PASS (unchanged — `meter`/`increment_usage` don't call `resolve_entitlements`)

---

## Task 3: Plans CRUD routes

**Files:**
- Modify: `backend/app/routes/operator.py` (replace the existing `GET /plans` route at `operator.py:565-569`, add new routes immediately after it)

**Interfaces:**
- Consumes: `get_system_admin` dependency (`app/dependencies/system_admin.py`), `record_audit_event` (`app/services/audit_log.py`), `get_supabase` (`app/db/supabase.py`) — all already imported at the top of `operator.py`.
- Produces: `GET /operator/plans` → `{"data": [{id, name, monthly_price, feature_keys, quotas, active, created_at, tenant_count}]}`. `POST /operator/plans`, `PATCH /operator/plans/{plan_id}` → `{"data": {...plan row...}}`. `DELETE /operator/plans/{plan_id}` → `{"deleted": true, "plan_id": ...}` (soft-delete, sets `active=false`).

- [ ] **Step 1: Replace the `GET /plans` route and add CRUD routes**

In `backend/app/routes/operator.py`, replace:

```python
@router.get("/plans")
def list_plans(_admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    plans = db.table("plans").select("id, name, pillar, tier, monthly_price, ai_tier, included").eq("active", True).execute()
    return {"data": plans.data or []}
```

with:

```python
class PlanPayload(BaseModel):
    name: str
    monthly_price: float = 0
    feature_keys: list[str] = []
    quotas: dict[str, int] = {}


@router.get("/plans")
def list_plans(_admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    plans = db.table("plans").select(
        "id, name, monthly_price, feature_keys, quotas, active, created_at"
    ).eq("active", True).order("created_at").execute()
    plan_rows = plans.data or []

    plan_ids = [p["id"] for p in plan_rows]
    counts: dict[str, int] = {}
    if plan_ids:
        subs = db.table("tenant_subscriptions").select("plan_id").in_("plan_id", plan_ids).execute()
        for s in (subs.data or []):
            pid = s.get("plan_id")
            if pid:
                counts[pid] = counts.get(pid, 0) + 1

    for p in plan_rows:
        p["tenant_count"] = counts.get(p["id"], 0)

    return {"data": plan_rows}


@router.post("/plans")
def create_plan(payload: PlanPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    plan = db.table("plans").insert({
        "name": payload.name,
        "monthly_price": payload.monthly_price,
        "feature_keys": payload.feature_keys,
        "quotas": payload.quotas,
    }).execute()
    created = plan.data[0] if plan.data else None
    record_audit_event(
        db,
        tenant_id=None,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.plan_created",
        target_type="plan",
        target_id=created["id"] if created else None,
        metadata={"name": payload.name, "monthly_price": payload.monthly_price},
    )
    return {"data": created}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: str, payload: PlanPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    existing = db.table("plans").select("id").eq("id", plan_id).maybe_single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan = db.table("plans").update({
        "name": payload.name,
        "monthly_price": payload.monthly_price,
        "feature_keys": payload.feature_keys,
        "quotas": payload.quotas,
    }).eq("id", plan_id).execute()
    record_audit_event(
        db,
        tenant_id=None,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.plan_updated",
        target_type="plan",
        target_id=plan_id,
        metadata={"name": payload.name, "monthly_price": payload.monthly_price},
    )
    return {"data": plan.data[0] if plan.data else None}


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    existing = db.table("plans").select("id, name").eq("id", plan_id).maybe_single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Plan not found")

    db.table("plans").update({"active": False}).eq("id", plan_id).execute()
    record_audit_event(
        db,
        tenant_id=None,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.plan_deleted",
        target_type="plan",
        target_id=plan_id,
        metadata={"name": existing.data.get("name")},
    )
    return {"deleted": True, "plan_id": plan_id}
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `cd backend && python -c "import app.routes.operator"`
Expected: no output, exit code 0 (import succeeds — proves no syntax errors and all names, e.g. `BaseModel`, `HTTPException`, `record_audit_event`, resolve correctly; these are already imported at the top of the file).

No dedicated test file for this task — per the Global Constraints, simple CRUD routes without branching logic follow the codebase's existing convention (`update_status`, `wipe_leads`, `delete_client` are untested the same way). The one piece of logic worth a human sanity check is the `tenant_count` aggregation in `list_plans`, which Task 11's manual smoke test covers by creating a plan, assigning it to a tenant, and confirming the count updates.

---

## Task 4: Tenant creation + subscription routes on the new `plan_id` shape

**Files:**
- Modify: `backend/app/routes/operator.py:78-88` (`CreateClientPayload`)
- Modify: `backend/app/routes/operator.py:239-292` (inside `create_client`)
- Modify: `backend/app/routes/operator.py:715-724` (`get_subscription`)
- Add: new `PATCH /clients/{tenant_id}/subscription` route immediately after `get_subscription`
- Modify: `backend/tests/test_create_client_entitlements_static.py`

**Interfaces:**
- Consumes: `resolve_entitlements(db, tenant_id) -> {"features": [...], "quotas": {...}}` from Task 2.
- Produces: `POST /clients` now takes `plan_id: str | None` instead of `messaging_plan_id`/`telecalling_plan_id`/`ai_tier`. `GET /clients/{tenant_id}/subscription` returns `{"data": {"plan_id": ..., "mrr": ..., "plan": {id, name, monthly_price, feature_keys, quotas} | None}}`. New `PATCH /clients/{tenant_id}/subscription` accepts `{"plan_id": str | None}`, reassigns the tenant's plan, recomputes `mrr`/`enabled_features`/usage-counter quotas, and returns `{"tenant_id", "plan_id", "mrr"}`.

- [ ] **Step 1: Update `CreateClientPayload`**

Replace `backend/app/routes/operator.py:78-88`:

```python
class CreateClientPayload(BaseModel):
    company_name: str
    business_type: str
    contact_name: str
    contact_phone: str
    billing_region: str | None = None
    email: EmailStr
    password: str
    messaging_plan_id: str | None = None
    telecalling_plan_id: str | None = None
    ai_tier: Literal["off", "basic", "standard", "premium", "byo"] = "off"
```

with:

```python
class CreateClientPayload(BaseModel):
    company_name: str
    business_type: str
    contact_name: str
    contact_phone: str
    billing_region: str | None = None
    email: EmailStr
    password: str
    plan_id: str | None = None
```

- [ ] **Step 2: Update `create_client`'s subscription/entitlement seeding**

Replace `backend/app/routes/operator.py:239-292` (the block from `# Create subscription record` through the closing of the `tenant_usage_counters` insert call, still inside the same `try:`):

```python
        # Create subscription record
        mrr = 0
        if payload.plan_id:
            plan = db.table("plans").select("monthly_price").eq("id", payload.plan_id).maybe_single().execute()
            mrr = plan.data["monthly_price"] if plan.data else 0

        db.table("tenant_subscriptions").insert({
            "tenant_id": tenant_id,
            "status": "trial",
            "plan_id": payload.plan_id,
            "mrr": mrr,
            "trial_ends": None,
        }).execute()

        # Resolve entitlements now that the subscription exists, and seed
        # enabled_features + usage counters so the console is usable immediately.
        ent = resolve_entitlements(db, tenant_id)

        features = list(dict.fromkeys(ent["features"]))
        db.table("tenants").update({"enabled_features": features}).eq("id", tenant_id).execute()

        quotas = ent["quotas"]
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        usage_metrics = {
            "message_sent": quotas.get("message_sent", 0),
            "ai_reply": quotas.get("ai_reply", 0),
            "call_minute": quotas.get("call_minute", 0),
            "team_seat_active": quotas.get("team_seat_active", 0),
            "storage_gb": quotas.get("storage_gb", 0),
            "ai_call_summary": quotas.get("ai_call_summary", 0),
            "ai_call_scoring": quotas.get("ai_call_scoring", 0),
        }
        db.table("tenant_usage_counters").insert([
            {"tenant_id": tenant_id, "period": period, "metric": metric, "used": 0, "included": included}
            for metric, included in usage_metrics.items()
        ]).execute()
```

- [ ] **Step 3: Update `get_subscription` and add the `PATCH` route**

Replace `backend/app/routes/operator.py:715-724`:

```python
@router.get("/clients/{tenant_id}/subscription")
def get_subscription(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    
    sub = db.table("tenant_subscriptions").select(
        "messaging_plan_id, telecalling_plan_id, ai_tier, mrr, custom_overrides"
    ).eq("tenant_id", tenant_id).maybe_single().execute()

    # maybe_single() returns None (not a response with .data = None) when zero rows match.
    return {"data": sub.data if sub else {}}
```

with:

```python
@router.get("/clients/{tenant_id}/subscription")
def get_subscription(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()

    sub = db.table("tenant_subscriptions").select("plan_id, mrr").eq("tenant_id", tenant_id).maybe_single().execute()
    data = dict(sub.data) if sub and sub.data else {}

    plan_id = data.get("plan_id")
    data["plan"] = None
    if plan_id:
        plan = db.table("plans").select(
            "id, name, monthly_price, feature_keys, quotas"
        ).eq("id", plan_id).maybe_single().execute()
        data["plan"] = plan.data if plan.data else None

    return {"data": data}


class UpdateSubscriptionPayload(BaseModel):
    plan_id: str | None = None


@router.patch("/clients/{tenant_id}/subscription")
def update_subscription(tenant_id: str, payload: UpdateSubscriptionPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()

    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    mrr = 0
    if payload.plan_id:
        plan = db.table("plans").select("monthly_price").eq("id", payload.plan_id).maybe_single().execute()
        if not plan.data:
            raise HTTPException(status_code=404, detail="Plan not found")
        mrr = plan.data["monthly_price"]

    db.table("tenant_subscriptions").upsert({
        "tenant_id": tenant_id,
        "plan_id": payload.plan_id,
        "mrr": mrr,
    }, on_conflict="tenant_id").execute()

    ent = resolve_entitlements(db, tenant_id)
    features = list(dict.fromkeys(ent["features"]))
    db.table("tenants").update({"enabled_features": features}).eq("id", tenant_id).execute()

    quotas = ent["quotas"]
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    usage_metrics = {
        "message_sent": quotas.get("message_sent", 0),
        "ai_reply": quotas.get("ai_reply", 0),
        "call_minute": quotas.get("call_minute", 0),
        "team_seat_active": quotas.get("team_seat_active", 0),
        "storage_gb": quotas.get("storage_gb", 0),
        "ai_call_summary": quotas.get("ai_call_summary", 0),
        "ai_call_scoring": quotas.get("ai_call_scoring", 0),
    }
    for metric, included in usage_metrics.items():
        db.table("tenant_usage_counters").upsert({
            "tenant_id": tenant_id,
            "period": period,
            "metric": metric,
            "included": included,
        }, on_conflict="tenant_id,period,metric").execute()

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.subscription_plan_changed",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"plan_id": payload.plan_id, "mrr": mrr},
    )

    return {"tenant_id": tenant_id, "plan_id": payload.plan_id, "mrr": mrr}
```

- [ ] **Step 4: Update the static test file**

In `backend/tests/test_create_client_entitlements_static.py`, replace `test_pillar_defaults_added_when_plans_present` (the pillar-injection logic it checks no longer exists — the plan's own `feature_keys` now carries everything) and `test_usage_counter_metric_mapping` (the quota keys are now the canonical metric names directly, no translation):

```python
    def test_usage_counter_metric_mapping(self):
        expected_mapping = {
            "message_sent": 'quotas.get("message_sent", 0)',
            "ai_reply": 'quotas.get("ai_reply", 0)',
            "call_minute": 'quotas.get("call_minute", 0)',
            "team_seat_active": 'quotas.get("team_seat_active", 0)',
            "storage_gb": 'quotas.get("storage_gb", 0)',
            "ai_call_summary": 'quotas.get("ai_call_summary", 0)',
            "ai_call_scoring": 'quotas.get("ai_call_scoring", 0)',
        }
        for metric, quota_expr in expected_mapping.items():
            self.assertRegex(self.source, rf'"{metric}":\s*{re.escape(quota_expr)}')
```

Remove the entire `test_pillar_defaults_added_when_plans_present` method (the string patterns it asserts — `features.extend(["whatsapp", ...])` and the telecalling equivalent — are deleted from `create_client` in Step 2 above, since the plan's `feature_keys` already carries those).

- [ ] **Step 5: Run the updated test file**

Run: `cd backend && python -m pytest tests/test_create_client_entitlements_static.py -v`
Expected: PASS (7 tests — 8 minus the removed pillar-defaults test)

- [ ] **Step 6: Verify the module still imports cleanly**

Run: `cd backend && python -c "import app.routes.operator"`
Expected: no output, exit code 0

---

## Task 5: Remove Fleet route, impersonation routes, and the a-la-carte feature-toggle route

**Files:**
- Modify: `backend/app/routes/operator.py` (delete `fleet_cockpit` route at `operator.py:559-562`, delete `toggle_feature` route at `operator.py:694-712`, delete the impersonation section at `operator.py:1947-2081`)
- Delete: `backend/tests/test_operator_impersonation.py`
- Rename: `backend/tests/test_fleet_health.py` → `backend/tests/test_tenant_health.py` (update its docstring only — the functions it tests, `compute_fleet_health`/`has_required_tokens`, are staying, still used internally by `GET /operator/alerts` via `_build_fleet_rows`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /operator/fleet`, `POST /operator/clients/{tenant_id}/features/toggle`, `POST /operator/impersonation/start`, `POST /operator/impersonation/end` no longer exist. `_build_fleet_rows`, `compute_fleet_health`, `has_required_tokens` remain as private helpers for `GET /operator/alerts` — do not touch them.

- [ ] **Step 1: Delete the Fleet route**

Remove `backend/app/routes/operator.py:559-562`:

```python
@router.get("/fleet")
def fleet_cockpit(_admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    return {"data": _build_fleet_rows(db)}
```

(Leave `_build_fleet_rows`, `compute_fleet_health`, `has_required_tokens`, and `_build_tenant_health_rows`-equivalent code untouched — `GET /operator/alerts` still calls `_build_fleet_rows` directly.)

- [ ] **Step 2: Delete the a-la-carte feature-toggle route**

Remove `backend/app/routes/operator.py:694-712` (the `FeatureTogglePayload`-consuming route — note `FeatureTogglePayload` itself, declared earlier alongside `UpdateStatusPayload`/`CallingProviderPayload` at `operator.py:572-574`, becomes unused and must be deleted too):

```python
@router.post("/clients/{tenant_id}/features/toggle")
def toggle_feature(tenant_id: str, payload: FeatureTogglePayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    
    tenant = db.table("tenants").select("enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    features = tenant.data.get("enabled_features", []) or []
    
    if payload.enabled:
        if payload.feature_key not in features:
            features.append(payload.feature_key)
    else:
        features = [f for f in features if f != payload.feature_key]
    
    db.table("tenants").update({"enabled_features": features}).eq("id", tenant_id).execute()
    
    return {"tenant_id": tenant_id, "enabled_features": features}
```

Also remove the now-unused `class FeatureTogglePayload(BaseModel): ...` declaration (do NOT remove `UpdateStatusPayload` or `CallingProviderPayload` — those are still used by other routes).

(`PATCH /clients/{tenant_id}/features` / `update_features` / `UpdateFeaturesPayload` is a **different**, unrelated route — the client-detail sidebar's channel on/off toggles (whatsapp/telecalling/etc.) go through it, not through billing. Leave it untouched.)

- [ ] **Step 3: Delete the impersonation section**

Remove `backend/app/routes/operator.py:1947-2081` in full — the `# --- Tenant impersonation ("View as tenant") ---` comment block, `IMPERSONATION_SESSION_TTL_SECONDS`, `StartImpersonationPayload`, `_resolve_impersonation_start`, `start_impersonation`, `EndImpersonationPayload`, `end_impersonation` — everything from the section header comment to the end of the file (this section is the last thing in the file).

- [ ] **Step 4: Delete the impersonation test file**

Delete `backend/tests/test_operator_impersonation.py` in full (tests `_resolve_impersonation_start` and the impersonation route wiring, both gone).

- [ ] **Step 5: Rename and re-scope the fleet-health test file**

Rename `backend/tests/test_fleet_health.py` to `backend/tests/test_tenant_health.py`, updating only the module docstring at the top (the test bodies are unchanged — they test `compute_fleet_health`/`has_required_tokens` directly, which still exist):

```python
"""
Tests for `compute_fleet_health` and `has_required_tokens`, the pure scoring
functions behind `_build_fleet_rows` — the shared per-tenant health signal
builder used by `GET /api/v1/operator/alerts` (the Fleet page that used to
also consume this was removed; the scoring logic it shared with Alerts stays).

Contract under test: health is derived purely from the signals passed in --
no DB access -- so every tier/branch can be exercised directly.
"""
```

The `from app.routes.operator import compute_fleet_health, has_required_tokens` import line and every test method body stay exactly as they are.

- [ ] **Step 6: Run the backend test suite**

Run: `cd backend && python -m pytest tests/test_tenant_health.py tests/test_operator_alerts.py -v`
Expected: PASS — `test_tenant_health.py` (renamed, same assertions) and `test_operator_alerts.py` (untouched, `compute_alerts` still calls into the same fleet-row builder) both green.

Run: `cd backend && python -c "import app.routes.operator"`
Expected: no output, exit code 0 (proves no dangling references to deleted names like `FeatureTogglePayload` or `_resolve_impersonation_start` remain anywhere in the file)

---

## Task 6: Sidebar, command palette, and layout — Fleet → Subscription, drop the impersonation banner

**Files:**
- Modify: `frontend/app/operator/(console)/components/operator-sidebar.tsx`
- Modify: `frontend/app/operator/(console)/components/command-palette.tsx`
- Modify: `frontend/app/operator/(console)/layout.tsx`

**Interfaces:**
- Produces: sidebar nav item `/operator/fleet` "Fleet" → `/operator/subscription` "Subscription". Command palette nav entry same swap. No more `ImpersonationBanner` in the console layout, so the sidebar header no longer needs to offset for it.

- [ ] **Step 1: Update the sidebar**

In `frontend/app/operator/(console)/components/operator-sidebar.tsx`, remove the impersonation import and wiring, and swap the Fleet nav item:

Replace the imports and `NAV_ITEMS` (lines 1-16):

```tsx
"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Clock, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { AiraLogo } from "@/components/logo";
import { AlertBell } from "./alert-bell";

const NAV_ITEMS = [
  { href: "/operator", label: "Clients" },
  { href: "/operator/subscription", label: "Subscription" },
  { href: "/operator/scheduler", label: "Schedulers" },
  { href: "/operator/audit-log", label: "Audit Log" },
];
```

Remove the `impersonating` state and its effect (originally lines 23, 25-32):

```tsx
  const [impersonating, setImpersonating] = useState(false);

  const refreshImpersonation = useCallback(() => {
    setImpersonating(getImpersonationSession() !== null);
  }, []);

  useEffect(() => {
    refreshImpersonation();
    return subscribeImpersonation(refreshImpersonation);
  }, [refreshImpersonation]);
```

Also remove `useCallback` from the `useState, useEffect, useCallback` import (already dropped in the replaced import block above — `useCallback` is no longer used anywhere in this file once the impersonation effect is gone).

Replace the header's inline `style` (originally):

```tsx
      <header
        className="sticky z-40 h-16 flex items-center justify-between gap-4 px-7 bg-white border-b border-border"
        style={{ top: impersonating ? "44px" : "0px" }}
      >
```

with:

```tsx
      <header className="sticky top-0 z-40 h-16 flex items-center justify-between gap-4 px-7 bg-white border-b border-border">
```

- [ ] **Step 2: Update the command palette**

In `frontend/app/operator/(console)/components/command-palette.tsx`, swap the `Server` icon import for `CreditCard` (line 4) and update the Fleet nav entry (line 22):

```tsx
import { Search, CornerDownLeft, Users, CreditCard, CalendarClock, ScrollText, Plus, Building2 } from "lucide-react";
```

```tsx
  { id: "nav-subscription", label: "Subscription", hint: "Go to Subscription", icon: CreditCard, href: "/operator/subscription" },
```

(This replaces `{ id: "nav-fleet", label: "Fleet", hint: "Go to Fleet", icon: Server, href: "/operator/fleet" }` in place, same position in the `NAV_ITEMS` array.)

- [ ] **Step 3: Remove the impersonation banner from the layout**

In `frontend/app/operator/(console)/layout.tsx`, remove the import and usage:

```tsx
import { ImpersonationBanner } from "./components/impersonation-banner";
```

```tsx
      <ImpersonationBanner />
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run typecheck`
Expected: no errors (this will fail until Task 7 also deletes `view-as-tenant-button.tsx`'s usage in `client/[id]/page.tsx` and the `subscription/page.tsx` route exists from Task 8 — if running this task in isolation before Tasks 7/8 land, typecheck errors referencing those are expected and will clear once this task's sibling tasks complete; don't treat those specific errors as a regression from this task's own edits).

---

## Task 7: Delete Fleet page + impersonation frontend code; clean up the client detail page

**Files:**
- Delete: `frontend/app/operator/(console)/fleet/page.tsx` (and the now-empty `fleet/` directory)
- Delete: `frontend/lib/impersonation.ts`
- Delete: `frontend/app/operator/(console)/components/impersonation-banner.tsx`
- Delete: `frontend/app/operator/(console)/client/[id]/components/view-as-tenant-button.tsx`
- Modify: `frontend/app/operator/(console)/client/[id]/page.tsx`

**Interfaces:**
- Produces: no more `/operator/fleet` route, no more impersonation session storage/banner/button anywhere in the frontend.

- [ ] **Step 1: Delete the standalone files**

Delete these four files:
- `frontend/app/operator/(console)/fleet/page.tsx`
- `frontend/lib/impersonation.ts`
- `frontend/app/operator/(console)/components/impersonation-banner.tsx`
- `frontend/app/operator/(console)/client/[id]/components/view-as-tenant-button.tsx`

Remove the `fleet/` directory itself once its only file is gone.

- [ ] **Step 2: Clean up `client/[id]/page.tsx`**

Remove the impersonation import (line 5) and the `ViewAsTenantButton` import (line 7):

```tsx
import { getImpersonationSession, subscribeImpersonation } from "@/lib/impersonation";
```

```tsx
import { ViewAsTenantButton } from "./components/view-as-tenant-button";
```

Remove the `impersonating` state and its effect (originally lines 33, 35-42):

```tsx
  const [impersonating, setImpersonating] = useState(false);

  const refreshImpersonation = useCallback(() => {
    setImpersonating(getImpersonationSession() !== null);
  }, []);

  useEffect(() => {
    refreshImpersonation();
    return subscribeImpersonation(refreshImpersonation);
  }, [refreshImpersonation]);
```

`useCallback` stays imported — `loadOverview` still uses it. Update the sticky header's `top` from the ternary to a fixed value (originally):

```tsx
          style={{ top: impersonating ? "108px" : "64px" }}
```

to:

```tsx
          style={{ top: "64px" }}
```

Remove the `<ViewAsTenantButton tenantId={tenantId} tenantName={tenant.name} />` line from inside the `{tenant && (...)}` block.

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors (this task alone will still show a typecheck error for the sidebar's `/operator/subscription` link having no matching route yet, if Task 8 hasn't run — that's expected until Task 8 lands; everything else must be clean)

---

## Task 8: New Subscription page — plan list + create/edit/delete builder

**Files:**
- Create: `frontend/app/operator/(console)/subscription/page.tsx`

**Interfaces:**
- Consumes: `operatorFetch<T>(path, init?)` from `frontend/lib/operator.ts`. `GET /operator/plans` → `{data: Plan[]}` where `Plan = {id, name, monthly_price, feature_keys, quotas, active, created_at, tenant_count}` (Task 3). `GET /operator/features/catalog` → `FeatureCatalogItem[]` (existing route, untouched). `POST /operator/plans`, `PATCH /operator/plans/{id}`, `DELETE /operator/plans/{id}` (Task 3).
- Produces: the page rendered at `/operator/subscription`, linked from the sidebar (Task 6).

- [ ] **Step 1: Create the page**

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { CreditCard, Plus, Pencil, Trash2, Users, MessageSquare, Zap, Brain, Phone, Cog, Settings2 } from "lucide-react";
import { operatorFetch } from "@/lib/operator";

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
}

interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
  active: boolean;
  created_at: string;
  tenant_count: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  channels: "Channels",
  messaging: "Messaging",
  ai: "AI",
  telecalling: "Telecalling",
  automation: "Automation",
  ops: "Ops",
};

const CATEGORY_ICONS: Record<string, typeof MessageSquare> = {
  channels: MessageSquare,
  messaging: Zap,
  ai: Brain,
  telecalling: Phone,
  automation: Cog,
  ops: Settings2,
};

const QUOTA_METRICS: { key: string; label: string }[] = [
  { key: "message_sent", label: "Messages / mo" },
  { key: "ai_reply", label: "AI Replies / mo" },
  { key: "call_minute", label: "Call Minutes / mo" },
  { key: "team_seat_active", label: "Team Seats" },
  { key: "storage_gb", label: "Storage (GB)" },
  { key: "ai_call_summary", label: "AI Call Summaries / mo" },
  { key: "ai_call_scoring", label: "AI Call Scoring / mo" },
];

interface PlanFormState {
  id: string | null;
  name: string;
  monthly_price: string;
  feature_keys: Set<string>;
  quotas: Record<string, string>;
}

function emptyForm(): PlanFormState {
  return { id: null, name: "", monthly_price: "", feature_keys: new Set(), quotas: {} };
}

export default function SubscriptionPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<PlanFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Plan | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    return Promise.all([
      operatorFetch<{ data: Plan[] }>("/api/v1/operator/plans"),
      operatorFetch<{ data: FeatureCatalogItem[] } | FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
    ])
      .then(([plansRes, catalogRes]) => {
        setPlans(plansRes.data ?? []);
        setCatalog(Array.isArray(catalogRes) ? catalogRes : catalogRes.data ?? []);
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const catalogByCategory = catalog.reduce<Record<string, FeatureCatalogItem[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  function openCreate() {
    setForm(emptyForm());
  }

  function openEdit(plan: Plan) {
    const quotas: Record<string, string> = {};
    for (const metric of QUOTA_METRICS) {
      const value = plan.quotas[metric.key];
      quotas[metric.key] = value ? String(value) : "";
    }
    setForm({
      id: plan.id,
      name: plan.name,
      monthly_price: String(plan.monthly_price),
      feature_keys: new Set(plan.feature_keys),
      quotas,
    });
  }

  function toggleFeature(key: string) {
    setForm(prev => {
      if (!prev) return prev;
      const next = new Set(prev.feature_keys);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { ...prev, feature_keys: next };
    });
  }

  function setQuota(key: string, value: string) {
    setForm(prev => (prev ? { ...prev, quotas: { ...prev.quotas, [key]: value } } : prev));
  }

  async function handleSave() {
    if (!form || !form.name.trim()) return;
    setSaving(true);
    setError(null);
    const quotas: Record<string, number> = {};
    for (const metric of QUOTA_METRICS) {
      const raw = form.quotas[metric.key];
      const parsed = raw ? parseInt(raw, 10) : 0;
      if (parsed > 0) quotas[metric.key] = parsed;
    }
    const payload = {
      name: form.name.trim(),
      monthly_price: parseFloat(form.monthly_price) || 0,
      feature_keys: Array.from(form.feature_keys),
      quotas,
    };
    try {
      if (form.id) {
        await operatorFetch(`/api/v1/operator/plans/${form.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await operatorFetch("/api/v1/operator/plans", { method: "POST", body: JSON.stringify(payload) });
      }
      setForm(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save plan");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await operatorFetch(`/api/v1/operator/plans/${deleteTarget.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete plan");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <div className="p-7 text-sm text-ink-muted">Loading plans…</div>;
  }

  return (
    <div className="p-7 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-lg font-bold text-ink">Subscription Plans</h1>
          <p className="text-xs text-ink-muted mt-0.5">Create and edit the plans tenants can be assigned to.</p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark transition-colors"
        >
          <Plus size={15} /> New Plan
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>
      )}

      {plans.length === 0 ? (
        <div className="rounded-card border border-dashed border-border p-10 text-center">
          <CreditCard size={28} className="mx-auto text-ink-muted mb-3" />
          <p className="text-sm font-medium text-ink">No plans yet</p>
          <p className="text-xs text-ink-muted mt-1">Create the first plan to start assigning it to tenants.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {plans.map(plan => (
            <div key={plan.id} className="bg-white rounded-card border border-border p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-ink">{plan.name}</h3>
                  <p className="text-lg font-bold text-primary mt-1">
                    ₹{plan.monthly_price.toLocaleString("en-IN")}
                    <span className="text-xs font-medium text-ink-muted">/mo</span>
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => openEdit(plan)} className="p-1.5 rounded-lg text-ink-muted hover:bg-surface-mid hover:text-ink" title="Edit plan">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => setDeleteTarget(plan)} className="p-1.5 rounded-lg text-ink-muted hover:bg-red-50 hover:text-danger" title="Delete plan">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-ink-muted mt-3">{plan.feature_keys.length} features included</p>
              <p className="text-xs text-ink-muted mt-1 flex items-center gap-1">
                <Users size={12} /> {plan.tenant_count} tenant{plan.tenant_count === 1 ? "" : "s"} assigned
              </p>
            </div>
          ))}
        </div>
      )}

      {form && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6">
            <h2 className="text-lg font-bold text-ink mb-4">{form.id ? "Edit Plan" : "New Plan"}</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Plan Name *</label>
                  <input
                    value={form.name}
                    onChange={e => setForm(prev => (prev ? { ...prev, name: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="Growth"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Monthly Price (₹) *</label>
                  <input
                    type="number"
                    min="0"
                    value={form.monthly_price}
                    onChange={e => setForm(prev => (prev ? { ...prev, monthly_price: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="9999"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Usage Quotas</label>
                <div className="grid grid-cols-2 gap-3">
                  {QUOTA_METRICS.map(metric => (
                    <div key={metric.key}>
                      <label className="text-xs text-ink-muted block mb-1">{metric.label}</label>
                      <input
                        type="number"
                        min="0"
                        value={form.quotas[metric.key] ?? ""}
                        onChange={e => setQuota(metric.key, e.target.value)}
                        className="w-full border border-border rounded-xl px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                        placeholder="0"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Features Included</label>
                <div className="space-y-4 max-h-64 overflow-y-auto border border-border rounded-xl p-3">
                  {Object.entries(catalogByCategory).map(([category, features]) => {
                    const Icon = CATEGORY_ICONS[category] || Zap;
                    return (
                      <div key={category}>
                        <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5">
                          <Icon size={12} /> {CATEGORY_LABELS[category] || category}
                        </p>
                        <div className="grid grid-cols-2 gap-1.5">
                          {features.map(f => (
                            <label key={f.feature_key} className="flex items-center gap-2 text-sm text-ink-secondary cursor-pointer">
                              <input
                                type="checkbox"
                                checked={form.feature_keys.has(f.feature_key)}
                                onChange={() => toggleFeature(f.feature_key)}
                                className="rounded border-border"
                              />
                              {f.display_name}
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="flex gap-3 pt-6 mt-4 border-t border-border">
              <button
                onClick={() => setForm(null)}
                className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim()}
                className="flex-1 px-4 py-2.5 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark disabled:opacity-50"
              >
                {saving ? "Saving…" : form.id ? "Save Changes" : "Create Plan"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-sm p-6">
            <h3 className="text-lg font-bold text-ink mb-2">Delete {deleteTarget.name}?</h3>
            <p className="text-sm text-ink-secondary mb-6">
              {deleteTarget.tenant_count > 0
                ? `${deleteTarget.tenant_count} tenant${deleteTarget.tenant_count === 1 ? "" : "s"} currently on this plan will keep their entitlements, but this plan will no longer be assignable to new tenants.`
                : "This plan is not assigned to any tenant."}
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)} className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting} className="flex-1 px-4 py-2.5 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 disabled:opacity-50">
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors from this file (`/operator/subscription` route now exists, clearing the sidebar-link typecheck gap noted in Task 6's verification step).

---

## Task 9: Rewrite Feature Store (plan picker) and Billing view (plan card)

**Files:**
- Modify: `frontend/app/operator/(console)/client/[id]/views/feature-store.tsx` (full rewrite)
- Modify: `frontend/app/operator/(console)/client/[id]/views/billing.tsx` (interfaces + Plans/AI-tier cards section)

**Interfaces:**
- Consumes: `GET /clients/{tenant_id}/subscription` → `{plan_id, mrr, plan: {id, name, monthly_price, feature_keys, quotas} | null}` (Task 4). `GET /operator/plans` → `{data: Plan[]}` (Task 3). `PATCH /clients/{tenant_id}/subscription` → `{tenant_id, plan_id, mrr}` (Task 4).

- [ ] **Step 1: Rewrite `feature-store.tsx`**

Replace the entire file:

```tsx
"use client";
import { useEffect, useState } from "react";
import { CreditCard, Check, MessageSquare, Zap, Brain, Phone, Cog, Settings2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  const json = await res.json();
  return ((json as { data?: T }).data ?? json) as T;
}

interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
}

interface Subscription {
  plan_id: string | null;
  mrr: number;
  plan: Plan | null;
}

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
}

export function FeatureStoreView({ tenantId }: { tenantId: string }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<Plan[]>("/api/v1/operator/plans"),
      apiFetch<FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
    ])
      .then(([sub, plansData, catalogData]) => {
        setSubscription(sub);
        setPlans(plansData || []);
        setCatalog(catalogData || []);
        setSelectedPlanId(sub?.plan_id || "");
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  async function handleChangePlan() {
    setChanging(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({ plan_id: selectedPlanId || null }),
      });
      const sub = await apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`);
      setSubscription(sub);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to change plan");
    } finally {
      setChanging(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  }

  const catalogByKey = new Map(catalog.map(f => [f.feature_key, f]));
  const currentPlan = subscription?.plan || null;
  const isDirty = selectedPlanId !== (subscription?.plan_id || "");

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <CreditCard size={16} className="text-ink-muted" /> Assigned Plan
        </h3>
        {currentPlan ? (
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-ink">{currentPlan.name}</span>
              <span className="text-primary font-bold">₹{currentPlan.monthly_price.toLocaleString("en-IN")}/mo</span>
            </div>
            <div className="mt-3 grid gap-1.5 md:grid-cols-2">
              {currentPlan.feature_keys.map(key => (
                <div key={key} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                  <Check size={13} className="text-success shrink-0" />
                  {catalogByKey.get(key)?.display_name || key}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No plan assigned.</p>
        )}
      </div>

      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Change Plan</h3>
        {plans.length === 0 ? (
          <p className="text-sm text-ink-muted">No plans exist yet — create one from the Subscription page.</p>
        ) : (
          <div className="flex items-center gap-3">
            <select
              value={selectedPlanId}
              onChange={e => setSelectedPlanId(e.target.value)}
              className="flex-1 border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">No plan</option>
              {plans.map(p => (
                <option key={p.id} value={p.id}>{p.name} — ₹{p.monthly_price.toLocaleString("en-IN")}/mo</option>
              ))}
            </select>
            <button
              onClick={handleChangePlan}
              disabled={!isDirty || changing}
              className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark disabled:opacity-50"
            >
              {changing ? "Applying…" : "Apply"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

Note the icon imports `MessageSquare, Zap, Brain, Phone, Cog, Settings2` from the old file are gone since the category-grouped grid is no longer needed here (the Subscription page owns that UI now) — this file only needs `CreditCard` and `Check`.

- [ ] **Step 2: Update `billing.tsx`'s interfaces and Plans/AI-tier cards**

Replace the `Subscription`/`Plan` interfaces (originally lines 20-41):

```tsx
interface PlanSummary {
  id: string;
  name: string;
  monthly_price: number;
}

interface Subscription {
  plan_id: string | null;
  mrr: number;
  plan: PlanSummary | null;
}

interface UsageMetric {
  metric: string;
  used: number;
  included: number;
  hard_cap: number | null;
}
```

(The `Plan` interface with `pillar`/`tier`/`monthly_price` and the `capitalize` helper — used only for `ai_tier` display, which no longer exists — are removed.)

Update the component body: replace the `useState` for `plans` and the fetch (originally lines 108-128) since the plan name now comes embedded in the subscription response, no separate `/plans` fetch needed:

```tsx
export function BillingView({ tenantId }: { tenantId: string }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<UsageMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<UsageMetric[]>(`/api/v1/operator/clients/${tenantId}/usage`),
    ])
      .then(([sub, use]) => {
        setSubscription(sub);
        setUsage(Array.isArray(use) ? use : []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load billing"))
      .finally(() => setLoading(false));
  }, [tenantId]);
```

Remove the `planName`/`messagingPlan`/`telecallingPlan`/`aiTier`/`planRows` derivations (originally lines 151-161, between the `if (!subscription) return null;` guard and the `return (` JSX).

Replace the summary grid (originally the `<div className="grid grid-cols-1 gap-4 lg:grid-cols-3">...</div>` containing the MRR card, Plans card, and AI Tier card) with a two-column version — MRR card stays as-is (with the `(subscription.mrr || 0)` guard already in place), the Plans and AI Tier cards collapse into one Plan card:

```tsx
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* MRR — prominent */}
          <div className="rounded-card border border-border bg-gradient-to-br from-primary-light to-white p-5 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-primary">
              <IndianRupee size={16} />
              <span className="font-label text-xs font-medium uppercase tracking-wider">Monthly Recurring</span>
            </div>
            <p className="text-3xl font-bold text-ink">
              ₹{(subscription.mrr || 0).toLocaleString("en-IN")}
              <span className="ml-1 text-sm font-medium text-ink-muted">/mo</span>
            </p>
          </div>

          {/* Plan */}
          <div className="rounded-card border border-border bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-ink-muted">
              <CreditCard size={16} />
              <span className="font-label text-xs font-medium uppercase tracking-wider">Plan</span>
            </div>
            {subscription.plan ? (
              <p className="text-sm font-semibold text-ink">{subscription.plan.name}</p>
            ) : (
              <p className="text-sm text-ink-muted">No plan assigned.</p>
            )}
          </div>
        </div>
```

The `Sparkles`/`MessageSquare`/`Phone` icon imports at the top of the file become unused once the Plans/AI-tier cards are gone — remove them from the `lucide-react` import line, keeping `CreditCard, AlertTriangle, IndianRupee, Activity`.

The Usage meters section below (driven by `/usage`, `UsageMeterRow`) is untouched.

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

---

## Task 10: Rewrite the onboarding wizard's plan step

**Files:**
- Modify: `frontend/app/operator/(console)/components/onboarding-wizard.tsx`

**Interfaces:**
- Consumes: `GET /operator/plans` → `{data: Plan[]}` where `Plan = {id, name, monthly_price, feature_keys, quotas}` (Task 3).
- Produces: `POST /clients` payload now sends `plan_id` instead of `messaging_plan_id`/`telecalling_plan_id`/`ai_tier` (matches Task 4's `CreateClientPayload`).

- [ ] **Step 1: Replace the `Plan` interface and remove the AI-tier constant**

Replace (originally lines 7-36):

```tsx
interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
}

interface OnboardingWizardProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

const BUSINESS_TYPES = [
  "Coaching", "Real Estate", "Healthcare", "Agency", "E-commerce", "Other",
];
```

(`AI_TIERS` is deleted entirely — no longer a separate concept.)

- [ ] **Step 2: Replace the pillar/tier/ai-tier state with a single `planId`**

Replace (originally lines 63-66):

```tsx
  const [selectedPillar, setSelectedPillar] = useState<"messaging" | "telecalling" | "both">("messaging");
  const [messagingTier, setMessagingTier] = useState<"basic" | "standard" | "pro">("standard");
  const [telecallingTier, setTelecallingTier] = useState<"basic" | "standard" | "pro">("standard");
  const [aiTier, setAiTier] = useState<string>("off");
```

with:

```tsx
  const [planId, setPlanId] = useState<string>("");
```

- [ ] **Step 3: Replace the price/MRR derivations**

Replace (originally lines 84-94, the `getPrice` function through `telecallingPlan`):

```tsx
  const mrr = plans.find(p => p.id === planId)?.monthly_price || 0;
```

- [ ] **Step 4: Update `handleCreate`'s payload**

Replace the `body: JSON.stringify({...})` inside `handleCreate` (originally lines 102-113):

```tsx
        body: JSON.stringify({
          company_name: companyName,
          business_type: businessType,
          contact_name: contactName,
          contact_phone: contactPhone,
          billing_region: billingRegion || null,
          email,
          password,
          plan_id: planId || null,
        }),
```

- [ ] **Step 5: Replace step 2's JSX**

Replace the entire `{step === 2 && (...)}` block (originally lines 197-277):

```tsx
          {step === 2 && (
            <div className="space-y-4">
              {plans.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border p-6 text-center">
                  <p className="text-sm text-ink-secondary">No subscription plans exist yet.</p>
                  <p className="text-xs text-ink-muted mt-1">
                    You can create one from the Subscription page and assign it to this client later.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-2">Subscription Plan (optional)</label>
                  <select
                    value={planId}
                    onChange={e => setPlanId(e.target.value)}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  >
                    <option value="">No plan (assign later)</option>
                    {plans.map(p => (
                      <option key={p.id} value={p.id}>{p.name} — ₹{p.monthly_price.toLocaleString("en-IN")}/mo</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          )}
```

- [ ] **Step 6: Update step 4's summary JSX**

Replace the Pillar/Messaging Tier/Telecalling Tier/AI Tier rows inside the `{step === 4 && (...)}` summary block (originally lines 323-338, between the "Business Type" row and the MRR total) with a single Plan row:

```tsx
                <div className="flex justify-between">
                  <span className="text-ink-muted">Subscription Plan:</span>
                  <span className="text-ink font-medium">{plans.find(p => p.id === planId)?.name || "None"}</span>
                </div>
```

- [ ] **Step 7: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

---

## Task 11: Full verification pass

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all tests pass, including the new `test_resolve_entitlements.py`, the updated `test_create_client_entitlements_static.py`, the renamed `test_tenant_health.py`, and confirming `test_operator_impersonation.py` no longer exists (no collection errors).

- [ ] **Step 2: Frontend typecheck and lint**

Run: `cd frontend && npm run typecheck`
Run: `cd frontend && npm run lint`
Expected: both clean, zero errors.

- [ ] **Step 3: Manual smoke test**

With the backend running (`cd backend && uvicorn app.main:app --reload`) and frontend running (`cd frontend && npm run dev`), log into the operator console and confirm:
1. Sidebar shows "Subscription" where "Fleet" used to be; no impersonation banner appears anywhere; no "View as tenant" button on any client detail page.
2. `/operator/subscription` loads, shows an empty state, and a new plan can be created with a couple of features checked and a couple of quotas set.
3. Opening a tenant's Feature Store tab shows "No plan assigned" (or the empty-plans message if none were created), and selecting the newly created plan + clicking Apply updates the assigned-plan card and the tenant's Billing tab MRR.
4. The "New Client" wizard's step 2 shows the plan dropdown (or the "no plans yet" message if run before step 2 above) and creating a tenant with a plan selected succeeds; creating one with no plan selected also succeeds (matching the pre-monetization case that was crashing before Task 4's `billing.tsx` guard).

This closes the loop the original bug report opened: the `toLocaleString` crash is fixed at its root (Task 4's `get_subscription` reshaping plus the already-applied `billing.tsx` guard), and the whole plan/billing model it was crashing inside of has been replaced end to end.
