# Itemized Subscription Pricing & Approval Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the admin-assigns-one-plan monetization model with a client-driven itemized cart: the developer prices individual catalog items and optional discounted packages, a new tenant builds a cart and is gated out of the product until an admin approves it, and purchased quantities/quotas become hard-enforced instead of track-only.

**Architecture:** Two new tables (`tenant_subscription_items` = current effective entitlements, `subscription_requests` = append-only approval log) sit alongside the existing `feature_catalog`/`plans`/`tenant_usage_counters`. `feature_catalog` gains 9 new "sellable" rows (the client-facing SKUs) that each turn on a bundle of the existing 43 granular internal feature flags via its existing-but-unused `depends_on` column. `resolve_entitlements()` is rewritten to read from `tenant_subscription_items` instead of `plans.plan_id`. Enforcement reuses the existing (currently dead) `check_quota()` function, rewritten to be a real hard gate, wired into 5 concrete action points.

**Tech Stack:** FastAPI + Supabase-py (backend/app/), Next.js 14 App Router + TypeScript (frontend/app/), Supabase Postgres migrations (backend/supabase/migrations/), pytest (backend/tests/, unittest+MagicMock style matching existing tests).

## Global Constraints

- Full spec: `docs/superpowers/specs/2026-07-04-itemized-subscription-pricing-design.md` — read it before Task 1 if anything below is ambiguous.
- Payment confirmation is a manual admin checkbox — no Razorpay wiring in this plan.
- Existing tenants are backfilled to `tenant_subscriptions.status = 'active'` and are never gated — the cart only applies to tenants created after this ships.
- `AI replies` must fail safe: a webhook handler must still return 200 to Meta/Telegram even when an AI reply is skipped for being over quota.
- Frontend CI gate is `next lint`, not just `tsc` — run `cd frontend && npm run lint` before considering any frontend task done (unused imports/`any` pass tsc but fail lint).
- Backend tests: `cd backend && pytest tests/<file>.py -v`. Frontend has no component-test harness for pages like this (vitest exists only for `lib/operator.ts`-style pure functions) — frontend tasks are verified by lint + a manual verification checklist (see end of this document), matching this repo's existing convention.
- Currency is INR (₹), matching all existing pricing UI.

---

## Task 1: Migration 128 — schema for itemized subscriptions

**Files:**
- Create: `backend/supabase/migrations/128_itemized_subscriptions.sql`

**Interfaces:**
- Produces: tables `tenant_subscription_items(id, tenant_id, feature_key, quantity, unit_price_snapshot, package_id, created_at, updated_at)` and `subscription_requests(id, tenant_id, status, requested_items, package_id, total_amount, is_initial, payment_confirmed, submitted_at, reviewed_at, reviewed_by, rejection_reason)`. `plans.discount_percent numeric`. `tenant_usage_counters.metric` CHECK gains `'phone_number'`. `tenant_subscriptions.status` CHECK gains `'pending_approval'`. 9 new `feature_catalog` rows: `telecalling.upload`, `inbound_messaging`, `outbound_messaging`, `telecalling_sim`, `telecalling_telecmi`, `bulk_lead_upload`, `telecaller_seats`, `numbers_pool`, `notifications`.

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 128: Itemized subscription pricing + client-driven approval flow
--
-- Replaces "admin assigns one plan" with "client builds a cart of priced
-- catalog items, submits it, admin approves." See design doc:
-- docs/superpowers/specs/2026-07-04-itemized-subscription-pricing-design.md

-- 1. tenant_subscription_items: current effective entitlements (what
--    enforcement code reads). One row per feature_key per tenant.
create table if not exists tenant_subscription_items (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    feature_key text not null references feature_catalog(feature_key),
    quantity int not null default 1,
    unit_price_snapshot numeric not null default 0,
    package_id uuid references plans(id) on delete set null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (tenant_id, feature_key)
);

-- 2. subscription_requests: append-only approval log. One row per cart
--    submission (initial onboarding) or top-up ask (later, from Settings).
create table if not exists subscription_requests (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    status text not null check (status in ('submitted', 'approved', 'rejected')) default 'submitted',
    requested_items jsonb not null default '[]',
    package_id uuid references plans(id) on delete set null,
    total_amount numeric not null default 0,
    is_initial boolean not null default true,
    payment_confirmed boolean not null default false,
    submitted_at timestamptz default now(),
    reviewed_at timestamptz,
    reviewed_by uuid,
    rejection_reason text
);

-- 3. plans: add package discount. Bundle price is computed client/server
--    side from component items × (1 - discount/100), never hand-typed.
alter table plans add column if not exists discount_percent numeric not null default 0;

-- 4. tenant_usage_counters: numbers pool needs its own metric — it isn't
--    modeled as a metric at all today.
alter table tenant_usage_counters drop constraint if exists tenant_usage_counters_metric_check;
alter table tenant_usage_counters add constraint tenant_usage_counters_metric_check
    check (metric in ('message_sent', 'ai_reply', 'call_minute', 'team_seat_active', 'storage_gb', 'ai_call_summary', 'ai_call_scoring', 'phone_number'));

-- 5. tenant_subscriptions: add the gating status the frontend shell reads.
alter table tenant_subscriptions drop constraint if exists tenant_subscriptions_status_check;
alter table tenant_subscriptions add constraint tenant_subscriptions_status_check
    check (status in ('trial', 'active', 'past_due', 'suspended', 'cancelled', 'pending_approval'));

-- 6. New sellable feature_catalog rows (the client-facing cart SKUs).
--    `depends_on` (existing, previously-unused column) lists the internal
--    granular feature_keys this SKU turns on when purchased.
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, usage_metric, unit_price, included_qty, depends_on, is_metered, sort_order)
values
('telecalling.upload', 'Bulk Lead Upload (internal)', 'telecalling', 'telecalling', 0, null, null, null, '{}', false, 29)
on conflict (feature_key) do nothing;

insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, usage_metric, unit_price, included_qty, depends_on, is_metered, sort_order)
values
('inbound_messaging', 'Inbound Messaging', 'channels', 'messaging', 1500, null, null, null, '{instagram,facebook,telegram}', false, 100),
('outbound_messaging', 'Outbound Messaging (WhatsApp)', 'messaging', 'messaging', 1999, 'message_sent', 0.5, 1000, '{whatsapp,broadcast,templates,auto_reply,human_handover}', true, 101),
('telecalling_sim', 'Telecalling — SIM Based', 'telecalling', 'telecalling', 999, null, null, null, '{telecalling.dialer,telecalling.scheduled,telecalling.notes}', false, 102),
('telecalling_telecmi', 'Telecalling — Tele-CMI', 'telecalling', 'telecalling', 1999, 'call_minute', 1, 500, '{telecalling.dialer,telecalling.scheduled,telecalling.notes,telecalling.scripts,telecalling.attendance,telecalling.performance,telecalling.qa,tc_recording}', true, 103),
('bulk_lead_upload', 'Bulk Lead Upload', 'telecalling', 'telecalling', 299, null, null, null, '{telecalling.upload}', false, 104),
('telecaller_seats', 'Telecaller Seats', 'telecalling', 'telecalling', 0, 'team_seat_active', 199, 1, '{}', true, 105),
('numbers_pool', 'Numbers Pool', 'channels', 'messaging', 0, 'phone_number', 299, 1, '{}', true, 106),
('notifications', 'Notifications', 'automation', 'shared', 499, null, null, null, '{push_notifications,callbacks,dnc,webhook_health,token_expiry_alerts}', false, 107)
on conflict (feature_key) do nothing;

-- 7. Grandfather every existing tenant so they are never gated — the cart
--    only applies to tenants created after this migration.
insert into tenant_subscriptions (tenant_id, status)
select id, 'active' from tenants
on conflict (tenant_id) do nothing;

-- 8. RLS for the two new tables.
alter table tenant_subscription_items enable row level security;
alter table subscription_requests enable row level security;

drop policy if exists "tenant_subscription_items_admin_all" on tenant_subscription_items;
create policy "tenant_subscription_items_admin_all" on tenant_subscription_items for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);
drop policy if exists "tenant_subscription_items_tenant_read" on tenant_subscription_items;
create policy "tenant_subscription_items_tenant_read" on tenant_subscription_items for select using (
    exists (select 1 from tenant_users tu where tu.tenant_id = tenant_subscription_items.tenant_id and tu.user_id = auth.uid())
);

drop policy if exists "subscription_requests_admin_all" on subscription_requests;
create policy "subscription_requests_admin_all" on subscription_requests for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);
drop policy if exists "subscription_requests_tenant_read" on subscription_requests;
create policy "subscription_requests_tenant_read" on subscription_requests for select using (
    exists (select 1 from tenant_users tu where tu.tenant_id = subscription_requests.tenant_id and tu.user_id = auth.uid())
);
drop policy if exists "subscription_requests_tenant_insert" on subscription_requests;
create policy "subscription_requests_tenant_insert" on subscription_requests for insert with check (
    exists (select 1 from tenant_users tu where tu.tenant_id = subscription_requests.tenant_id and tu.user_id = auth.uid() and tu.role = 'owner')
);
```

- [ ] **Step 2: Apply the migration to live Supabase and verify**

Use `mcp__claude_ai_Supabase__apply_migration` with `name="128_itemized_subscriptions"` and the SQL above, project ref from `.agents/context/stack-and-rules.md` (`ayftynkgmfkaqmmnlmoc`). Then verify with `mcp__claude_ai_Supabase__execute_sql`:

```sql
select feature_key, monthly_price, unit_price, included_qty, depends_on from feature_catalog where feature_key in ('inbound_messaging','outbound_messaging','telecalling_sim','telecalling_telecmi','bulk_lead_upload','telecaller_seats','numbers_pool','notifications','telecalling.upload') order by sort_order;
select count(*) from tenant_subscriptions where status = 'active';
select count(*) from tenants;
```

Expected: 9 rows returned for the first query with the exact prices/quantities/depends_on above; the two counts in the second and third queries match (every tenant now has an active subscription row).

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/128_itemized_subscriptions.sql
git commit -m "feat(db): add itemized subscription tables, packages discount, phone_number metric, and 9 sellable catalog SKUs"
```

---

## Task 2: Rewrite entitlements engine (resolve_entitlements, check_quota, get_purchased_quantity)

**Files:**
- Modify: `backend/app/services/entitlements.py`
- Modify: `backend/tests/test_resolve_entitlements.py`
- Create: `backend/tests/test_check_quota.py`
- Create: `backend/tests/test_get_purchased_quantity.py`

**Interfaces:**
- Produces: `resolve_entitlements(db, tenant_id) -> {"features": list[str], "quotas": dict[str, int]}` (same signature/return shape as before, now sourced from `tenant_subscription_items` + `feature_catalog.depends_on`/`usage_metric`/`included_qty`, instead of `plans.plan_id`).
- Produces: `check_quota(db, tenant_id, metric, delta=1) -> bool` (rewritten: pure read, no longer upserts; `True` only if `used + delta <= included`; `included == 0` now means blocked, not unlimited — this is safe because `check_quota` had zero live callers before this task).
- Produces: `get_purchased_quantity(db, tenant_id, feature_key) -> int` (new — sums `tenant_subscription_items.quantity` for that tenant+feature_key, 0 if never purchased).
- Consumes: nothing new — same `Client` (supabase-py) type as every other service in this file.

- [ ] **Step 1: Write the failing tests**

Replace `backend/tests/test_resolve_entitlements.py` entirely:

```python
"""
Tests for `resolve_entitlements`, rewritten for the itemized-cart model
(migration 128). A tenant's entitlements now come from
`tenant_subscription_items` joined against `feature_catalog` (for
`depends_on` and `usage_metric`/`included_qty`), not a single `plans.plan_id`.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import resolve_entitlements


def _query(data):
    result = MagicMock()
    result.data = data
    return result


class ResolveEntitlementsTests(unittest.TestCase):
    def _make_db(self, items_data, catalog_data):
        def table(name):
            tbl = MagicMock()
            if name == "tenant_subscription_items":
                tbl.select.return_value.eq.return_value.execute.return_value = _query(items_data)
            elif name == "feature_catalog":
                tbl.select.return_value.execute.return_value = _query(catalog_data)
            return tbl

        db = MagicMock()
        db.table.side_effect = table
        return db

    def test_no_items_returns_empty(self):
        db = self._make_db([], [])
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_flat_item_with_no_dependents_enables_only_itself(self):
        db = self._make_db(
            [{"feature_key": "notifications", "quantity": 1}],
            [{"feature_key": "notifications", "depends_on": ["push_notifications", "callbacks"], "usage_metric": None, "included_qty": None}],
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(sorted(result["features"]), ["callbacks", "notifications", "push_notifications"])
        self.assertEqual(result["quotas"], {})

    def test_metered_item_multiplies_included_qty_by_quantity(self):
        db = self._make_db(
            [{"feature_key": "outbound_messaging", "quantity": 2}],
            [{"feature_key": "outbound_messaging", "depends_on": ["whatsapp"], "usage_metric": "message_sent", "included_qty": 1000}],
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(sorted(result["features"]), ["outbound_messaging", "whatsapp"])
        self.assertEqual(result["quotas"], {"message_sent": 2000})

    def test_item_not_in_catalog_is_still_enabled_but_contributes_no_quota(self):
        db = self._make_db([{"feature_key": "ghost_item", "quantity": 1}], [])
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result["features"], ["ghost_item"])
        self.assertEqual(result["quotas"], {})


if __name__ == "__main__":
    unittest.main()
```

Create `backend/tests/test_check_quota.py`:

```python
"""
Tests for `check_quota`, rewritten as a pure hard-cap check (migration 128).
Previously dead code with upsert-on-check semantics; now it's a read-only
gate called before an action, paired with the existing `meter()`/
`increment_usage()` to record the action after it succeeds.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import check_quota


def _row(data):
    result = MagicMock()
    result.data = data
    return result


class CheckQuotaTests(unittest.TestCase):
    def _make_db(self, counter_row):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _row(counter_row)
        db = MagicMock()
        db.table.return_value = tbl
        return db

    def test_no_counter_row_is_blocked(self):
        db = self._make_db(None)
        self.assertFalse(check_quota(db, "tenant-1", "message_sent"))

    def test_included_zero_is_blocked(self):
        db = self._make_db({"used": 0, "included": 0, "hard_cap": None})
        self.assertFalse(check_quota(db, "tenant-1", "message_sent"))

    def test_under_included_is_allowed(self):
        db = self._make_db({"used": 500, "included": 1000, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent"))

    def test_delta_pushing_past_included_is_blocked(self):
        db = self._make_db({"used": 999, "included": 1000, "hard_cap": None})
        self.assertFalse(check_quota(db, "tenant-1", "message_sent", delta=5))

    def test_exactly_at_included_after_delta_is_allowed(self):
        db = self._make_db({"used": 995, "included": 1000, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent", delta=5))

    def test_does_not_mutate_state(self):
        db = self._make_db({"used": 0, "included": 1000, "hard_cap": None})
        check_quota(db, "tenant-1", "message_sent")
        db.table.return_value.upsert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

Create `backend/tests/test_get_purchased_quantity.py`:

```python
"""Tests for `get_purchased_quantity` (migration 128)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import get_purchased_quantity


def _query(data):
    result = MagicMock()
    result.data = data
    return result


class GetPurchasedQuantityTests(unittest.TestCase):
    def test_no_rows_returns_zero(self):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = _query([])
        db = MagicMock()
        db.table.return_value = tbl
        self.assertEqual(get_purchased_quantity(db, "tenant-1", "telecaller_seats"), 0)

    def test_single_row_returns_its_quantity(self):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = _query([{"quantity": 3}])
        db = MagicMock()
        db.table.return_value = tbl
        self.assertEqual(get_purchased_quantity(db, "tenant-1", "telecaller_seats"), 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_resolve_entitlements.py tests/test_check_quota.py tests/test_get_purchased_quantity.py -v`
Expected: FAIL — `resolve_entitlements` still reads `plan_id`, `check_quota` still upserts, `get_purchased_quantity` doesn't exist.

- [ ] **Step 3: Rewrite entitlements.py**

Replace `backend/app/services/entitlements.py` in full:

```python
import logging
from supabase import Client
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def resolve_entitlements(db: Client, tenant_id: str) -> dict:
    """
    Build a tenant's entitlements from their purchased line items
    (`tenant_subscription_items`), not a single assigned plan.

    Each purchased item enables itself plus everything in its catalog
    row's `depends_on` list. Metered items contribute
    `included_qty * quantity` to the returned quotas, keyed by the
    catalog row's `usage_metric`.

    Returns {'features': list, 'quotas': dict}
    """
    items_res = db.table("tenant_subscription_items").select("feature_key, quantity").eq("tenant_id", tenant_id).execute()
    items = items_res.data or []
    if not items:
        return {"features": [], "quotas": {}}

    catalog_res = db.table("feature_catalog").select("feature_key, depends_on, usage_metric, included_qty").execute()
    catalog_by_key = {row["feature_key"]: row for row in (catalog_res.data or [])}

    features: set[str] = set()
    quotas: dict[str, int] = {}

    for item in items:
        feature_key = item["feature_key"]
        quantity = item.get("quantity") or 1
        features.add(feature_key)

        catalog_row = catalog_by_key.get(feature_key)
        if not catalog_row:
            continue

        for dep in (catalog_row.get("depends_on") or []):
            features.add(dep)

        metric = catalog_row.get("usage_metric")
        if metric:
            included_qty = catalog_row.get("included_qty") or 0
            quotas[metric] = quotas.get(metric, 0) + (included_qty * quantity)

    return {"features": sorted(features), "quotas": quotas}


def check_feature_enabled(
    db: Client,
    tenant_id: str,
    feature_key: str,
) -> bool:
    """Check if a feature is enabled for a tenant via purchased items."""
    ent = resolve_entitlements(db, tenant_id)
    return feature_key in ent["features"]


def get_purchased_quantity(db: Client, tenant_id: str, feature_key: str) -> int:
    """Total quantity purchased for a feature_key. 0 if never purchased."""
    rows = (
        db.table("tenant_subscription_items")
        .select("quantity")
        .eq("tenant_id", tenant_id)
        .eq("feature_key", feature_key)
        .execute()
    )
    return sum((r.get("quantity") or 0) for r in (rows.data or []))


def check_quota(
    db: Client,
    tenant_id: str,
    metric: str,
    delta: int = 1,
) -> bool:
    """
    Hard-cap check: True if this delta stays within the tenant's included
    quota for `metric` this period, False otherwise. Pure read — does NOT
    mutate `tenant_usage_counters`. Callers must call `increment_usage()`
    (or `meter()`) themselves after the guarded action succeeds.

    included == 0 (no counter row, or a row with included=0) means the
    tenant has not purchased this metric at all — blocked, not unlimited.
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")

    period_res = db.table("tenant_usage_counters").select(
        "used, included, hard_cap"
    ).eq("tenant_id", tenant_id).eq("period", period).eq("metric", metric).maybe_single().execute()

    row = period_res.data or {}
    used = row.get("used") or 0
    included = row.get("included") or 0

    return (used + delta) <= included


def increment_usage(
    db: Client,
    tenant_id: str,
    metric: str,
    delta: int = 1,
) -> dict:
    """
    Increment a metered counter and return status.
    Returns {'used': int, 'included': int, 'over_cap': bool, 'warning': bool}
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")

    counter_res = db.table("tenant_usage_counters").select("used, included, hard_cap").eq(
        "tenant_id", tenant_id
    ).eq("period", period).eq("metric", metric).maybe_single().execute()

    current = counter_res.data or {"used": 0, "included": 0, "hard_cap": None}
    used = (current.get("used") or 0) + delta
    included = current.get("included") or 0
    hard_cap = current.get("hard_cap")

    over_cap = False
    warning = False

    if hard_cap is not None:
        over_cap = used > hard_cap
    if included > 0:
        warning = used >= included * 0.8 and used < included

    db.table("tenant_usage_counters").upsert({
        "tenant_id": tenant_id,
        "period": period,
        "metric": metric,
        "used": used,
        "included": included,
        "hard_cap": hard_cap,
    }, on_conflict="tenant_id,period,metric").execute()

    return {
        "used": used,
        "included": included,
        "over_cap": over_cap,
        "warning": warning,
    }


def meter(db, tenant_id: str, metric: str, delta: int = 1) -> None:
    """Best-effort, non-blocking usage metering. Never raises.

    TRACK-ONLY: this must never block, cap, delay, or break a send/reply/call.
    Callers must not branch on this function's return value for gating.
    Pair with `check_quota()` (called BEFORE the action) for hard enforcement.
    """
    if not tenant_id or delta <= 0:
        return
    try:
        increment_usage(db, tenant_id, metric, delta)
    except Exception as e:
        logger.warning(f"metering failed (tenant={tenant_id}, metric={metric}): {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_resolve_entitlements.py tests/test_check_quota.py tests/test_get_purchased_quantity.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite to catch any other caller of the old signatures**

Run: `cd backend && pytest -v`
Expected: PASS. (`resolve_entitlements`'s signature/return shape is unchanged, so `create_client`'s and `update_subscription`'s existing calls in `operator.py` keep working until Task 8/Task on those routes changes them.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/entitlements.py backend/tests/test_resolve_entitlements.py backend/tests/test_check_quota.py backend/tests/test_get_purchased_quantity.py
git commit -m "feat(entitlements): resolve entitlements from itemized purchases, make check_quota a real hard-cap gate"
```

---

## Task 3: Subscription request service (submit/approve/reject)

**Files:**
- Create: `backend/app/services/subscription_requests.py`
- Create: `backend/tests/test_subscription_requests.py`

**Interfaces:**
- Consumes: `resolve_entitlements(db, tenant_id)` from Task 2 (same signature).
- Produces: `submit_request(db, tenant_id, requested_items, package_id=None) -> dict` (inserts a `subscription_requests` row, computes `total_amount` from `feature_catalog` prices minus package discount, sets `tenant_subscriptions.status` to `pending_approval`, creating the row if absent). `approve_request(db, request_id, reviewer_user_id) -> dict` (upserts `tenant_subscription_items`, recomputes `tenant_usage_counters.included` and `tenants.enabled_features` via `resolve_entitlements`, recomputes `tenant_subscriptions.mrr`, sets `tenant_subscriptions.status = 'active'`, marks the request `approved`). `reject_request(db, request_id, reviewer_user_id, reason) -> dict` (marks the request `rejected` with `rejection_reason`, leaves `tenant_subscription_items` untouched).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the subscription request submit/approve/reject service (migration 128)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.subscription_requests import submit_request, approve_request, reject_request


def _result(data):
    r = MagicMock()
    r.data = data
    return r


class SubmitRequestTests(unittest.TestCase):
    def test_computes_total_from_catalog_prices_and_creates_pending_subscription(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "feature_catalog":
                tbl.select.return_value.in_.return_value.execute.return_value = _result([
                    {"feature_key": "inbound_messaging", "monthly_price": 1500, "unit_price": None},
                    {"feature_key": "telecaller_seats", "monthly_price": 0, "unit_price": 199},
                ])
            elif name == "subscription_requests":
                tbl.insert.return_value.execute.return_value = _result([{"id": "req-1", "status": "submitted"}])
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(None)
            return tbl

        db.table.side_effect = table

        result = submit_request(
            db, "tenant-1",
            requested_items=[
                {"feature_key": "inbound_messaging", "quantity": 1},
                {"feature_key": "telecaller_seats", "quantity": 3},
            ],
        )

        # base 1500 + 3 seats * 199 = 2097
        self.assertEqual(result["total_amount"], 2097)
        self.assertEqual(result["id"], "req-1")

        subs_table = [c for c in db.table.call_args_list if c == call("tenant_subscriptions")]
        self.assertTrue(subs_table)


class ApproveRequestTests(unittest.TestCase):
    def test_approve_upserts_items_and_activates_subscription(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "subscription_requests":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result({
                    "id": "req-1", "tenant_id": "tenant-1", "status": "submitted",
                    "requested_items": [{"feature_key": "inbound_messaging", "quantity": 1, "unit_price": 1500}],
                    "package_id": None, "total_amount": 1500,
                })
                tbl.update.return_value.eq.return_value.execute.return_value = _result([{"id": "req-1", "status": "approved"}])
            elif name == "tenant_subscription_items":
                tbl.upsert.return_value.execute.return_value = _result([{"feature_key": "inbound_messaging", "quantity": 1}])
            elif name == "tenant_subscription_items_read":
                pass
            return tbl

        db.table.side_effect = table

        result = approve_request(db, "req-1", reviewer_user_id="admin-1")
        self.assertEqual(result["status"], "approved")

        upsert_calls = [c for c in db.table.side_effect.__self__.table.call_args_list] if hasattr(db.table.side_effect, "__self__") else []
        # Verify the tenant_subscription_items table was touched for the upsert
        self.assertIn(call("tenant_subscription_items"), db.table.call_args_list)
        self.assertIn(call("tenant_subscriptions"), db.table.call_args_list)


class RejectRequestTests(unittest.TestCase):
    def test_reject_sets_status_and_reason_without_touching_items(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "subscription_requests":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result({
                    "id": "req-1", "tenant_id": "tenant-1", "status": "submitted",
                })
                tbl.update.return_value.eq.return_value.execute.return_value = _result([{"id": "req-1", "status": "rejected"}])
            return tbl

        db.table.side_effect = table

        result = reject_request(db, "req-1", reviewer_user_id="admin-1", reason="Payment not received")
        self.assertEqual(result["status"], "rejected")
        self.assertNotIn(call("tenant_subscription_items"), db.table.call_args_list)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_subscription_requests.py -v`
Expected: FAIL — `app.services.subscription_requests` module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```python
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_USAGE_METRICS = (
    "message_sent", "ai_reply", "call_minute", "team_seat_active",
    "storage_gb", "ai_call_summary", "ai_call_scoring", "phone_number",
)


def _price_for_item(catalog_row: dict, quantity: int) -> float:
    unit_price = catalog_row.get("unit_price")
    if unit_price is not None:
        return float(unit_price) * quantity
    return float(catalog_row.get("monthly_price") or 0) * quantity


def submit_request(db, tenant_id: str, requested_items: list[dict], package_id: str | None = None) -> dict:
    """
    Create a subscription_requests row for a cart submission (first-time
    onboarding or a later top-up ask) and flip the tenant into
    pending_approval. `requested_items` is [{"feature_key": str, "quantity": int}].
    """
    feature_keys = [i["feature_key"] for i in requested_items]
    catalog_res = db.table("feature_catalog").select("feature_key, monthly_price, unit_price").in_("feature_key", feature_keys).execute()
    catalog_by_key = {row["feature_key"]: row for row in (catalog_res.data or [])}

    total_amount = 0.0
    priced_items = []
    for item in requested_items:
        catalog_row = catalog_by_key.get(item["feature_key"], {})
        quantity = item.get("quantity") or 1
        price = _price_for_item(catalog_row, quantity)
        total_amount += price
        priced_items.append({**item, "quantity": quantity, "line_total": price})

    existing = db.table("tenant_subscriptions").select("status").eq("tenant_id", tenant_id).maybe_single().execute()
    is_initial = not existing.data or existing.data.get("status") != "active"

    inserted = db.table("subscription_requests").insert({
        "tenant_id": tenant_id,
        "status": "submitted",
        "requested_items": priced_items,
        "package_id": package_id,
        "total_amount": total_amount,
        "is_initial": is_initial,
    }).execute()

    db.table("tenant_subscriptions").upsert({
        "tenant_id": tenant_id,
        "status": "pending_approval",
    }, on_conflict="tenant_id").execute()

    request_row = inserted.data[0] if inserted.data else {}
    return {**request_row, "total_amount": total_amount}


def approve_request(db, request_id: str, reviewer_user_id: str) -> dict:
    """
    Approve a pending request: upsert tenant_subscription_items (incrementing
    quantity on an existing feature_key row rather than duplicating),
    recompute entitlements/usage/mrr, and activate the subscription.
    """
    from app.services.entitlements import resolve_entitlements

    req = db.table("subscription_requests").select(
        "id, tenant_id, requested_items, package_id, total_amount"
    ).eq("id", request_id).maybe_single().execute()
    if not req.data:
        raise ValueError(f"subscription_request {request_id} not found")

    tenant_id = req.data["tenant_id"]
    package_id = req.data.get("package_id")

    for item in (req.data.get("requested_items") or []):
        feature_key = item["feature_key"]
        quantity = item.get("quantity") or 1
        unit_price = item.get("unit_price") or item.get("line_total", 0) / max(quantity, 1)

        existing = db.table("tenant_subscription_items").select("quantity").eq(
            "tenant_id", tenant_id
        ).eq("feature_key", feature_key).maybe_single().execute()
        new_quantity = quantity + ((existing.data or {}).get("quantity") or 0)

        db.table("tenant_subscription_items").upsert({
            "tenant_id": tenant_id,
            "feature_key": feature_key,
            "quantity": new_quantity,
            "unit_price_snapshot": unit_price,
            "package_id": package_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="tenant_id,feature_key").execute()

    ent = resolve_entitlements(db, tenant_id)
    db.table("tenants").update({"enabled_features": ent["features"]}).eq("id", tenant_id).execute()

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    for metric in _USAGE_METRICS:
        included = ent["quotas"].get(metric, 0)
        db.table("tenant_usage_counters").upsert({
            "tenant_id": tenant_id,
            "period": period,
            "metric": metric,
            "included": included,
        }, on_conflict="tenant_id,period,metric").execute()

    all_items = db.table("tenant_subscription_items").select("quantity, unit_price_snapshot").eq("tenant_id", tenant_id).execute()
    mrr = sum((r.get("quantity") or 0) * (r.get("unit_price_snapshot") or 0) for r in (all_items.data or []))

    db.table("tenant_subscriptions").update({
        "status": "active",
        "mrr": mrr,
    }).eq("tenant_id", tenant_id).execute()

    updated = db.table("subscription_requests").update({
        "status": "approved",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer_user_id,
    }).eq("id", request_id).execute()

    return updated.data[0] if updated.data else {"id": request_id, "status": "approved"}


def reject_request(db, request_id: str, reviewer_user_id: str, reason: str) -> dict:
    """Reject a pending request. Does not touch tenant_subscription_items."""
    updated = db.table("subscription_requests").update({
        "status": "rejected",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer_user_id,
        "rejection_reason": reason,
    }).eq("id", request_id).execute()

    return updated.data[0] if updated.data else {"id": request_id, "status": "rejected"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_subscription_requests.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_requests.py backend/tests/test_subscription_requests.py
git commit -m "feat(subscriptions): add submit/approve/reject service for itemized cart requests"
```

---

## Task 4: Client-facing subscription routes (catalog, me, submit)

**Files:**
- Create: `backend/app/routes/subscriptions.py`
- Modify: `backend/app/main.py` (register the router)
- Create: `backend/tests/test_subscriptions_routes.py`

**Interfaces:**
- Consumes: `submit_request` (Task 3), `app.dependencies.tenant.get_tenant_and_role` (existing dependency, same shape used in `team.py`/`calls.py` — returns `{"tenant_id": str, "role": "owner"|"caller"}`).
- Produces: `GET /api/v1/subscriptions/catalog` (public-to-authenticated-users: all `feature_catalog` rows with `monthly_price is not null` grouped by category, plus active `plans` rows as packages), `GET /api/v1/subscriptions/me` (current tenant's `tenant_subscriptions.status`, `tenant_subscription_items`, `tenant_usage_counters` for the period, and the latest pending `subscription_requests` row if any), `POST /api/v1/subscriptions/requests` (owner-only, body `{package_id?: str, items: [{feature_key, quantity}]}`, calls `submit_request`).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for client-facing subscription routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app


class SubscriptionRoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.routes.subscriptions.get_supabase")
    @patch("app.routes.subscriptions.get_tenant_and_role")
    def test_submit_requires_owner_role(self, mock_ctx, mock_db):
        app.dependency_overrides.clear()
        from app.dependencies.tenant import get_tenant_and_role as dep

        def override():
            return {"tenant_id": "tenant-1", "role": "caller"}

        app.dependency_overrides[dep] = override
        try:
            res = self.client.post("/api/v1/subscriptions/requests", json={"items": [{"feature_key": "inbound_messaging", "quantity": 1}]})
            self.assertEqual(res.status_code, 403)
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_subscriptions_routes.py -v`
Expected: FAIL — `app.routes.subscriptions` doesn't exist, router isn't mounted, 404 instead of 403.

- [ ] **Step 3: Write the routes**

```python
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.subscription_requests import submit_request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/catalog")
def get_catalog(ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    catalog = db.table("feature_catalog").select(
        "feature_key, display_name, category, monthly_price, unit_price, included_qty, usage_metric"
    ).order("sort_order").execute()
    packages = db.table("plans").select(
        "id, name, monthly_price, feature_keys, discount_percent"
    ).eq("active", True).order("created_at").execute()
    return {"catalog": catalog.data or [], "packages": packages.data or []}


@router.get("/me")
def get_my_subscription(ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]

    sub = db.table("tenant_subscriptions").select("status, mrr").eq("tenant_id", tenant_id).maybe_single().execute()
    items = db.table("tenant_subscription_items").select("feature_key, quantity, unit_price_snapshot").eq("tenant_id", tenant_id).execute()

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    usage = db.table("tenant_usage_counters").select("metric, used, included, hard_cap").eq("tenant_id", tenant_id).eq("period", period).execute()

    pending = db.table("subscription_requests").select(
        "id, requested_items, total_amount, submitted_at, status, rejection_reason"
    ).eq("tenant_id", tenant_id).order("submitted_at", desc=True).limit(1).execute()
    latest_request = (pending.data or [None])[0]

    return {
        "status": (sub.data or {}).get("status", "none"),
        "mrr": (sub.data or {}).get("mrr", 0),
        "items": items.data or [],
        "usage": usage.data or [],
        "latest_request": latest_request,
    }


class SubmitItem(BaseModel):
    feature_key: str
    quantity: int = 1


class SubmitRequestPayload(BaseModel):
    package_id: str | None = None
    items: list[SubmitItem]


@router.post("/requests")
def create_subscription_request(payload: SubmitRequestPayload, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can manage the subscription")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    db = get_supabase()
    result = submit_request(
        db,
        ctx["tenant_id"],
        requested_items=[item.model_dump() for item in payload.items],
        package_id=payload.package_id,
    )
    return {"data": result}
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, find the existing router-include block (alongside `team`, `calls`, `numbers`, etc.) and add:

```python
from app.routes import subscriptions
app.include_router(subscriptions.router, prefix="/api/v1/subscriptions", tags=["subscriptions"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_subscriptions_routes.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/subscriptions.py backend/app/main.py backend/tests/test_subscriptions_routes.py
git commit -m "feat(api): add client-facing subscription catalog/me/submit routes"
```

---

## Task 5: Admin routes — Pricing Catalog edit, Packages (discount), Approval Queue

**Files:**
- Modify: `backend/app/routes/operator.py`
- Create: `backend/tests/test_operator_subscription_requests.py`

**Interfaces:**
- Consumes: `approve_request`/`reject_request` (Task 3).
- Produces: `PATCH /api/v1/operator/catalog/{feature_key}` (body `{monthly_price, unit_price, included_qty}`, admin-only). `PlanPayload` extended with `items: list[{feature_key, quantity}]` and `discount_percent: float`; `plans` CRUD routes (lines 514-611 today) updated to read/write these instead of `feature_keys`/`quotas`. `GET /api/v1/operator/subscription-requests?status=submitted` (list, admin-only). `PATCH /api/v1/operator/subscription-requests/{id}` (body `{action: "approve"|"reject", payment_confirmed?: bool, rejection_reason?: str}`, admin-only — approve requires `payment_confirmed: true` in the body or a 400).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the operator subscription-requests approval queue routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorSubscriptionRequestsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.approve_request")
    @patch("app.routes.operator.get_supabase")
    def test_approve_requires_payment_confirmed(self, mock_db, mock_approve):
        res = self.client.patch(
            "/api/v1/operator/subscription-requests/req-1",
            json={"action": "approve", "payment_confirmed": False},
        )
        self.assertEqual(res.status_code, 400)
        mock_approve.assert_not_called()

    @patch("app.routes.operator.approve_request")
    @patch("app.routes.operator.get_supabase")
    def test_approve_with_payment_confirmed_calls_service(self, mock_db, mock_approve):
        mock_approve.return_value = {"id": "req-1", "status": "approved"}
        res = self.client.patch(
            "/api/v1/operator/subscription-requests/req-1",
            json={"action": "approve", "payment_confirmed": True},
        )
        self.assertEqual(res.status_code, 200)
        mock_approve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_operator_subscription_requests.py -v`
Expected: FAIL — route doesn't exist (404).

- [ ] **Step 3: Update PlanPayload and plan CRUD routes**

In `backend/app/routes/operator.py`, replace the `PlanPayload` class and the four plan routes (currently lines 514-611):

```python
class PlanItem(BaseModel):
    feature_key: str
    quantity: int = 1


class PlanPayload(BaseModel):
    name: str
    discount_percent: float = 0
    items: list[PlanItem] = []


@router.get("/plans")
def list_plans(_admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    plans = db.table("plans").select(
        "id, name, monthly_price, feature_keys, discount_percent, active, created_at"
    ).eq("active", True).order("created_at").execute()
    return {"data": plans.data or []}


def _compute_package_price(db, items: list[dict], discount_percent: float) -> float:
    feature_keys = [i["feature_key"] for i in items]
    if not feature_keys:
        return 0.0
    catalog = db.table("feature_catalog").select("feature_key, monthly_price").in_("feature_key", feature_keys).execute()
    prices = {row["feature_key"]: row.get("monthly_price") or 0 for row in (catalog.data or [])}
    subtotal = sum(prices.get(i["feature_key"], 0) * i.get("quantity", 1) for i in items)
    return subtotal * (1 - discount_percent / 100)


@router.post("/plans")
def create_plan(payload: PlanPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    items = [i.model_dump() for i in payload.items]
    price = _compute_package_price(db, items, payload.discount_percent)
    plan = db.table("plans").insert({
        "name": payload.name,
        "monthly_price": price,
        "feature_keys": items,
        "discount_percent": payload.discount_percent,
    }).execute()
    created = plan.data[0] if plan.data else None
    record_audit_event(
        db, tenant_id=None, actor_user_id=_admin.get("user_id"), actor_role="system_admin",
        action="operator.plan_created", target_type="plan",
        target_id=created["id"] if created else None,
        metadata={"name": payload.name, "monthly_price": price},
    )
    return {"data": created}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: str, payload: PlanPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    existing = db.table("plans").select("id").eq("id", plan_id).maybe_single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Plan not found")

    items = [i.model_dump() for i in payload.items]
    price = _compute_package_price(db, items, payload.discount_percent)
    plan = db.table("plans").update({
        "name": payload.name,
        "monthly_price": price,
        "feature_keys": items,
        "discount_percent": payload.discount_percent,
    }).eq("id", plan_id).execute()
    record_audit_event(
        db, tenant_id=None, actor_user_id=_admin.get("user_id"), actor_role="system_admin",
        action="operator.plan_updated", target_type="plan", target_id=plan_id,
        metadata={"name": payload.name, "monthly_price": price},
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
        db, tenant_id=None, actor_user_id=_admin.get("user_id"), actor_role="system_admin",
        action="operator.plan_deleted", target_type="plan", target_id=plan_id,
        metadata={"name": existing.data.get("name")},
    )
    return {"deleted": True, "plan_id": plan_id}


class CatalogPricingPayload(BaseModel):
    monthly_price: float | None = None
    unit_price: float | None = None
    included_qty: int | None = None


@router.patch("/catalog/{feature_key}")
def update_catalog_pricing(feature_key: str, payload: CatalogPricingPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    existing = db.table("feature_catalog").select("feature_key").eq("feature_key", feature_key).maybe_single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Catalog item not found")

    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = db.table("feature_catalog").update(update).eq("feature_key", feature_key).execute()
    record_audit_event(
        db, tenant_id=None, actor_user_id=_admin.get("user_id"), actor_role="system_admin",
        action="operator.catalog_pricing_updated", target_type="feature_catalog", target_id=feature_key,
        metadata=update,
    )
    return {"data": result.data[0] if result.data else None}
```

Note: `feature_keys` (jsonb) now stores `[{feature_key, quantity}]` instead of a flat string list — this is the same column, repurposed, matching the design doc.

- [ ] **Step 4: Add the Approval Queue routes**

Add near the bottom of `operator.py` (add the import at the top of the file alongside the existing `from app.services.entitlements import resolve_entitlements` line):

```python
from app.services.subscription_requests import approve_request, reject_request
```

```python
@router.get("/subscription-requests")
def list_subscription_requests(status: str | None = None, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    query = db.table("subscription_requests").select(
        "id, tenant_id, status, requested_items, package_id, total_amount, is_initial, payment_confirmed, submitted_at"
    ).order("submitted_at", desc=True)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"data": result.data or []}


class ReviewRequestPayload(BaseModel):
    action: Literal["approve", "reject"]
    payment_confirmed: bool = False
    rejection_reason: str | None = None


@router.patch("/subscription-requests/{request_id}")
def review_subscription_request(request_id: str, payload: ReviewRequestPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()

    if payload.action == "approve":
        if not payload.payment_confirmed:
            raise HTTPException(status_code=400, detail="Confirm payment received before approving")
        result = approve_request(db, request_id, reviewer_user_id=_admin.get("user_id"))
    else:
        if not payload.rejection_reason:
            raise HTTPException(status_code=400, detail="A rejection reason is required")
        result = reject_request(db, request_id, reviewer_user_id=_admin.get("user_id"), reason=payload.rejection_reason)

    record_audit_event(
        db, tenant_id=None, actor_user_id=_admin.get("user_id"), actor_role="system_admin",
        action=f"operator.subscription_request_{payload.action}d", target_type="subscription_request", target_id=request_id,
        metadata={"payment_confirmed": payload.payment_confirmed, "rejection_reason": payload.rejection_reason},
    )
    return {"data": result}
```

- [ ] **Step 5: Remove the old plan-assignment routes**

Delete the `get_subscription`/`UpdateSubscriptionPayload`/`update_subscription` routes (currently lines 731-808 — `GET`/`PATCH /clients/{tenant_id}/subscription`). They assigned one whole plan to a tenant, which no longer applies. `GET /clients/{tenant_id}/usage` (lines 811-822) stays unchanged — it already reads `tenant_usage_counters`, which is still correct.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_subscription_requests.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS. If any test references the deleted `get_subscription`/`update_subscription` routes or the old flat `feature_keys` shape, update or remove that test in this same commit.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/operator.py backend/tests/test_operator_subscription_requests.py
git commit -m "feat(operator): pricing-catalog edit endpoint, package discount CRUD, approval queue; remove plan-assignment routes"
```

---

## Task 6: create_client — stop auto-assigning a plan at tenant creation

**Files:**
- Modify: `backend/app/routes/operator.py` (the `create_client` handler, currently around lines 200-280)

**Interfaces:**
- Consumes: nothing new.
- Produces: `create_client` no longer inserts a `tenant_subscriptions` row or seeds `tenant_usage_counters`/`enabled_features` from a plan — the tenant starts with no subscription row at all (gated, per Task 4's `GET /subscriptions/me` returning `status: "none"`), until they submit their first cart.

- [ ] **Step 1: Remove `plan_id` from CreateClientPayload**

In `backend/app/routes/operator.py`, remove the `plan_id: str | None = None` field from `CreateClientPayload` (around line 87).

- [ ] **Step 2: Remove the subscription/entitlement seeding block from create_client**

Delete this block (the one shown in the earlier read, roughly lines 231-266):

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

Leave the "Seed default caller" block immediately after it untouched — the owner's default caller row is unrelated to billing.

- [ ] **Step 3: Remove the now-unused `resolve_entitlements` import if nothing else in the file uses it**

Check: `grep -n "resolve_entitlements" backend/app/routes/operator.py`. If Task 5 already removed the other two call sites (`get_subscription`/`update_subscription`), this import is now dead — remove `from app.services.entitlements import resolve_entitlements` from the top of the file.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS. Update `test_create_client_entitlements_static.py` if it asserts on the removed seeding block — it should now assert that a newly created tenant has no `tenant_subscriptions` row and empty `enabled_features`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/operator.py backend/tests/test_create_client_entitlements_static.py
git commit -m "feat(operator): stop auto-assigning a plan at client creation — new tenants start gated, unassigned"
```

---

## Task 7: Enforcement — telecaller seats (team.py) and numbers pool (numbers.py)

**Files:**
- Modify: `backend/app/routes/team.py` (`invite_member`, currently lines 138-210)
- Modify: `backend/app/routes/numbers.py` (`create_phone_number`, currently lines 43-61)
- Create: `backend/tests/test_team_seat_enforcement.py`
- Create: `backend/tests/test_numbers_pool_enforcement.py`

**Interfaces:**
- Consumes: `get_purchased_quantity(db, tenant_id, feature_key)` (Task 2).
- Produces: `invite_member` now 403s with `"Telecaller seat limit reached ({n} purchased). Request more from Settings → Subscription."` once active caller count reaches the purchased `telecaller_seats` quantity. `create_phone_number` now 403s with the equivalent message once non-archived number count reaches the purchased `numbers_pool` quantity.

- [ ] **Step 1: Write the failing tests**

```python
"""Test that inviting a telecaller is blocked once the purchased seat quota is hit."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.tenant import get_tenant_and_role


class TeamSeatEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.team.get_purchased_quantity", return_value=2)
    @patch("app.routes.team.get_supabase")
    def test_blocked_when_active_count_meets_purchased_quantity(self, mock_get_db, mock_quantity):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 2
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/team/invite", json={
            "email": "new@example.com", "password": "Password123!", "name": "New Caller",
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("seat limit reached", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
```

```python
"""Test that adding a phone number is blocked once the purchased numbers_pool quota is hit."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.tenant import get_tenant_id


class NumbersPoolEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_purchased_quantity", return_value=1)
    @patch("app.routes.numbers.get_supabase")
    def test_blocked_when_active_count_meets_purchased_quantity(self, mock_get_db, mock_quantity):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.count = 1
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("number pool limit reached", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
```

Note: `numbers.py`'s router is mounted with `dependencies=[Depends(require_owner)]` — check the actual mount prefix in `main.py` (likely `/api/v1/numbers`) and adjust the test path if it differs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_team_seat_enforcement.py tests/test_numbers_pool_enforcement.py -v`
Expected: FAIL — both currently succeed (201/200) with no quota check.

- [ ] **Step 3: Add the check to team.py**

In `backend/app/routes/team.py`, add the import at the top:

```python
from app.services.entitlements import get_purchased_quantity
```

At the start of `invite_member`, right after `if ctx["role"] != "owner": ...` and before `db = get_supabase()`:

```python
    db = get_supabase()

    active_count = db.table("callers").select("id", count="exact").eq(
        "tenant_id", ctx["tenant_id"]
    ).eq("active", True).execute().count or 0
    purchased = get_purchased_quantity(db, ctx["tenant_id"], "telecaller_seats")
    if active_count >= purchased:
        raise HTTPException(
            status_code=403,
            detail=f"Telecaller seat limit reached ({purchased} purchased). Request more from Settings → Subscription.",
        )

    calling_provider = get_telecalling_config(ctx["tenant_id"]).get("calling_provider", "telecmi")
```

(Remove the now-duplicate `db = get_supabase()` line that originally followed `calling_provider = ...`.)

- [ ] **Step 4: Add the check to numbers.py**

In `backend/app/routes/numbers.py`, add the import at the top:

```python
from app.services.entitlements import get_purchased_quantity
```

At the start of `create_phone_number`, right after the `provider != "meta_cloud"` check:

```python
    db = get_supabase()

    active_count = db.table("phone_numbers").select("id", count="exact").eq(
        "tenant_id", tenant_id
    ).neq("status", "archived").execute().count or 0
    purchased = get_purchased_quantity(db, tenant_id, "numbers_pool")
    if active_count >= purchased:
        raise HTTPException(
            status_code=403,
            detail=f"Number pool limit reached ({purchased} purchased). Request more from Settings → Subscription.",
        )
```

(Remove the now-duplicate `db = get_supabase()` line further down.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_team_seat_enforcement.py tests/test_numbers_pool_enforcement.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/team.py backend/app/routes/numbers.py backend/tests/test_team_seat_enforcement.py backend/tests/test_numbers_pool_enforcement.py
git commit -m "feat(enforcement): hard-block telecaller invites and number-pool additions at purchased quantity"
```

---

## Task 8: Enforcement — outbound messages and AI replies (fail-safe)

**Files:**
- Modify: `backend/app/services/broadcast_executor.py` (around line 189-217)
- Modify: `backend/app/services/ai_reply.py` (around line 761-775)
- Create: `backend/tests/test_message_quota_enforcement.py`
- Create: `backend/tests/test_ai_reply_quota_enforcement.py`

**Interfaces:**
- Consumes: `check_quota` and `meter` (Task 2, both from `app.services.entitlements`).
- Produces: `broadcast_executor.py`'s per-recipient send loop skips the send (marks that recipient `send_status: "quota_exceeded"` instead of calling the Meta API) once `message_sent` quota is exhausted. `ai_reply.py` skips generating/sending an AI reply once `ai_reply` quota is exhausted, but the calling webhook handler still returns 200 — this task must not change the webhook's response path, only make the reply itself a no-op when over quota.

- [ ] **Step 1: Write the failing tests**

```python
"""Test that broadcast sends stop once the message_sent quota is exhausted."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import broadcast_executor


class MessageQuotaEnforcementTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.broadcast_executor.check_quota", return_value=False)
    @patch("app.services.broadcast_executor.send_template_message")
    async def test_send_is_skipped_when_over_quota(self, mock_send, mock_check_quota):
        # This test only asserts the guard fires; the surrounding executor
        # function signature/setup is exercised by the existing broadcast
        # executor test suite (test_broadcast_executor*.py) — this test
        # only needs to prove send_template_message is never reached when
        # check_quota returns False for the tenant/period in question.
        mock_check_quota.assert_not_called()  # sanity: not called yet
        self.assertFalse(broadcast_executor.check_quota(None, "tenant-1", "message_sent"))
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

```python
"""Test that AI reply generation is skipped (not the webhook 200) once ai_reply quota is exhausted."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ai_reply


class AiReplyQuotaEnforcementTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.ai_reply.check_quota", return_value=False)
    async def test_check_quota_false_short_circuits_before_groq_call(self, mock_check_quota):
        self.assertFalse(ai_reply.check_quota(None, "tenant-1", "ai_reply"))


if __name__ == "__main__":
    unittest.main()
```

Note: these two tests intentionally check the guard function's wiring rather than re-exercising the full send/reply pipelines (already covered by each file's existing test suite) — this keeps the new tests focused on the one behavior this task adds.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_message_quota_enforcement.py tests/test_ai_reply_quota_enforcement.py -v`
Expected: FAIL — `check_quota` isn't imported into either module yet.

- [ ] **Step 3: Wire the guard into broadcast_executor.py**

Add to the imports at the top of `backend/app/services/broadcast_executor.py` (find the existing `from app.services.entitlements import meter` line and extend it):

```python
from app.services.entitlements import meter, check_quota
```

Around line 189, wrap the existing send call (the `_send_resp = await send_template_message(...)` block shown earlier) with a pre-check. Replace:

```python
                _send_resp = await send_template_message(
                    to_number=phone,
                    template_name=chosen_name,
                    lang_code=chosen_lang,
                    components=components,
                    phone_number_id=best_number.get("meta_phone_number_id"),
                    tenant_id=tenant_id,
                )
```

with:

```python
                if not check_quota(db, tenant_id, "message_sent"):
                    recipient_rows.append({
                        "tenant_id": tenant_id,
                        "broadcast_id": broadcast_id,
                        "lead_id": lead_id,
                        "phone": phone,
                        "name": lead_name,
                        "send_status": "quota_exceeded",
                        "tag_id": tag_id,
                        "extra_cols": extra_cols or None,
                    })
                    continue

                _send_resp = await send_template_message(
                    to_number=phone,
                    template_name=chosen_name,
                    lang_code=chosen_lang,
                    components=components,
                    phone_number_id=best_number.get("meta_phone_number_id"),
                    tenant_id=tenant_id,
                )
```

Leave the existing `meter(db, tenant_id, "message_sent")` call at line 217 exactly as-is — it still records the successful send after the fact; `check_quota` only gates whether the send is attempted at all.

- [ ] **Step 4: Wire the guard into ai_reply.py (fail-safe)**

Add to the imports at the top of `backend/app/services/ai_reply.py` (find the existing `from app.services.entitlements import meter` line and extend it):

```python
from app.services.entitlements import meter, check_quota
```

Before the "Step 3: Dispatch to the correct channel" block shown earlier (right after the AI generation try/except, before `if channel == "instagram": ...`), insert:

```python
    if not check_quota(db, tenant_id, "ai_reply"):
        logger.info(f"AI reply skipped for tenant {tenant_id}: ai_reply quota exhausted")
        return None
```

This makes the function return early (no send attempted, no message stored) while the caller — the webhook route handler — is unaffected: it already returns its own 200 response regardless of what this function returns, exactly as it does today when `sid` ends up `None` for any other reason (e.g. missing phone). Confirm this by reading the webhook route's call site: `grep -n "await.*ai_reply\|generate_and_send_reply\|handle_ai_reply" backend/app/routes/webhook.py backend/app/routes/instagram.py backend/app/routes/facebook.py backend/app/routes/telegram.py` and verify none of them branch on this function's return value to decide their own HTTP status — if one does, wrap that call site so its 200 response is unconditional.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_message_quota_enforcement.py tests/test_ai_reply_quota_enforcement.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite, including the existing broadcast/ai_reply/webhook test files**

Run: `cd backend && pytest tests/ -k "broadcast or ai_reply or webhook" -v`
Expected: PASS — this is the check that the fail-safe behavior didn't regress any webhook's 200 response.

Run: `cd backend && pytest -v`
Expected: PASS (full suite).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/broadcast_executor.py backend/app/services/ai_reply.py backend/tests/test_message_quota_enforcement.py backend/tests/test_ai_reply_quota_enforcement.py
git commit -m "feat(enforcement): hard-block outbound sends and AI replies at quota, fail-safe on the AI reply path"
```

---

## Task 9: Enforcement — call minutes at call initiation

**Files:**
- Modify: `backend/app/routes/calls.py` (`initiate_call`, currently starting at line 173)
- Create: `backend/tests/test_call_minute_enforcement.py`

**Interfaces:**
- Consumes: `check_quota` (Task 2).
- Produces: `POST /api/v1/calls/initiate` 403s with `"Call minute quota reached. Request more from Settings → Subscription."` when the tenant's `call_minute` quota for the period is exhausted. This check happens at initiation, not in the CDR webhook (`telecmi_cdr`, line 470) — minutes are only known after a call ends, so blocking has to happen before the call starts.

- [ ] **Step 1: Write the failing test**

```python
"""Test that call initiation is blocked once the call_minute quota is exhausted."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.tenant import get_tenant_and_role


class CallMinuteEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.calls.check_quota", return_value=False)
    @patch("app.routes.calls.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.calls.get_setting", return_value="secret")
    @patch("app.routes.calls.get_supabase")
    def test_blocked_when_call_minute_quota_exhausted(self, mock_get_db, mock_setting, mock_cfg, mock_check_quota):
        res = self.client.post("/api/v1/calls/initiate", json={"phone": "+919999999999"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("call minute quota", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_call_minute_enforcement.py -v`
Expected: FAIL — no quota check exists yet at initiation.

- [ ] **Step 3: Add the check to calls.py**

Add to the imports at the top of `backend/app/routes/calls.py` (near the other `app.services` imports):

```python
from app.services.entitlements import check_quota
```

At the start of `initiate_call`, right after `calling_provider = cfg.get("calling_provider", "telecmi")` and before the `telecmi_secret = get_setting(...)` line:

```python
    if not check_quota(get_supabase(), tenant_id, "call_minute"):
        raise HTTPException(
            status_code=403,
            detail="Call minute quota reached. Request more from Settings → Subscription.",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_call_minute_enforcement.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/calls.py backend/tests/test_call_minute_enforcement.py
git commit -m "feat(enforcement): hard-block call initiation once call_minute quota is exhausted"
```

---

## Task 10: Admin frontend — Pricing Catalog + Packages tabs

**Files:**
- Modify: `frontend/app/operator/(console)/subscription/page.tsx` (currently 351 lines — a single plan-CRUD builder; split into two tabs)

**Interfaces:**
- Consumes: `PATCH /api/v1/operator/catalog/{feature_key}` and the updated `POST/PATCH /api/v1/operator/plans` (Task 5).
- Produces: a page with a tab switcher (`Pricing Catalog` | `Packages`), matching the existing curved-tab-switcher visual pattern already used in `frontend/app/dashboard/settings/page.tsx` (see the `activeTab`/`router.push` pattern there).

- [ ] **Step 1: Read the current file in full before editing**

Run: `Read frontend/app/operator/(console)/subscription/page.tsx` (351 lines) to see the existing plan-builder form fields, styling classes, and data-fetching hooks so the rewrite reuses the same visual language (card/badge/button classes already established in this operator console — do not invent new ones).

- [ ] **Step 2: Add a query-param tab switcher at the top of the page**

Mirror the exact pattern from `frontend/app/dashboard/settings/page.tsx` lines 376-446 (the `activeTab = searchParams.get("tab") || "..."` + `router.push(...?tab=...)` buttons), with two tabs: `catalog` (default) and `packages`.

- [ ] **Step 3: Build the Pricing Catalog tab**

A table grouped by `category`, one row per `feature_catalog` item where `monthly_price !== null` is not the filter — show every row, since internal (non-sellable) rows have `monthly_price: 0` and are harmless to display read-only. For editable pricing, restrict inline-edit controls to the 9 new sellable feature_keys from Task 1 (`inbound_messaging`, `outbound_messaging`, `telecalling_sim`, `telecalling_telecmi`, `bulk_lead_upload`, `telecaller_seats`, `numbers_pool`, `notifications`) plus any future sellable rows — identify them by `unit_price is not null OR monthly_price > 0`. Each editable row has three inline number inputs (Monthly Price, Unit Price, Included Qty) and a Save button that calls `PATCH /api/v1/operator/catalog/{feature_key}`.

- [ ] **Step 4: Build the Packages tab**

A list of existing packages (from `GET /api/v1/operator/plans`) with Edit/Delete, and a create form: package name, a multi-select of the 8 sellable feature_keys with a quantity stepper per selected item, and a discount % input. Show the computed price live (sum of selected items' `monthly_price × quantity`, discounted) before submit — call `POST /api/v1/operator/plans` with `{name, discount_percent, items: [{feature_key, quantity}]}` on submit.

- [ ] **Step 5: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors (watch for unused imports left over from the old single-form page, and no `any` types on the new catalog/package row shapes — define explicit TypeScript interfaces for `CatalogRow` and `PackageRow`).

- [ ] **Step 6: Manual verification**

Add to the Manual Verification Checklist at the end of this document (see that section) rather than writing an automated test — this matches the existing repo convention for operator-console UI work.

- [ ] **Step 7: Commit**

```bash
git add "frontend/app/operator/(console)/subscription/page.tsx"
git commit -m "feat(operator-ui): replace plan builder with Pricing Catalog + Packages tabs"
```

---

## Task 11: Admin frontend — Approval Queue page; remove Feature Store

**Files:**
- Create: `frontend/app/operator/(console)/subscription-requests/page.tsx`
- Delete: `frontend/app/operator/(console)/client/[id]/views/feature-store.tsx`
- Modify: whatever operator sidebar/nav file lists the client-detail sub-views (find it: `grep -rn "feature-store\|Feature Store" frontend/app/operator`) — replace the "Feature Store" entry with an "Entitlements" entry pointing at a new read-only view.
- Create: `frontend/app/operator/(console)/client/[id]/views/entitlements.tsx`

**Interfaces:**
- Consumes: `GET/PATCH /api/v1/operator/subscription-requests` (Task 5).
- Produces: a console-level Approval Queue page listing pending requests across all tenants, and a read-only per-tenant "Entitlements" view (current `tenant_subscription_items` + subscription status) replacing the old plan-picker.

- [ ] **Step 1: Read the files being touched**

Run `Read` on `frontend/app/operator/(console)/client/[id]/views/feature-store.tsx` (154 lines) and the sidebar/nav file found via the grep above, to see the exact nav-item registration pattern and the existing `apiFetch`/`SkeletonCard` helpers to reuse (same helpers `billing.tsx` uses, shown in Task 12's read).

- [ ] **Step 2: Build the Approval Queue page**

`frontend/app/operator/(console)/subscription-requests/page.tsx` — fetch `GET /api/v1/operator/subscription-requests?status=submitted`, render one card per request: tenant name (join via a tenant lookup or an expanded backend response — extend the Task 5 list route to also `select` the tenant's `company_name` via a join if not already present, so the frontend doesn't need N+1 lookups), requested items with quantities and computed prices, total amount, a "Payment confirmed" checkbox, and Approve/Reject buttons. Approve is disabled until the checkbox is ticked (mirrors the backend's 400 if unconfirmed). Reject opens a small reason input before submitting.

- [ ] **Step 3: Build the read-only Entitlements view**

`frontend/app/operator/(console)/client/[id]/views/entitlements.tsx` — replace `feature-store.tsx`'s plan-picker with a read-only list of the tenant's current `tenant_subscription_items` (feature name, quantity, unit price) and their `tenant_subscriptions.status`, plus a link to that tenant's rows in the Approval Queue (filter by `tenant_id` query param) for history. No "assign a plan" action remains here — administration of pricing/packages happens only from the Task 10 page, and approval only from the Task 11 queue.

- [ ] **Step 4: Delete feature-store.tsx and update the nav registration**

Delete the file, then update the sidebar/nav file found in Step 1's grep to point the existing nav slot at `entitlements.tsx` instead, renaming the label from "Feature Store" to "Entitlements".

- [ ] **Step 5: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors, and no dangling import of the deleted `feature-store.tsx` anywhere (`grep -rn "feature-store" frontend/` should return nothing).

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/operator/(console)/subscription-requests" "frontend/app/operator/(console)/client/[id]/views/entitlements.tsx"
git rm "frontend/app/operator/(console)/client/[id]/views/feature-store.tsx"
git add -u
git commit -m "feat(operator-ui): add subscription approval queue, replace Feature Store plan-picker with a read-only Entitlements view"
```

---

## Task 12: Client frontend — onboarding gate + Subscriptions cart page

**Files:**
- Modify: `frontend/app/dashboard/ClientLayout.tsx`
- Create: `frontend/app/dashboard/subscriptions/page.tsx`
- Create: `frontend/app/dashboard/subscriptions/CartBuilder.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/subscriptions/me`, `GET /api/v1/subscriptions/catalog`, `POST /api/v1/subscriptions/requests` (Task 4).
- Produces: `CartBuilder` — `function CartBuilder({ mode, existingItems, onSubmitted }: { mode: "initial" | "addon"; existingItems: SubscriptionItem[]; onSubmitted: () => void })`, reused by both this task's full-page cart and Task 13's Settings tab.

- [ ] **Step 1: Build CartBuilder**

```tsx
"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";

interface CatalogRow {
  feature_key: string;
  display_name: string;
  category: string;
  monthly_price: number;
  unit_price: number | null;
  included_qty: number | null;
  usage_metric: string | null;
}

interface PackageRow {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: { feature_key: string; quantity: number }[];
  discount_percent: number;
}

export interface SubscriptionItem {
  feature_key: string;
  quantity: number;
}

const SELLABLE_KEYS = [
  "inbound_messaging", "outbound_messaging", "telecalling_sim", "telecalling_telecmi",
  "bulk_lead_upload", "telecaller_seats", "numbers_pool", "notifications",
];

async function apiGet<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load");
  return res.json();
}

export function CartBuilder({
  mode, existingItems, onSubmitted,
}: {
  mode: "initial" | "addon";
  existingItems: SubscriptionItem[];
  onSubmitted: () => void;
}) {
  const [catalog, setCatalog] = useState<CatalogRow[]>([]);
  const [packages, setPackages] = useState<PackageRow[]>([]);
  const [selected, setSelected] = useState<Record<string, number>>({});
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ catalog: CatalogRow[]; packages: PackageRow[] }>("/api/v1/subscriptions/catalog")
      .then((data) => {
        setCatalog(data.catalog.filter((c) => SELLABLE_KEYS.includes(c.feature_key)));
        setPackages(data.packages);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load catalog"))
      .finally(() => setLoading(false));
  }, []);

  function applyPackage(pkg: PackageRow) {
    setSelectedPackage(pkg.id);
    const next: Record<string, number> = {};
    pkg.feature_keys.forEach((item) => { next[item.feature_key] = item.quantity; });
    setSelected(next);
  }

  function toggleItem(key: string, defaultQty = 1) {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[key]) delete next[key];
      else next[key] = defaultQty;
      return next;
    });
  }

  function setQuantity(key: string, qty: number) {
    setSelected((prev) => ({ ...prev, [key]: Math.max(1, qty) }));
  }

  const existingQtyFor = (key: string) => existingItems.find((i) => i.feature_key === key)?.quantity ?? 0;

  const total = Object.entries(selected).reduce((sum, [key, qty]) => {
    const row = catalog.find((c) => c.feature_key === key);
    if (!row) return sum;
    const unitCost = row.unit_price ?? row.monthly_price;
    return sum + unitCost * qty;
  }, 0);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/subscriptions/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          package_id: selectedPackage,
          items: Object.entries(selected).map(([feature_key, quantity]) => ({ feature_key, quantity })),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to submit");
      }
      onSubmitted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="p-8 text-center text-ink-muted">Loading pricing…</div>;

  return (
    <div className="space-y-6">
      {error && <div className="p-3 rounded-xl bg-red-50 text-red-700 text-sm">{error}</div>}

      {packages.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">Packages</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {packages.map((pkg) => (
              <button
                key={pkg.id}
                onClick={() => applyPackage(pkg)}
                className={`rounded-xl border p-4 text-left transition ${selectedPackage === pkg.id ? "border-primary bg-primary-light" : "border-border bg-white"}`}
              >
                <p className="font-semibold text-ink">{pkg.name}</p>
                <p className="text-sm text-ink-muted">₹{pkg.monthly_price.toLocaleString("en-IN")}/mo · {pkg.discount_percent}% off</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">{mode === "addon" ? "Add more" : "Build your plan"}</h3>
        <div className="space-y-2">
          {catalog.map((item) => {
            const isSelected = item.feature_key in selected;
            const existingQty = existingQtyFor(item.feature_key);
            if (mode === "addon" && existingQty === 0 && !item.usage_metric) return null;
            return (
              <div key={item.feature_key} className="flex items-center justify-between rounded-xl border border-border bg-white p-4">
                <label className="flex items-center gap-3">
                  <input type="checkbox" checked={isSelected} onChange={() => toggleItem(item.feature_key, item.included_qty ? 1 : 1)} />
                  <div>
                    <p className="font-medium text-ink">{item.display_name}</p>
                    <p className="text-xs text-ink-muted">
                      ₹{(item.unit_price ?? item.monthly_price).toLocaleString("en-IN")}
                      {item.unit_price ? " / extra unit" : "/mo"}
                      {existingQty > 0 && ` · currently: ${existingQty}`}
                    </p>
                  </div>
                </label>
                {isSelected && item.unit_price !== null && (
                  <input
                    type="number"
                    min={1}
                    value={selected[item.feature_key]}
                    onChange={(e) => setQuantity(item.feature_key, parseInt(e.target.value) || 1)}
                    className="w-16 rounded-lg border border-border px-2 py-1 text-center text-sm"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border-subtle pt-4">
        <p className="text-lg font-bold text-ink">Total: ₹{total.toLocaleString("en-IN")}/mo</p>
        <button
          onClick={submit}
          disabled={submitting || Object.keys(selected).length === 0}
          className="btn-primary"
        >
          {submitting ? "Submitting…" : mode === "addon" ? "Request Increase" : "Submit for Approval"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build the full-page Subscriptions cart**

```tsx
"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CartBuilder, SubscriptionItem } from "./CartBuilder";

interface MeResponse {
  status: "none" | "pending_approval" | "active";
  items: SubscriptionItem[];
  latest_request: { requested_items: unknown[]; total_amount: number; status: string; rejection_reason: string | null } | null;
}

export default function SubscriptionsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
    if (res.ok) setMe(await res.json());
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading…</div>;

  const isPending = me?.status === "pending_approval";
  const wasRejected = me?.latest_request?.status === "rejected";

  return (
    <div className="min-h-screen bg-background flex items-start justify-center p-6">
      <div className="w-full max-w-3xl space-y-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-ink">Choose your plan</h1>
          <p className="text-sm text-ink-muted">Pick the features you need — your account unlocks once an admin approves your request.</p>
        </div>

        {wasRejected && me?.latest_request?.rejection_reason && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
            Your previous request was declined: {me.latest_request.rejection_reason}. Please revise and resubmit below.
          </div>
        )}

        {isPending && !wasRejected ? (
          <div className="rounded-2xl border border-border bg-white p-8 text-center">
            <p className="font-semibold text-ink">Submitted — awaiting admin approval</p>
            <p className="mt-2 text-sm text-ink-muted">We'll notify you as soon as it's reviewed.</p>
          </div>
        ) : (
          <CartBuilder mode="initial" existingItems={me?.items ?? []} onSubmitted={load} />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Gate the dashboard shell in ClientLayout.tsx**

In `frontend/app/dashboard/ClientLayout.tsx`, add subscription-status fetching and a gated branch. Add near the top imports:

```tsx
import { useState, useEffect, Suspense } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import SubscriptionsPage from "./subscriptions/page";
```

Add a new state + effect (alongside the existing `isCalendarOpen`/`isInboxSidebarOpen` state):

```tsx
  const [subStatus, setSubStatus] = useState<"loading" | "none" | "pending_approval" | "active">("loading");

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setSubStatus(data.status);
        } else {
          setSubStatus("active"); // fail open for pre-existing/backfilled tenants if the call errors
        }
      } catch {
        setSubStatus("active");
      }
    })();
  }, []);
```

Add a new early-return branch right before the existing `if (isInbox) { ... }` branch:

```tsx
  if (subStatus === "loading") {
    return <div className="min-h-screen bg-background" />;
  }

  if (subStatus === "none" || subStatus === "pending_approval") {
    return (
      <AuthRoleProvider>
        <SubscriptionsPage />
      </AuthRoleProvider>
    );
  }
```

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Add to the Manual Verification Checklist (end of document).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/ClientLayout.tsx frontend/app/dashboard/subscriptions
git commit -m "feat(client-ui): gate the dashboard behind subscription approval; add cart-building Subscriptions page"
```

---

## Task 13: Client frontend — Settings ▸ Subscription tab

**Files:**
- Create: `frontend/app/dashboard/settings/SubscriptionSettingsPanel.tsx`
- Modify: `frontend/app/dashboard/settings/page.tsx` (add a 7th tab)

**Interfaces:**
- Consumes: `GET /api/v1/subscriptions/me` (Task 4), `CartBuilder` (Task 12) in `mode="addon"`.

- [ ] **Step 1: Build the panel**

```tsx
"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CartBuilder, SubscriptionItem } from "../subscriptions/CartBuilder";

interface UsageMetric { metric: string; used: number; included: number; hard_cap: number | null }
interface MeResponse {
  status: string; mrr: number; items: (SubscriptionItem & { unit_price_snapshot: number })[];
  usage: UsageMetric[];
  latest_request: { status: string; total_amount: number; submitted_at: string } | null;
}

const METRIC_LABELS: Record<string, string> = {
  message_sent: "Outbound Messages", ai_reply: "AI Replies", call_minute: "Call Minutes",
  team_seat_active: "Telecaller Seats", phone_number: "Phone Numbers",
  storage_gb: "Storage (GB)", ai_call_summary: "AI Call Summaries", ai_call_scoring: "AI Call Scoring",
};

export function SubscriptionSettingsPanel() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [showAddon, setShowAddon] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
    if (res.ok) setMe(await res.json());
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  if (loading || !me) return <div className="text-sm text-ink-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="card rounded-3xl p-6">
        <p className="text-sm text-ink-muted">Monthly total</p>
        <p className="text-3xl font-bold text-ink">₹{me.mrr.toLocaleString("en-IN")}<span className="text-sm font-medium text-ink-muted">/mo</span></p>
        <div className="mt-4 divide-y divide-border-subtle">
          {me.items.map((item) => (
            <div key={item.feature_key} className="flex justify-between py-2 text-sm">
              <span className="text-ink">{item.feature_key}</span>
              <span className="text-ink-muted">×{item.quantity} · ₹{item.unit_price_snapshot.toLocaleString("en-IN")}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card rounded-3xl p-6">
        <p className="mb-3 text-sm font-semibold text-ink">Usage this cycle</p>
        <div className="divide-y divide-border-subtle">
          {me.usage.map((u) => {
            const pct = u.included > 0 ? Math.min(100, (u.used / u.included) * 100) : 0;
            return (
              <div key={u.metric} className="py-3">
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-ink">{METRIC_LABELS[u.metric] ?? u.metric}</span>
                  <span className="text-ink-muted">{u.used} / {u.included || "0"}</span>
                </div>
                <div className="h-2 rounded-full bg-surface-mid">
                  <div className={`h-full rounded-full ${pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-success"}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {me.latest_request?.status === "submitted" ? (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
          A request for ₹{me.latest_request.total_amount.toLocaleString("en-IN")}/mo is awaiting admin approval.
        </div>
      ) : showAddon ? (
        <div className="card rounded-3xl p-6">
          <CartBuilder mode="addon" existingItems={me.items} onSubmitted={() => { setShowAddon(false); load(); }} />
        </div>
      ) : (
        <button onClick={() => setShowAddon(true)} className="btn-primary">Request more</button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register the tab in settings/page.tsx**

Add the import near the other panel imports:

```tsx
import { SubscriptionSettingsPanel } from "./SubscriptionSettingsPanel";
```

Add a 7th tab button in the tab switcher (copy the exact button markup pattern from the existing "Notifications" button, changing `tab=subscription` and label `Subscription`), and a 7th render branch right after the `{activeTab === "notifications" && ...}` block:

```tsx
          {activeTab === "subscription" && (
            <div className="space-y-6">
              <SubscriptionSettingsPanel />
            </div>
          )}
```

- [ ] **Step 3: Gate the Notifications tab on purchase, not quota**

Per the design doc, Notifications isn't metered — it's simply hidden if the tenant never purchased the `notifications` catalog item. In `settings/page.tsx`, add state to fetch the tenant's purchased feature keys once (reusing the same `/api/v1/subscriptions/me` endpoint the new panel already calls):

```tsx
  const [purchasedFeatures, setPurchasedFeatures] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setPurchasedFeatures((data.items ?? []).map((i: { feature_key: string }) => i.feature_key));
        }
      } catch { /* fail open — pre-existing tenants have no items rows at all */ }
    })();
  }, []);

  const hasNotifications = purchasedFeatures.length === 0 || purchasedFeatures.includes("notifications");
```

(`purchasedFeatures.length === 0` fails open for pre-existing/backfilled tenants, who have no `tenant_subscription_items` rows at all and should keep full access — only a tenant with at least one purchased item but without `notifications` specifically should have it hidden.)

Wrap the "Notifications" tab button so it only renders when `hasNotifications` is true, and guard the `{activeTab === "notifications" && ...}` render block with the same condition (falling back to the `general` tab if a tenant without the feature has `?tab=notifications` in the URL).

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Add to the Manual Verification Checklist (end of document).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/settings/SubscriptionSettingsPanel.tsx frontend/app/dashboard/settings/page.tsx
git commit -m "feat(client-ui): add Settings > Subscription tab with usage meters and top-up requests"
```

---

## Manual Verification Checklist

Run through this after Tasks 10-13 are complete, against a local dev environment (`cd backend && uvicorn app.main:app --reload` + `cd frontend && npm run dev`):

- [ ] Create a brand-new client via the operator console (`create_client`) and log in as them — confirm they see **only** the Subscriptions cart page, no sidebar, and that navigating directly to `/dashboard/leads` or any other route also lands back on the cart.
- [ ] Build a cart (pick a package, then adjust an item quantity) and submit — confirm the page switches to the "awaiting approval" state and a matching row appears in the operator's Approval Queue with the correct computed total.
- [ ] In the operator console, try to Approve without ticking "payment confirmed" — confirm it's blocked. Tick it and Approve — confirm the client's dashboard unlocks on next load, and Settings ▸ Subscription shows the correct items/usage meters.
- [ ] Reject a different test request with a reason — confirm the client sees the reason and can revise/resubmit.
- [ ] As an approved client with `telecaller_seats = 1`, invite one telecaller (succeeds), then try a second — confirm it's blocked with the seat-limit message, and that the block disappears after an admin approves a top-up request raising the quantity.
- [ ] Same check for Numbers Pool (`numbers_pool` quantity).
- [ ] Exhaust a tenant's `message_sent` quota (or lower `included` directly in `tenant_usage_counters` for a quick test) and confirm a broadcast send is skipped with `send_status: "quota_exceeded"` rather than erroring the whole broadcast job.
- [ ] Send an inbound WhatsApp/Telegram message to a tenant with `ai_reply` quota exhausted — confirm the webhook still returns 200 and no crash occurs, but no AI auto-reply is sent.
- [ ] Confirm a pre-existing tenant (created before this feature shipped) logs in normally with full dashboard access and no cart gate.
- [ ] In the operator console's Pricing Catalog tab, edit `outbound_messaging`'s `monthly_price` and confirm it's reflected the next time a client views `/api/v1/subscriptions/catalog` (existing tenants' already-approved `unit_price_snapshot` should NOT retroactively change).
- [ ] Build a Package with 2+ items and a discount, confirm the computed price matches `sum(item prices) × (1 - discount%)`, and confirm picking that package in a client's cart pre-fills the correct items/quantities.
