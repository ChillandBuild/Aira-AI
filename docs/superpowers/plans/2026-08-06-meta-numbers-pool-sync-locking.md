# Meta-Account-Driven Numbers Pool Sync + Quota Locking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a bulk sync pull every phone number already registered on a client's Meta WhatsApp Business Account (WABA) into `phone_numbers`, regardless of how many the tenant's subscription allows, and gate *usability* (not visibility) by quota — numbers beyond what's purchased show up locked/blurred and are functionally inert until the client either upgrades or chooses a different primary.

**Architecture:** A new shared pure-function module (`app/services/numbers_pool.py`) computes which numbers are "unlocked" from a tenant's `phone_numbers` rows + pool limit, with no new DB column — the result is recomputed on every read/route decision. Three call sites consume it: `GET /api/v1/numbers/` (display), `PATCH /api/v1/numbers/{id}` (write guard), and `outbound_router.get_best_number()` (live routing exclusion). A new `POST /api/v1/numbers/sync-from-meta` endpoint discovers and imports numbers from Meta's Graph API `{waba_id}/phone_numbers` edge.

**Tech Stack:** FastAPI + Supabase (Python backend, `backend/app/`), Next.js 14 + TypeScript (frontend, `frontend/app/dashboard/numbers/`), Meta Graph API v21.0, pytest (`unittest.TestCase` + `pytest.mark.asyncio`), Vitest (frontend, not used in this plan — no existing test coverage for this page).

## Global Constraints

- No new DB migration — `locked` is computed live from existing `phone_numbers` columns (`role`, `created_at`, `status`) plus the existing `numbers_pool` limit calculation. Never add a stored `locked`/`is_locked` column.
- Locking rule: if a `role="primary"` number exists, it always wins a slot; the remaining `limit - 1` slots go to non-primary numbers oldest-first by `created_at`. If **no** primary exists yet, everything is locked regardless of `limit` — oldest-first only ever fills slots *in addition to* a guaranteed primary slot, never on its own.
- Setting a number as primary (`PATCH` with `role="primary"`) is always allowed on any number, locked or not — it is the unlock mechanism itself.
- Manual single-number `POST /api/v1/numbers` keeps its existing hard 400-at-quota block, completely unchanged.
- Inbound WhatsApp messages are never gated by lock status. Locking only ever excludes a number from being *selected to send from* (`outbound_router.get_best_number()`).
- `backend/app/services/failover.py`'s quality-red auto-promotion (`handle_quality_red`) is unchanged — a locked standby may still be promoted during an outage, and legitimately wins the primary slot once promoted.
- Phone number normalization: strip everything except digits and a leading `+` (e.g. `"+91 98765-43210"` → `"+919876543210"`), so Meta-formatted numbers match our stored format.
- `phone_numbers.messaging_tier` has a DB check constraint allowing only `1000`, `10000`, `100000` — never write an unmapped or `0` value; omit the field from an insert/update instead and let the column default (`1000`) or existing value stand.
- `phone_numbers.quality_rating` has a DB check constraint allowing only `green`, `yellow`, `red` — same rule, omit rather than write an unmapped value.
- `phone_numbers.number` has a global `unique` constraint (not per-tenant).
- Backend tests: `cd backend && pytest`. Frontend verification requires **both** `cd frontend && npm run typecheck` **and** `cd frontend && npm run lint` — CI runs lint and it catches things tsc alone passes (unused imports, `any`).

---

### Task 1: Shared lock-computation + normalization pure functions

**Files:**
- Create: `backend/app/services/numbers_pool.py`
- Test: `backend/tests/test_numbers_pool_locking.py`

**Interfaces:**
- Produces: `normalize_phone_number(raw: str) -> str`, `compute_unlocked_ids(rows: list[dict], limit: int) -> set[str]` — both pure, no DB/FastAPI dependency. Later tasks import both from `app.services.numbers_pool`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_numbers_pool_locking.py`:

```python
"""Pure lock-slot algorithm: primary always wins a slot, remaining slots
fill oldest-first among the rest, and nothing is auto-filled without a
primary present."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.numbers_pool import compute_unlocked_ids, normalize_phone_number


class ComputeUnlockedIdsTests(unittest.TestCase):
    def test_no_primary_locks_everything_regardless_of_limit(self):
        rows = [
            {"id": "a", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "c", "role": "standby", "created_at": "2026-01-03T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=1), set())
        self.assertEqual(compute_unlocked_ids(rows, limit=3), set())

    def test_primary_always_unlocked_even_if_not_oldest(self):
        rows = [
            {"id": "a", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "primary", "created_at": "2026-01-05T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=1), {"b"})

    def test_remaining_slots_fill_oldest_first_among_non_primary(self):
        rows = [
            {"id": "primary", "role": "primary", "created_at": "2026-01-10T00:00:00Z"},
            {"id": "oldest", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "middle", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "newest", "role": "standby", "created_at": "2026-01-03T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=2), {"primary", "oldest"})
        self.assertEqual(compute_unlocked_ids(rows, limit=3), {"primary", "oldest", "middle"})

    def test_limit_zero_locks_everything_including_primary(self):
        rows = [{"id": "a", "role": "primary", "created_at": "2026-01-01T00:00:00Z"}]
        self.assertEqual(compute_unlocked_ids(rows, limit=0), set())

    def test_limit_exceeds_row_count_unlocks_all(self):
        rows = [
            {"id": "a", "role": "primary", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=10), {"a", "b"})


class NormalizePhoneNumberTests(unittest.TestCase):
    def test_strips_spaces_and_dashes_keeps_leading_plus(self):
        self.assertEqual(normalize_phone_number("+91 98765-43210"), "+919876543210")

    def test_no_leading_plus_stays_bare_digits(self):
        self.assertEqual(normalize_phone_number("919876543210"), "919876543210")

    def test_handles_empty_string(self):
        self.assertEqual(normalize_phone_number(""), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_numbers_pool_locking.py -v`
Expected: FAIL (or collection error) — `app.services.numbers_pool` module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/numbers_pool.py`:

```python
import re


def normalize_phone_number(raw: str) -> str:
    """Strip everything except digits and a leading '+', so Meta-formatted
    numbers ("+91 98765-43210") match our stored format ("+919876543210")."""
    raw = (raw or "").strip()
    plus = "+" if raw.startswith("+") else ""
    digits = re.sub(r"\D", "", raw)
    return f"{plus}{digits}"


def compute_unlocked_ids(rows: list[dict], limit: int) -> set[str]:
    """
    Pure lock-slot algorithm, given a tenant's non-archived phone_numbers rows
    (each needs at least "id", "role", "created_at") and their numbers_pool
    limit.

    - role="primary" always wins a slot, regardless of age.
    - Remaining (limit - 1) slots go to non-primary rows, oldest `created_at`
      first.
    - If no primary exists yet, nothing is unlocked -- oldest-first only ever
      fills slots *in addition to* a guaranteed primary slot, it never
      operates without one. This matters for a brand-new tenant's first Meta
      sync: several numbers can land at once with no primary chosen yet, and
      none of them should be auto-activated by arbitrary sync-batch order --
      the client must explicitly choose one.
    """
    if limit <= 0:
        return set()

    primary = next((r for r in rows if r.get("role") == "primary"), None)
    if primary is None:
        return set()

    unlocked = {primary["id"]}
    others = sorted(
        (r for r in rows if r.get("id") != primary.get("id")),
        key=lambda r: r.get("created_at") or "",
    )
    for r in others[: max(limit - 1, 0)]:
        unlocked.add(r["id"])
    return unlocked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_numbers_pool_locking.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/numbers_pool.py backend/tests/test_numbers_pool_locking.py
git commit -m "feat: add pure numbers-pool lock-slot algorithm"
```

---

### Task 2: DB-backed lock lookup + move numbers_pool_limit into the shared module

**Files:**
- Modify: `backend/app/services/numbers_pool.py`
- Modify: `backend/app/routes/numbers.py:1-44` (imports + delete `_numbers_pool_limit`)
- Test: `backend/tests/test_numbers_pool_locking.py` (append)
- Existing regression test: `backend/tests/test_numbers_pool_enforcement.py` (must still pass unchanged)

**Interfaces:**
- Consumes: `compute_unlocked_ids` from Task 1.
- Produces: `numbers_pool_limit(db, tenant_id: str) -> int`, `get_unlocked_number_ids(db, tenant_id: str) -> set[str]`. Tasks 3, 4, 6, 7 import both from `app.services.numbers_pool`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_numbers_pool_locking.py` (add these imports at top alongside the existing ones: `from unittest.mock import MagicMock` and `from app.services.numbers_pool import get_unlocked_number_ids, numbers_pool_limit`):

```python
class GetUnlockedNumberIdsTests(unittest.TestCase):
    def _mock_db(self, rows, purchased_quantity=0, has_messaging_module=True):
        db = MagicMock()
        items_tbl = MagicMock()
        entitlement_items = []
        if has_messaging_module:
            entitlement_items.append({"feature_key": "outbound_messaging", "quantity": 1})
        if purchased_quantity:
            entitlement_items.append({"feature_key": "numbers_pool", "quantity": purchased_quantity})
        items_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=entitlement_items)
        items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"quantity": purchased_quantity}] if purchased_quantity else []
        )
        catalog_tbl = MagicMock()
        catalog_tbl.select.return_value.execute.return_value = MagicMock(data=[])

        numbers_tbl = MagicMock()
        numbers_tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=rows)

        def table(name):
            return {
                "tenant_subscription_items": items_tbl,
                "feature_catalog": catalog_tbl,
                "phone_numbers": numbers_tbl,
            }[name]
        db.table.side_effect = table
        return db

    def test_returns_primary_plus_oldest_non_primary_within_limit(self):
        rows = [
            {"id": "primary", "role": "primary", "created_at": "2026-01-10T00:00:00Z"},
            {"id": "oldest", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "newest", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
        ]
        db = self._mock_db(rows, purchased_quantity=1, has_messaging_module=True)
        self.assertEqual(get_unlocked_number_ids(db, "tenant-1"), {"primary", "oldest"})

    def test_no_messaging_module_no_purchase_locks_everything(self):
        rows = [{"id": "a", "role": "primary", "created_at": "2026-01-01T00:00:00Z"}]
        db = self._mock_db(rows, purchased_quantity=0, has_messaging_module=False)
        self.assertEqual(get_unlocked_number_ids(db, "tenant-1"), set())


class NumbersPoolLimitMovedTests(unittest.TestCase):
    def test_numbers_pool_limit_importable_from_shared_module(self):
        db = MagicMock()
        items_tbl = MagicMock()
        items_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"feature_key": "outbound_messaging", "quantity": 1}]
        )
        items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        catalog_tbl = MagicMock()
        catalog_tbl.select.return_value.execute.return_value = MagicMock(data=[])

        def table(name):
            return {"tenant_subscription_items": items_tbl, "feature_catalog": catalog_tbl}[name]
        db.table.side_effect = table

        self.assertEqual(numbers_pool_limit(db, "tenant-1"), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_numbers_pool_locking.py -v`
Expected: FAIL — `get_unlocked_number_ids` and `numbers_pool_limit` don't exist in `numbers_pool.py` yet.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/numbers_pool.py` (add `from app.services.entitlements import get_purchased_quantity, resolve_entitlements` to the top of the file):

```python
def numbers_pool_limit(db, tenant_id: str) -> int:
    """
    Purchasing Inbound or Outbound (WhatsApp) messaging includes 1 free
    phone number -- that's the messaging module's whole point, not an
    add-on. Anything beyond that free number is an explicit paid top-up via
    `tenant_subscription_items` (feature_key='numbers_pool'). A tenant with
    no messaging module purchased at all gets 0.
    """
    ent = resolve_entitlements(db, tenant_id)
    features = set(ent.get("features") or [])
    baseline = 1 if ("inbound_messaging" in features or "outbound_messaging" in features) else 0
    return baseline + get_purchased_quantity(db, tenant_id, "numbers_pool")


def get_unlocked_number_ids(db, tenant_id: str) -> set[str]:
    """DB-backed wrapper around compute_unlocked_ids -- fetches the tenant's
    non-archived phone_numbers and current numbers_pool limit, and returns the
    set of ids allowed to be active/primary/unpaused right now."""
    limit = numbers_pool_limit(db, tenant_id)
    rows = (
        db.table("phone_numbers")
        .select("id,role,created_at")
        .eq("tenant_id", tenant_id)
        .neq("status", "archived")
        .execute()
        .data
        or []
    )
    return compute_unlocked_ids(rows, limit)
```

Now update `backend/app/routes/numbers.py`. Replace the top of the file:

```python
import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.entitlements import get_purchased_quantity, resolve_entitlements
from app.services.meta_cloud import get_number_quality
```

with:

```python
import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.meta_cloud import get_number_quality, list_waba_phone_numbers
from app.services.numbers_pool import (
    get_unlocked_number_ids,
    normalize_phone_number,
    numbers_pool_limit,
)
```

(`list_waba_phone_numbers` is added in Task 5 — this import will fail until then, so **do this rename/import edit together with Task 5's `meta_cloud.py` change**, not before. For this task, use this intermediate import instead, without `list_waba_phone_numbers`:)

```python
import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.meta_cloud import get_number_quality
from app.services.numbers_pool import get_unlocked_number_ids, numbers_pool_limit
```

Then replace the `_numbers_pool_limit` function:

```python
def _numbers_pool_limit(db, tenant_id: str) -> int:
    """
    Purchasing Inbound or Outbound (WhatsApp) messaging includes 1 free
    phone number -- that's the messaging module's whole point, not an
    add-on. Anything beyond that free number is an explicit paid top-up via
    `tenant_subscription_items` (feature_key='numbers_pool'). A tenant with
    no messaging module purchased at all gets 0.
    """
    ent = resolve_entitlements(db, tenant_id)
    features = set(ent.get("features") or [])
    baseline = 1 if ("inbound_messaging" in features or "outbound_messaging" in features) else 0
    return baseline + get_purchased_quantity(db, tenant_id, "numbers_pool")
```

with a thin alias so the rest of the file (which calls `_numbers_pool_limit(...)` in `list_phone_numbers` and `create_phone_number`) doesn't need touching in this task:

```python
_numbers_pool_limit = numbers_pool_limit
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_numbers_pool_locking.py tests/test_numbers_pool_enforcement.py -v`
Expected: PASS — new tests pass, and `test_numbers_pool_enforcement.py` (existing, unmodified) still passes since `_numbers_pool_limit` behaves identically.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/numbers_pool.py backend/app/routes/numbers.py backend/tests/test_numbers_pool_locking.py
git commit -m "refactor: move numbers_pool_limit into shared module, add get_unlocked_number_ids"
```

---

### Task 3: `GET /api/v1/numbers/` reports `locked` per row

**Files:**
- Modify: `backend/app/routes/numbers.py:47-62`
- Test: `backend/tests/test_numbers_locking_routes.py`

**Interfaces:**
- Consumes: `get_unlocked_number_ids`, `numbers_pool_limit` (Task 2).
- Produces: `GET /api/v1/numbers/` response `data[i].locked: bool`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_numbers_locking_routes.py`:

```python
"""GET /numbers/ marks over-quota rows as locked; PATCH enforces the lock."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


class NumbersLockingGetTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.get_supabase")
    def test_list_marks_over_quota_numbers_locked(self, mock_get_db, mock_limit, mock_unlocked):
        db = MagicMock()
        rows = [
            {"id": "a", "role": "primary", "status": "active", "quality_rating": "green"},
            {"id": "b", "role": "standby", "status": "warming", "quality_rating": "green"},
        ]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(data=rows)
        mock_get_db.return_value = db
        mock_limit.return_value = 1
        mock_unlocked.return_value = {"a"}

        res = self.client.get("/api/v1/numbers/")
        self.assertEqual(res.status_code, 200)
        by_id = {n["id"]: n for n in res.json()["data"]}
        self.assertFalse(by_id["a"]["locked"])
        self.assertTrue(by_id["b"]["locked"])

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.get_supabase")
    def test_archived_numbers_never_locked(self, mock_get_db, mock_limit, mock_unlocked):
        db = MagicMock()
        rows = [{"id": "c", "role": "standby", "status": "archived", "quality_rating": "green"}]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(data=rows)
        mock_get_db.return_value = db
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.get("/api/v1/numbers/")
        self.assertFalse(res.json()["data"][0]["locked"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_numbers_locking_routes.py -v`
Expected: FAIL — `KeyError: 'locked'`, the field doesn't exist in the response yet.

- [ ] **Step 3: Write minimal implementation**

Replace `list_phone_numbers` in `backend/app/routes/numbers.py`:

```python
@router.get("/")
async def list_phone_numbers(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("role")
        .order("quality_rating")
        .execute()
    )
    rows = result.data or []
    numbers_limit = numbers_pool_limit(db, tenant_id)
    unlocked_ids = get_unlocked_number_ids(db, tenant_id)
    data = [
        {**row, "locked": row.get("status") != "archived" and row["id"] not in unlocked_ids}
        for row in rows
    ]
    return {
        "data": data,
        "numbers_pool": {"limit": numbers_limit, "used": len(rows)},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_numbers_locking_routes.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full existing numbers suite to check for regressions**

Run: `cd backend && pytest tests/test_numbers_pool_enforcement.py -v`
Expected: PASS unchanged (this task didn't touch `create_phone_number`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/numbers.py backend/tests/test_numbers_locking_routes.py
git commit -m "feat: report locked status per number in GET /api/v1/numbers/"
```

---

### Task 4: `PATCH /{number_id}` blocks activating a locked number

**Files:**
- Modify: `backend/app/routes/numbers.py:99-128`
- Test: `backend/tests/test_numbers_locking_routes.py` (append)

**Interfaces:**
- Consumes: `get_unlocked_number_ids` (Task 2).
- Produces: `PATCH /api/v1/numbers/{id}` 400s when `status="active"` or `paused_outbound=false` targets a currently-locked number, unless the same request also sets `role="primary"`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_numbers_locking_routes.py` (new class, same file):

```python
class NumbersLockingPatchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_blocks_activating_locked_number(self, mock_get_db, mock_unlocked):
        mock_get_db.return_value = MagicMock()
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"status": "active"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("locked", res.json()["detail"].lower())

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_blocks_resuming_locked_number(self, mock_get_db, mock_unlocked):
        mock_get_db.return_value = MagicMock()
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"paused_outbound": False},
        )
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_pausing_a_locked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "paused_outbound": True}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"paused_outbound": True},
        )
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_setting_locked_number_as_primary(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "role": "primary"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()  # currently locked -- Set Primary is the unlock action

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"role": "primary"},
        )
        self.assertEqual(res.status_code, 200)
        mock_unlocked.assert_not_called()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_rename_on_locked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "display_name": "New Name"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"display_name": "New Name"},
        )
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_activating_an_unlocked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "00000000-0000-0000-0000-000000000001", "status": "active"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = {"00000000-0000-0000-0000-000000000001"}

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"status": "active"},
        )
        self.assertEqual(res.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_numbers_locking_routes.py -v`
Expected: FAIL on the new locking-guard tests (the block/allow behavior doesn't exist yet — `test_blocks_activating_locked_number` and `test_blocks_resuming_locked_number` will currently return 200 instead of 400).

- [ ] **Step 3: Write minimal implementation**

Replace `update_phone_number` in `backend/app/routes/numbers.py`:

```python
@router.patch("/{number_id}")
async def update_phone_number(
    number_id: UUID,
    payload: UpdatePhoneNumber,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    db = get_supabase()
    updates = {}
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.status is not None:
        updates["status"] = payload.status
    if payload.display_name is not None:
        updates["display_name"] = payload.display_name.strip()
    if payload.paused_outbound is not None:
        updates["paused_outbound"] = payload.paused_outbound
    if payload.warm_up_day is not None:
        updates["warm_up_day"] = payload.warm_up_day
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Setting role="primary" is always allowed -- it's the unlock mechanism
    # itself (the primary slot is always guaranteed). Any other attempt to
    # activate a currently-locked number (flip to active, or resume outbound)
    # is blocked until the client either sets it primary or upgrades.
    attempting_activation = payload.status == "active" or payload.paused_outbound is False
    if attempting_activation and payload.role != "primary":
        unlocked_ids = get_unlocked_number_ids(db, tenant_id)
        if str(number_id) not in unlocked_ids:
            raise HTTPException(
                status_code=400,
                detail="This number is locked by your numbers pool quota. Set it as primary or upgrade in Subscriptions to activate it.",
            )

    if payload.role == "primary":
        # Ensure exclusive primary logic: demote all other primary numbers to standby
        db.table("phone_numbers").update({"role": "standby"}).eq("tenant_id", tenant_id).eq("role", "primary").execute()

    result = db.table("phone_numbers").update(updates).eq("id", str(number_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Phone number not found")
    return result.data[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_numbers_locking_routes.py -v`
Expected: PASS (8 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/numbers.py backend/tests/test_numbers_locking_routes.py
git commit -m "feat: block activating/resuming a locked number via PATCH"
```

---

### Task 5: `meta_cloud.list_waba_phone_numbers` — fetch a WABA's registered numbers

**Files:**
- Modify: `backend/app/services/meta_cloud.py` (add function after `list_all_templates`, around line 876)
- Modify: `backend/app/routes/numbers.py` (finish the import swap started in Task 2)
- Test: `backend/tests/test_meta_cloud_list_waba_phone_numbers.py`

**Interfaces:**
- Produces: `async def list_waba_phone_numbers(waba_id: str, access_token: Optional[str] = None, tenant_id: Optional[str] = None) -> list[dict]` — each dict has whatever fields Meta returns for `fields=id,display_phone_number,verified_name,quality_rating,messaging_limit_tier`. Task 6 imports and calls this.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_meta_cloud_list_waba_phone_numbers.py`:

```python
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.meta_cloud import list_waba_phone_numbers


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_single_page():
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {
        "data": [
            {
                "id": "111",
                "display_phone_number": "+1 555-0100",
                "verified_name": "Aira Main",
                "quality_rating": "GREEN",
                "messaging_limit_tier": "TIER_1000",
            },
        ],
        "paging": {},
    }
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert len(result) == 1
    assert result[0]["id"] == "111"
    assert result[0]["display_phone_number"] == "+1 555-0100"


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_paginates():
    page1 = MagicMock()
    page1.is_success = True
    page1.json.return_value = {
        "data": [{"id": "111", "display_phone_number": "+15550100"}],
        "paging": {"next": "https://graph.facebook.com/v21.0/waba-1/phone_numbers?after=CURSOR"},
    }
    page2 = MagicMock()
    page2.is_success = True
    page2.json.return_value = {
        "data": [{"id": "222", "display_phone_number": "+15550200"}],
        "paging": {},
    }
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[page1, page2])
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert [n["id"] for n in result] == ["111", "222"]


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_stops_on_meta_error():
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 400
    mock_response.text = '{"error": {"message": "Invalid waba"}}'
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert result == []


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meta_cloud_list_waba_phone_numbers.py -v`
Expected: FAIL — `ImportError: cannot import name 'list_waba_phone_numbers'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/meta_cloud.py`, add this function immediately after `list_all_templates` (which ends around line 876, right before `async def delete_template_from_meta`):

```python
async def list_waba_phone_numbers(
    waba_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """
    Fetch every phone number registered on a WABA, handling pagination.
    Returns Meta's raw phone-number dicts (id, display_phone_number,
    verified_name, quality_rating, messaging_limit_tier).
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/phone_numbers"
    params = {
        "fields": "id,display_phone_number,verified_name,quality_rating,messaging_limit_tier",
        "limit": 100,
    }
    numbers: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {tok}"})
            if not resp.is_success:
                logger.error("list_waba_phone_numbers failed: %s %s", resp.status_code, resp.text)
                break
            body = resp.json()
            numbers.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            url = next_url  # type: ignore[assignment]
            params = {}  # params are embedded in next_url cursor

    return numbers
```

Now finish the import swap in `backend/app/routes/numbers.py` (started in Task 2). Replace:

```python
from app.services.meta_cloud import get_number_quality
from app.services.numbers_pool import get_unlocked_number_ids, numbers_pool_limit
```

with:

```python
from app.config_dynamic import get_setting
from app.services.meta_cloud import get_number_quality, list_waba_phone_numbers
from app.services.numbers_pool import (
    get_unlocked_number_ids,
    normalize_phone_number,
    numbers_pool_limit,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meta_cloud_list_waba_phone_numbers.py tests/test_numbers_locking_routes.py tests/test_numbers_pool_enforcement.py -v`
Expected: PASS across all three files (the numbers.py import change must not break the earlier tasks' passing tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_cloud.py backend/app/routes/numbers.py backend/tests/test_meta_cloud_list_waba_phone_numbers.py
git commit -m "feat: add meta_cloud.list_waba_phone_numbers"
```

---

### Task 6: `POST /api/v1/numbers/sync-from-meta` — bulk discovery + refresh

**Files:**
- Modify: `backend/app/routes/numbers.py` (add route + `_QUALITY_MAP`/`_TIER_MAP`/`_WARM_UP_MAX` already exist at module level, defined just above `sync_number_from_meta`)
- Test: `backend/tests/test_numbers_sync_from_meta.py`

**Interfaces:**
- Consumes: `list_waba_phone_numbers` (Task 5), `get_unlocked_number_ids`, `normalize_phone_number` (Task 2/1), `get_setting` (`app.config_dynamic`).
- Produces: `POST /api/v1/numbers/sync-from-meta` → same response shape as `GET /`, plus `synced: int` and `failed: int`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_numbers_sync_from_meta.py`:

```python
"""POST /api/v1/numbers/sync-from-meta discovers every number on the tenant's
Meta WABA, inserting ones we don't have yet (always as standby/warming --
never auto-primary) and refreshing quality/tier on ones we do."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


def _mock_numbers_db(initial_rows):
    """Minimal Supabase mock for phone_numbers + incidents, backed by a
    mutable in-memory list so inserts/updates during a sync are reflected in
    later reads within the same test."""
    db = MagicMock()
    state = {"rows": [dict(r) for r in initial_rows]}
    next_id = {"n": 1}

    numbers_tbl = MagicMock()

    select_node = MagicMock()
    select_node.execute.side_effect = lambda: MagicMock(data=list(state["rows"]))
    select_node.order.return_value.order.return_value.execute.side_effect = (
        lambda: MagicMock(data=list(state["rows"]))
    )
    numbers_tbl.select.return_value.eq.return_value = select_node

    def do_insert(payload):
        row = dict(payload)
        row.setdefault("id", f"new-{next_id['n']}")
        row.setdefault("created_at", f"2026-02-{next_id['n']:02d}T00:00:00Z")
        row.setdefault("quality_rating", "green")
        row.setdefault("messaging_tier", 1000)
        next_id["n"] += 1
        state["rows"].append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[row])
        return m
    numbers_tbl.insert.side_effect = do_insert

    def do_update(payload):
        m = MagicMock()

        def eq_id(_field, value):
            m2 = MagicMock()

            def eq_tenant(_field2, _value2):
                m3 = MagicMock()

                def execute():
                    matched = [r for r in state["rows"] if r["id"] == value]
                    for r in matched:
                        r.update(payload)
                    return MagicMock(data=matched)
                m3.execute.side_effect = execute
                return m3
            m2.eq.side_effect = eq_tenant
            return m2
        m.eq.side_effect = eq_id
        return m
    numbers_tbl.update.side_effect = do_update

    incidents_tbl = MagicMock()
    incidents_tbl.insert.return_value.execute.return_value = MagicMock(data=[])

    def table(name):
        return {"phone_numbers": numbers_tbl, "incidents": incidents_tbl}[name]
    db.table.side_effect = table
    db._state = state
    return db


class SyncFromMetaTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_missing_waba_id_returns_400(self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked):
        mock_get_db.return_value = _mock_numbers_db([])
        mock_get_setting.return_value = None

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 400)
        mock_list.assert_not_called()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_fresh_tenant_imports_all_as_standby_and_locked(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        db = _mock_numbers_db([])
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+91 98765-00001", "verified_name": "Number 1",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
            {"id": "meta-2", "display_phone_number": "+91 98765-00002", "verified_name": "Number 2",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
            {"id": "meta-3", "display_phone_number": "+91 98765-00003", "verified_name": "Number 3",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()  # no primary yet -- everything locked

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["synced"], 3)
        self.assertEqual(body["failed"], 0)
        self.assertEqual(len(body["data"]), 3)
        for row in body["data"]:
            self.assertEqual(row["role"], "standby")
            self.assertEqual(row["status"], "warming")
            self.assertTrue(row["locked"])
        numbers = {r["number"] for r in db._state["rows"]}
        self.assertEqual(numbers, {"+919876500001", "+919876500002", "+919876500003"})

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_matches_existing_row_by_meta_id_and_refreshes_quality(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        existing = [{
            "id": "row-1", "number": "+919876500001", "display_name": "Number 1",
            "role": "primary", "status": "active", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 14, "meta_phone_number_id": "meta-1",
            "created_at": "2026-01-01T00:00:00Z", "last_reset_at": "2026-01-01T00:00:00Z",
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+919876500001", "verified_name": "Number 1",
             "quality_rating": "YELLOW", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = {"row-1"}

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["synced"], 1)
        updated_row = next(r for r in db._state["rows"] if r["id"] == "row-1")
        self.assertEqual(updated_row["quality_rating"], "yellow")
        self.assertEqual(len(db._state["rows"]), 1)  # no duplicate inserted

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_matches_existing_row_by_normalized_number_and_backfills_meta_id(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        existing = [{
            "id": "row-1", "number": "+919876500001", "display_name": "Manually Added",
            "role": "standby", "status": "warming", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 0, "meta_phone_number_id": None,
            "created_at": "2026-01-01T00:00:00Z", "last_reset_at": None,
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+91 98765 00001", "verified_name": "Number 1",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(db._state["rows"]), 1)  # matched, not duplicated
        self.assertEqual(db._state["rows"][0]["meta_phone_number_id"], "meta-1")

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_locked_existing_row_never_promoted_to_active_by_warmup(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        from datetime import datetime, timedelta, timezone
        old_reset = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        existing = [{
            "id": "row-2", "number": "+919876500002", "display_name": "Second Number",
            "role": "standby", "status": "warming", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 1, "meta_phone_number_id": "meta-2",
            "created_at": "2026-01-02T00:00:00Z", "last_reset_at": old_reset,
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-2", "display_phone_number": "+919876500002", "verified_name": "Second Number",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()  # row-2 is locked (not primary, over quota)

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        updated_row = next(r for r in db._state["rows"] if r["id"] == "row-2")
        self.assertGreaterEqual(updated_row["warm_up_day"], 14)  # still accrues warm-up day
        self.assertEqual(updated_row["status"], "warming")  # but never promoted to active

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_one_bad_number_does_not_abort_the_whole_sync(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        db = _mock_numbers_db([])
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": None, "display_phone_number": "bad"},  # no usable id -- should be skipped/counted as failed
            {"id": "meta-9", "display_phone_number": "+919876509999", "verified_name": "Good Number",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["synced"], 1)
        self.assertEqual(body["failed"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_numbers_sync_from_meta.py -v`
Expected: FAIL — `404 Not Found`, the route doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

Add this route to `backend/app/routes/numbers.py`, placed after `create_phone_number` and before `update_phone_number`:

```python
@router.post("/sync-from-meta")
async def sync_all_numbers_from_meta(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    """Pull every number registered on the tenant's Meta WABA into
    phone_numbers -- regardless of numbers_pool quota. Numbers beyond quota
    land locked (role=standby, never auto-primary), not rejected."""
    db = get_supabase()
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        raise HTTPException(status_code=400, detail="Connect Meta WhatsApp (meta_waba_id) in Settings first")

    meta_numbers = await list_waba_phone_numbers(waba_id=waba_id, tenant_id=tenant_id)

    existing_rows = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .execute()
        .data
        or []
    )
    by_meta_id = {r["meta_phone_number_id"]: r for r in existing_rows if r.get("meta_phone_number_id")}
    by_number = {r["number"]: r for r in existing_rows if r.get("number")}

    # Snapshot lock state *before* this sync's inserts/updates -- used only to
    # decide whether an existing row's warm-up may promote it to "active".
    # Newly-inserted rows never attempt promotion (they start at day 0), so
    # this snapshot doesn't need to account for numbers this same sync adds.
    unlocked_before = get_unlocked_number_ids(db, tenant_id)

    now = datetime.now(timezone.utc)
    synced = 0
    failed = 0

    for meta_num in meta_numbers:
        try:
            meta_pid = meta_num.get("id")
            if not meta_pid:
                failed += 1
                continue

            raw_quality = (meta_num.get("quality_rating") or "").upper()
            quality = _QUALITY_MAP.get(raw_quality)
            tier = _TIER_MAP.get(meta_num.get("messaging_limit_tier") or "")
            display_number = normalize_phone_number(meta_num.get("display_phone_number") or "")

            row = by_meta_id.get(meta_pid) or (by_number.get(display_number) if display_number else None)

            if row is None:
                insert_data: dict = {
                    "provider": "meta_cloud",
                    "number": display_number or meta_pid,
                    "display_name": meta_num.get("verified_name") or display_number or meta_pid,
                    "role": "standby",
                    "status": "warming",
                    "warm_up_day": 0,
                    "paused_outbound": False,
                    "meta_phone_number_id": meta_pid,
                    "tenant_id": tenant_id,
                }
                if quality:
                    insert_data["quality_rating"] = quality
                if tier:
                    insert_data["messaging_tier"] = tier
                inserted = db.table("phone_numbers").insert(insert_data).execute()
                new_row = inserted.data[0]
                existing_rows.append(new_row)
                by_meta_id[meta_pid] = new_row
                if display_number:
                    by_number[display_number] = new_row
                synced += 1
                continue

            updates: dict = {"daily_send_count": 0, "last_reset_at": now.isoformat()}
            if quality:
                updates["quality_rating"] = quality
            if tier:
                updates["messaging_tier"] = tier
            if not row.get("meta_phone_number_id"):
                updates["meta_phone_number_id"] = meta_pid

            last_reset_raw = row.get("last_reset_at")
            days_elapsed = 0
            if last_reset_raw:
                last_reset = datetime.fromisoformat(last_reset_raw.replace("Z", "+00:00"))
                days_elapsed = max(0, (now - last_reset).days)

            locked = row["id"] not in unlocked_before
            if row["status"] == "warming" and days_elapsed > 0:
                new_day = min(row["warm_up_day"] + days_elapsed, _WARM_UP_MAX)
                updates["warm_up_day"] = new_day
                if new_day >= _WARM_UP_MAX and not locked:
                    updates["status"] = "active"

            db.table("phone_numbers").update(updates).eq("id", row["id"]).eq("tenant_id", tenant_id).execute()

            old_quality = row.get("quality_rating", "green")
            new_quality = updates.get("quality_rating", old_quality)
            if new_quality != old_quality:
                incident_type = "quality_yellow" if new_quality == "yellow" else "quality_red" if new_quality == "red" else None
                if incident_type:
                    db.table("incidents").insert({
                        "type": incident_type,
                        "phone_number_id": row["id"],
                        "tenant_id": tenant_id,
                        "detail": {
                            "number": row.get("number"),
                            "display_name": row.get("display_name"),
                            "old_quality": old_quality,
                            "new_quality": new_quality,
                            "source": "bulk_meta_sync",
                        },
                    }).execute()
            synced += 1
        except Exception:
            logger.exception("sync-from-meta: failed to process one Meta number for tenant %s", tenant_id)
            failed += 1

    result = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("role")
        .order("quality_rating")
        .execute()
    )
    rows = result.data or []
    numbers_limit = numbers_pool_limit(db, tenant_id)
    unlocked_after = get_unlocked_number_ids(db, tenant_id)
    data = [
        {**r, "locked": r.get("status") != "archived" and r["id"] not in unlocked_after}
        for r in rows
    ]
    return {
        "data": data,
        "numbers_pool": {"limit": numbers_limit, "used": len(rows)},
        "synced": synced,
        "failed": failed,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_numbers_sync_from_meta.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full numbers test surface for regressions**

Run: `cd backend && pytest tests/test_numbers_sync_from_meta.py tests/test_numbers_locking_routes.py tests/test_numbers_pool_enforcement.py tests/test_meta_cloud_list_waba_phone_numbers.py tests/test_numbers_pool_locking.py -v`
Expected: PASS across all five files.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/numbers.py backend/tests/test_numbers_sync_from_meta.py
git commit -m "feat: add POST /api/v1/numbers/sync-from-meta bulk discovery endpoint"
```

---

### Task 7: `outbound_router.get_best_number()` excludes locked numbers live

**Files:**
- Modify: `backend/app/services/outbound_router.py:1-64`
- Test: `backend/tests/test_outbound_router_locking.py`

**Interfaces:**
- Consumes: `get_unlocked_number_ids` (Task 2).
- Produces: `get_best_number(tenant_id)` never returns a locked number, even if it otherwise meets every routing criterion. This is what makes a subscription downgrade take effect immediately, on the very next send.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_outbound_router_locking.py`:

```python
"""get_best_number() must never select a number that's over the tenant's
numbers_pool quota, even if it's status=active/unpaused/warmed-up -- this is
what makes a subscription downgrade take effect immediately, without waiting
for a manual re-sync or any write to the number's own row."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.outbound_router import get_best_number


def _candidate(id_, **overrides):
    row = {
        "id": id_, "quality_rating": "green", "messaging_tier": 1000,
        "daily_send_count": 0, "warm_up_day": 14, "status": "active",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_excludes_locked_candidate_even_if_otherwise_eligible():
    db = MagicMock()
    rows = [_candidate("locked-1"), _candidate("unlocked-1")]
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.gte.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)

    with patch("app.services.outbound_router.get_supabase", return_value=db), \
         patch("app.services.outbound_router.get_unlocked_number_ids", return_value={"unlocked-1"}):
        best = await get_best_number("tenant-1")

    assert best is not None
    assert best["id"] == "unlocked-1"


@pytest.mark.asyncio
async def test_returns_none_when_every_candidate_is_locked():
    db = MagicMock()
    rows = [_candidate("locked-1")]
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.gte.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)

    with patch("app.services.outbound_router.get_supabase", return_value=db), \
         patch("app.services.outbound_router.get_unlocked_number_ids", return_value=set()):
        best = await get_best_number("tenant-1")

    assert best is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_outbound_router_locking.py -v`
Expected: FAIL — `test_excludes_locked_candidate_even_if_otherwise_eligible` picks `locked-1` (first sorted, both otherwise identical) instead of returning `unlocked-1`, since no filter exists yet.

- [ ] **Step 3: Write minimal implementation**

Replace the top of `backend/app/services/outbound_router.py`:

```python
import logging

from app.db.supabase import get_supabase
from app.services.numbers_pool import get_unlocked_number_ids

logger = logging.getLogger(__name__)
```

Replace `get_best_number`:

```python
async def get_best_number(tenant_id: str) -> dict | None:
    db = get_supabase()
    rows = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .neq("quality_rating", "red")
        .gte("warm_up_day", 14)
        .eq("paused_outbound", False)
        .execute()
        .data
        or []
    )
    if not rows:
        logger.warning("No healthy outbound numbers available")
        return None

    unlocked_ids = get_unlocked_number_ids(db, tenant_id)
    rows = [r for r in rows if r["id"] in unlocked_ids]
    if not rows:
        logger.warning("All outbound numbers are locked by the numbers pool quota")
        return None

    def _sort_key(row: dict) -> tuple:
        # green before yellow (alphabetically, "green" < "yellow")
        quality_rank = 0 if row.get("quality_rating", "").lower() == "green" else 1
        tier = row.get("messaging_tier") or 1000
        ratio = (row.get("daily_send_count") or 0) / tier
        return (quality_rank, ratio)

    rows = [
        r for r in rows
        if (r.get("daily_send_count") or 0) < _TIER_DAILY_LIMITS.get(r.get("messaging_tier") or 1000, 1_000)
    ]
    if not rows:
        logger.warning("All outbound numbers have hit their daily tier limit")
        return None

    rows = [
        r for r in rows
        if r.get("status") != "warming" or (r.get("daily_send_count") or 0) < _warmup_daily_cap(r.get("warm_up_day") or 0)
    ]
    if not rows:
        logger.warning("All outbound numbers have hit their daily warm-up cap")
        return None

    rows.sort(key=_sort_key)
    return rows[0]
```

(Everything below the lock filter is the existing logic, unchanged — only the new `unlocked_ids` filter block is inserted right after the initial empty-check.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_outbound_router_locking.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full backend suite for regressions**

Run: `cd backend && pytest -v`
Expected: PASS across the whole suite (no pre-existing test patches `app.services.outbound_router.get_unlocked_number_ids` or relies on `get_best_number` selecting a specific one of two otherwise-identical candidates, so this filter shouldn't break anything else — confirm by reading any failure closely if one appears).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/outbound_router.py backend/tests/test_outbound_router_locking.py
git commit -m "feat: exclude numbers-pool-locked numbers from outbound routing live"
```

---

### Task 8: Frontend — locked/blurred number cards + bulk sync rewire

**Files:**
- Modify: `frontend/app/dashboard/numbers/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/numbers/` and `POST /api/v1/numbers/sync-from-meta` response shape from Tasks 3 and 6 (`data[i].locked: boolean`, plus `synced`/`failed` on the sync response).

- [ ] **Step 1: Add `locked` to the `PhoneNumber` type**

In `frontend/app/dashboard/numbers/page.tsx`, replace:

```ts
type PhoneNumber = {
  id: string;
  provider: "meta_cloud";
  number: string;
  display_name: string;
  role: "primary" | "standby" | "archived";
  status: "active" | "warming" | "restricted" | "archived";
  quality_rating: "green" | "yellow" | "red";
  messaging_tier: number;
  daily_send_count: number;
  warm_up_day: number;
  paused_outbound: boolean;
  meta_phone_number_id?: string | null;
  created_at: string;
};
```

with:

```ts
type PhoneNumber = {
  id: string;
  provider: "meta_cloud";
  number: string;
  display_name: string;
  role: "primary" | "standby" | "archived";
  status: "active" | "warming" | "restricted" | "archived";
  quality_rating: "green" | "yellow" | "red";
  messaging_tier: number;
  daily_send_count: number;
  warm_up_day: number;
  paused_outbound: boolean;
  meta_phone_number_id?: string | null;
  created_at: string;
  locked: boolean;
};
```

- [ ] **Step 2: Add the `Lock` icon import**

Replace:

```ts
import { Plus, X, Pencil, Check, Trash2, PauseCircle, PlayCircle, Star, RefreshCw, Info, ChevronDown, ChevronUp, ChevronRight } from "lucide-react";
```

with:

```ts
import { Plus, X, Pencil, Check, Trash2, PauseCircle, PlayCircle, Star, RefreshCw, Info, ChevronDown, ChevronUp, ChevronRight, Lock } from "lucide-react";
```

- [ ] **Step 3: Rewire `numbersApi` to call the new bulk endpoint**

Replace:

```ts
  syncMeta: (id: string) =>
    apiFetch<PhoneNumber>(`/api/v1/numbers/${id}/sync-meta`, { method: "POST" }),
};
```

with:

```ts
  syncMeta: (id: string) =>
    apiFetch<PhoneNumber>(`/api/v1/numbers/${id}/sync-meta`, { method: "POST" }),
  syncFromMeta: () =>
    apiFetch<{ data: PhoneNumber[]; numbers_pool?: { limit: number; used: number }; synced: number; failed: number }>(
      "/api/v1/numbers/sync-from-meta",
      { method: "POST" }
    ),
};
```

- [ ] **Step 4: Rewrite `handleSyncAllMeta` to call it once instead of looping**

Replace:

```ts
  async function handleSyncAllMeta() {
    if (!canManageNumbers) return;
    const configuredNumbers = numbers.filter((n) => n.meta_phone_number_id && n.status !== "archived");
    if (configuredNumbers.length === 0) {
      toast.error("No configured numbers to sync");
      return;
    }
    setSyncingAll(true);
    let successCount = 0;
    let failCount = 0;

    await Promise.all(
      configuredNumbers.map(async (num) => {
        try {
          await numbersApi.syncMeta(num.id);
          successCount++;
        } catch (err) {
          console.error(`Failed to sync number ${num.number}:`, err);
          failCount++;
        }
      })
    );

    await reload();
    setSyncingAll(false);

    if (failCount === 0) {
      toast.success(`Successfully synced ${successCount} numbers from Meta`);
    } else if (successCount > 0) {
      toast.success(`Synced ${successCount} numbers, ${failCount} failed`);
    } else {
      toast.error("Failed to sync numbers from Meta");
    }
  }
```

with:

```ts
  async function handleSyncAllMeta() {
    if (!canManageNumbers) return;
    setSyncingAll(true);
    try {
      const res = await numbersApi.syncFromMeta();
      setNumbers(res.data ?? []);
      setNumbersPool(res.numbers_pool ?? null);
      if (res.failed === 0) {
        toast.success(`Synced ${res.synced} number${res.synced === 1 ? "" : "s"} from Meta`);
      } else if (res.synced > 0) {
        toast.success(`Synced ${res.synced} numbers, ${res.failed} failed`);
      } else {
        toast.error("Failed to sync numbers from Meta");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncingAll(false);
    }
  }
```

- [ ] **Step 5: Remove the now-stale "no configured numbers" disable condition on both Sync buttons**

There are two buttons that disable when `numbers.filter(n => n.meta_phone_number_id && n.status !== "archived").length === 0` — this no longer applies since sync now discovers numbers directly from Meta rather than requiring them to already exist locally. Replace the first occurrence:

```tsx
                  <button
                    onClick={handleSyncAllMeta}
                    disabled={syncingAll || numbers.filter(n => n.meta_phone_number_id && n.status !== "archived").length === 0}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-primary hover:border-primary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                    title="Sync all configured numbers from Meta"
                  >
```

with:

```tsx
                  <button
                    onClick={handleSyncAllMeta}
                    disabled={syncingAll}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-primary hover:border-primary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                    title="Discover and sync every number on your connected Meta WhatsApp account"
                  >
```

And the second occurrence (in the Activity Log tab's Sync button):

```tsx
                  disabled={syncingAll || numbers.filter(n => n.meta_phone_number_id && n.status !== "archived").length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-primary hover:border-primary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                  title="Sync quality from Meta and log any changes"
```

with:

```tsx
                  disabled={syncingAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-surface-mid text-on-surface hover:text-primary hover:border-primary/40 rounded-lg font-label text-xs font-semibold transition-colors disabled:opacity-50"
                  title="Discover and sync every number on your connected Meta WhatsApp account"
```

- [ ] **Step 6: Blur locked cards and gate the Pause/Resume action**

Replace the opening of the number card (the `<div key={num.id} ...>` and the Row 1 wrapper `<div className="mb-3 flex flex-wrap items-center gap-3">`):

```tsx
                    <div
                      key={num.id}
                      className="rounded-xl border border-surface-mid bg-surface-low/40 p-4 hover:bg-surface-low transition-colors"
                    >
                      {/* Row 1: name + role + status + quality */}
                      <div className="mb-3 flex flex-wrap items-center gap-3">
```

with:

```tsx
                    <div
                      key={num.id}
                      className={cn(
                        "rounded-xl border bg-surface-low/40 p-4 hover:bg-surface-low transition-colors",
                        num.locked ? "border-dashed border-surface-mid/70" : "border-surface-mid"
                      )}
                    >
                      {/* Row 1: name + role + status + quality */}
                      <div className={cn("mb-3 flex flex-wrap items-center gap-3", num.locked && "blur-[1.5px] opacity-60")}>
```

Immediately after the closing of that Row 1 `</div>` (right before the `{/* Row 2: sends bar + warm-up + actions */}` comment), add the locked-status banner. Find:

```tsx
                      </div>

                      {/* Row 2: sends bar + warm-up + actions */}
```

and replace with:

```tsx
                      </div>

                      {num.locked && (
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-100">
                          <span className="flex items-center gap-1.5 font-body text-[11px] text-amber-700">
                            <Lock size={11} className="shrink-0" />
                            Over your numbers pool quota — set this as primary to activate it, or upgrade for more slots.
                          </span>
                          <a
                            href="/dashboard/subscriptions"
                            className="shrink-0 px-2.5 py-1 bg-primary text-white rounded-md font-label text-[11px] font-semibold hover:bg-primary/90 transition-colors"
                          >
                            Upgrade
                          </a>
                        </div>
                      )}

                      {/* Row 2: sends bar + warm-up + actions */}
```

Now gate the Pause/Resume button so a locked number can be paused further but not resumed. Replace:

```tsx
                        {/* Pause / Resume */}
                        {canManageNumbers && (
                          <button
                            onClick={() => handleTogglePause(num)}
                            disabled={isPausing}
                            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg border font-label text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                              num.paused_outbound
                                ? "border-green-200 bg-green-50 hover:bg-green-100 text-green-700"
                                : "border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700"
                            }`}
                            title={num.paused_outbound ? "Resume outbound messaging" : "Pause outbound messaging"}
                          >
                            {num.paused_outbound
                              ? <><PlayCircle size={12} /> Resume</>
                              : <><PauseCircle size={12} /> Pause</>
                            }
                          </button>
                        )}
```

with:

```tsx
                        {/* Pause / Resume -- resuming a locked number is blocked (matches the backend PATCH guard); pausing one further is still fine */}
                        {canManageNumbers && (
                          <button
                            onClick={() => handleTogglePause(num)}
                            disabled={isPausing || (num.locked && num.paused_outbound)}
                            title={
                              num.locked && num.paused_outbound
                                ? "Locked by your numbers pool quota — set as primary or upgrade to resume"
                                : num.paused_outbound ? "Resume outbound messaging" : "Pause outbound messaging"
                            }
                            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg border font-label text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                              num.paused_outbound
                                ? "border-green-200 bg-green-50 hover:bg-green-100 text-green-700"
                                : "border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700"
                            }`}
                          >
                            {num.paused_outbound
                              ? <><PlayCircle size={12} /> Resume</>
                              : <><PauseCircle size={12} /> Pause</>
                            }
                          </button>
                        )}
```

(The "Set Primary" button needs no change — it already shows for any `role !== "primary" && role !== "archived"` number regardless of lock state, which is exactly the unlock action locked numbers need. Rename, Delete, and per-number "Sync Meta" also need no change — all three stay enabled on locked numbers.)

- [ ] **Step 7: Verify — typecheck and lint**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

Run: `cd frontend && npm run lint`
Expected: no errors (CI runs this — tsc passing alone is not sufficient, per this project's established verification bar).

- [ ] **Step 8: Verify — manual browser check**

Run: `cd frontend && npm run dev` (and `cd backend && uvicorn app.main:app --reload` if not already running).

In the browser, navigate to `/dashboard/numbers`:
- Confirm the page loads with no console errors.
- Confirm the "Sync from Meta" button is enabled even with zero existing numbers (previously it required an existing `meta_phone_number_id`).
- If a test tenant with `meta_waba_id` configured is available, click "Sync from Meta" and confirm: numbers beyond the tenant's `numbers_pool.limit` render blurred with the amber "Locked" banner and an "Upgrade" link to `/dashboard/subscriptions`; "Set Primary" is still clickable on a locked card and clicking it un-blurs that card on the next reload.
- If no live Meta WABA is available for manual testing, confirm at minimum that a locked number (simulate by temporarily forcing `locked: true` in a browser devtools network override, or reviewer's judgment) renders the blur + banner correctly and that Pause/Resume respects the `num.locked && num.paused_outbound` disable condition.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/dashboard/numbers/page.tsx
git commit -m "feat: blur/lock over-quota numbers in the pool UI, sync bulk button pulls from Meta directly"
```

---

## Self-Review Notes

- **Spec coverage:** locking rule (Task 1/2), `GET` locked field (Task 3), `PATCH` guard incl. primary-exempt (Task 4), `list_waba_phone_numbers` (Task 5), bulk sync incl. no-auto-primary + normalization fallback + skip-promotion-when-locked (Task 6), live routing exclusion (Task 7), frontend blur/CTA/button gating + bulk-button rewire (Task 8). `failover.py` and manual-add are explicitly left untouched per the spec's non-goals — no task touches either.
- **Type consistency:** `get_unlocked_number_ids(db, tenant_id) -> set[str]` and `numbers_pool_limit(db, tenant_id) -> int` signatures match across Tasks 2, 3, 4, 6, 7. `normalize_phone_number(raw: str) -> str` matches across Tasks 1 and 6. `list_waba_phone_numbers(waba_id, access_token=None, tenant_id=None) -> list[dict]` matches across Tasks 5 and 6.
- **No placeholders:** every step has complete, runnable code — no TBD/TODO markers.
