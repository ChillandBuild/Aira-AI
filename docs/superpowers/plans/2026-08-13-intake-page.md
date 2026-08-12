# Intake Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-client "Consultations" page into a domain-neutral "Intake" page — a filterable, exportable table whose columns adapt to each tenant's configured fields — and add tiered packages so a lead picks Basic/Premium/VIP before paying.

**Architecture:** The `expert_handoff_sessions` table is renamed `intake_sessions` and gains four snapshot columns (`field_schema`, `package_key`, `package_name`, `package_amount_paise`) written at collection time, so later config edits never rewrite historical rows. The tenant config grows a `packages[]` list and a `service_noun` string; the WhatsApp flow gains one status (`awaiting_package_choice`) between the offer and field collection. The frontend replaces the list+detail split with a horizontally-scrolling table (sticky Lead/Phone), a column picker, keyset infinite scroll, and a right-side drawer.

**Tech Stack:** FastAPI + Supabase (PostgREST client) on the backend, Next.js 14 App Router + Tailwind on the frontend, Razorpay payment links, Gemini for slot-filling, `pytest`/`unittest` for backend tests.

## Global Constraints

- Backend tests use `unittest.TestCase` + `unittest.mock.MagicMock` + `fastapi.testclient.TestClient`, matching `backend/tests/test_expert_handoff_sessions_route.py`. Do not introduce a different test style.
- Run backend tests with `cd backend && pytest`.
- Run frontend checks with `cd frontend && npm run lint` **and** `npm run typecheck`. Lint fails on unused imports; the build does not. Both must pass.
- Migrations live in `backend/supabase/migrations/NNN_name.sql`. The last applied is `175_auto_enable_rls_new_tables.sql`; this plan adds `176`.
- Migrations are applied to live Supabase via the Supabase MCP `apply_migration` tool. **Ask the user before applying anything to live Supabase.** After any schema change, run `NOTIFY pgrst, 'reload schema';`.
- The old `/api/v1/expert-handoff` route prefix MUST stay mounted for the lifetime of this plan. Razorpay's dashboard has `/api/v1/expert-handoff/razorpay-webhook` registered externally; unmounting it loses live payment confirmations.
- Prices are rendered by Python from config. The LLM never generates a price or a package name — it only matches a lead's reply to an existing `package.key`.
- Money written to a session row comes from the Razorpay webhook payload, never from config.
- Never mutate a dict or list in place; build a new one (`{**old, **patch}`).
- Frontend accent colour is `#5b21b6`; follow the existing `card`, `badge`, `font-display`/`font-label`/`font-body` class conventions already used in `frontend/app/dashboard/`.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Settings tab `Messaging Channels` → `Integrations` | The panel holds Meta Ads and Razorpay, not just messaging channels. |
| D2 | Page `Consultations` → `Intake`, fixed generic name | "Consultation" fits astrology, not a clinic or an agency. A fixed neutral noun avoids a per-tenant label config for the staff-facing UI. |
| D3 | Rename goes all the way: route, folder, table, API prefix, backend modules, app_settings key | Chosen over label-only so the codebase does not carry two vocabularies. |
| D4 | Old `/api/v1/expert-handoff` prefix kept as a live alias | Razorpay's webhook URL is registered externally and cannot be changed atomically with a deploy. |
| D5 | Per-row `field_schema` snapshot | Field labels are free-text and deletable. Without a snapshot, renaming a field retroactively relabels old rows — a wrong label is worse than a blank cell. |
| D6 | Table columns = union of keys across visible rows; current-config fields first, then legacy keys | One flat list the client can scan and export, with no silent data loss when the field set changes between campaigns. |
| D7 | Column picker, persisted in `localStorage` | Field sets accumulate; the client should be able to narrow the view without the export losing data. |
| D8 | CSV from a backend endpoint, honouring filter + search, ignoring the column picker | Hiding a column is a viewing choice, not a data choice. A client-side CSV would silently export only the loaded rows. |
| D9 | Keyset infinite scroll, batches of 50 | Today's endpoint has a hard `.limit(50)` with no way to reach older rows — a live bug. Keyset (not offset) avoids duplicate/skipped rows as new sessions arrive mid-scroll. |
| D10 | Filters: All / Awaiting Payment / Paid / Resolved | Resolved rows currently vanish permanently after "Mark Resolved", making the action unauditable. Mid-collection and cancelled rows stay hidden — not actionable. |
| D11 | Row click opens a right-side drawer | Keeps the table scannable while giving long free-text field values room. |
| D12 | `packages[]` replaces the single `amount_paise` | The astrology tenant sells Basic/Premium/VIP at different prices. |
| D13 | Lead picks the package right after accepting the offer, before fields are collected | The lead sees the price before investing effort in giving DOB/birthplace. It is also the only order that supports per-package field sets later. |
| D14 | Package name and price snapshotted onto the row | Repricing VIP must not rewrite last month's revenue history. |
| D15 | Package changeable before payment, by the lead in chat or by staff in the drawer | Upsells and mistakes both happen; it is cheap while the row is unpaid. |
| D16 | Paid amount recorded from the webhook payload | A lead can pay a link that was just superseded. The row must show what was actually charged, and flag a mismatch rather than trust config. |
| D17 | `service_noun` config string substituted into the receipt, the Razorpay description, and the AI prompt block | Those three are hardcoded "consultation" strings that no AI tuning reaches. Messages stay hardcoded; only the noun varies. |
| D18 | Same field set for all packages | YAGNI. The per-row snapshot makes per-package fields an additive change later, not a rewrite. |

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/supabase/migrations/176_intake_rename_and_packages.sql` | Table rename, four new columns, status CHECK update, app_settings key rename, backfill |
| `backend/app/services/intake.py` | Renamed from `services/expert_handoff.py`; adds package selection, snapshots, service noun |
| `backend/app/routes/intake.py` | Renamed from `routes/expert_handoff.py`; adds filters, keyset paging, CSV, package override |
| `backend/app/services/intake_csv.py` | CSV row/header assembly — pure functions, no I/O, unit-testable |
| `backend/tests/test_intake_packages.py` | Package config, choice matching, link amount |
| `backend/tests/test_intake_csv.py` | Header union, label collision, cell ordering |
| `backend/tests/test_intake_sessions_route.py` | Renamed from `test_expert_handoff_sessions_route.py`; filters + keyset paging |
| `frontend/app/dashboard/intake/page.tsx` | Page shell: filters, search, CSV button, table container, drawer host |
| `frontend/app/dashboard/intake/IntakeTable.tsx` | The table itself: columns, sticky cells, infinite-scroll sentinel |
| `frontend/app/dashboard/intake/IntakeDrawer.tsx` | Right-side drawer: fields, payment info, package override, Mark Resolved |
| `frontend/app/dashboard/intake/ColumnPicker.tsx` | Column visibility dropdown + `localStorage` persistence |
| `frontend/app/dashboard/intake/columns.ts` | Pure column-derivation logic from rows + snapshots |
| `frontend/app/dashboard/consultations/page.tsx` | Replaced with a redirect to `/dashboard/intake` |

**Deleted:** `backend/app/services/expert_handoff.py`, `backend/app/routes/expert_handoff.py`, `frontend/app/dashboard/consultations/ConsultationDetails.tsx`, `backend/tests/test_expert_handoff_sessions_route.py`.

**Modified:** `backend/app/main.py`, `backend/app/routes/app_settings.py`, `backend/app/routes/webhook.py`, `backend/app/services/ai_reply.py`, `backend/tests/test_expert_handoff.py`, `backend/tests/test_expert_handoff_webhook.py`, `frontend/lib/api.ts`, `frontend/components/sidebar.tsx`, `frontend/components/MoreMenu.tsx`, `frontend/components/AppHeader.tsx`, `frontend/app/dashboard/settings/page.tsx`, `frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx`.

---

### Task 1: Migration — rename table, add snapshot columns, backfill

**Files:**
- Create: `backend/supabase/migrations/176_intake_rename_and_packages.sql`

**Interfaces:**
- Produces: table `intake_sessions` with columns `field_schema jsonb`, `package_key text`, `package_name text`, `package_amount_paise integer`; status CHECK accepting `awaiting_package_choice`; `app_settings.key = 'intake_config'`.

- [ ] **Step 1: Write the migration**

```sql
-- 176_intake_rename_and_packages.sql
-- Renames the Paid Expert Handoff feature to "Intake" and adds per-row
-- snapshots so later config edits never rewrite historical rows.

BEGIN;

ALTER TABLE expert_handoff_sessions RENAME TO intake_sessions;

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS field_schema jsonb,
  ADD COLUMN IF NOT EXISTS package_key text,
  ADD COLUMN IF NOT EXISTS package_name text,
  ADD COLUMN IF NOT EXISTS package_amount_paise integer;

-- The old CHECK travelled with the rename but still carries the old name and
-- lacks the new status.
ALTER TABLE intake_sessions
  DROP CONSTRAINT IF EXISTS expert_handoff_sessions_status_check;

ALTER TABLE intake_sessions
  ADD CONSTRAINT intake_sessions_status_check CHECK (status = ANY (ARRAY[
    'offer_pending'::text,
    'awaiting_package_choice'::text,
    'collecting'::text,
    'awaiting_confirmation'::text,
    'awaiting_payment'::text,
    'paid'::text,
    'resolved'::text,
    'cancelled'::text
  ]));

-- Keyset paging index: (tenant_id, created_at DESC, id DESC).
CREATE INDEX IF NOT EXISTS idx_intake_sessions_tenant_created
  ON intake_sessions (tenant_id, created_at DESC, id DESC);

UPDATE app_settings SET key = 'intake_config' WHERE key = 'expert_handoff_config';

-- Backfill field_schema from each tenant's current configured fields.
UPDATE intake_sessions s
SET field_schema = (a.value::jsonb -> 'fields')
FROM app_settings a
WHERE a.tenant_id = s.tenant_id
  AND a.key = 'intake_config'
  AND s.field_schema IS NULL
  AND (a.value::jsonb -> 'fields') IS NOT NULL;

-- Backfill the package snapshot from the old single-fee config.
UPDATE intake_sessions s
SET package_key = 'standard',
    package_name = 'Consultation',
    package_amount_paise = COALESCE(s.amount_paise, (a.value::jsonb ->> 'amount_paise')::int)
FROM app_settings a
WHERE a.tenant_id = s.tenant_id
  AND a.key = 'intake_config'
  AND s.package_key IS NULL;

COMMIT;
```

- [ ] **Step 2: Dry-run the backfill against live data before applying**

Ask the user for permission to touch live Supabase first. Then run this read-only check via the Supabase MCP `execute_sql` tool and record the output:

```sql
select s.id, s.status, s.amount_paise, (a.value::jsonb -> 'fields') as would_snapshot
from expert_handoff_sessions s
left join app_settings a on a.tenant_id = s.tenant_id and a.key = 'expert_handoff_config';
```

Expected: 4 rows, each with a non-null `would_snapshot` array. If any row's `would_snapshot` is null, that tenant has no saved config — note it and continue; `field_schema` stays null and the frontend falls back to prettified keys.

- [ ] **Step 3: Apply the migration**

Apply via Supabase MCP `apply_migration` with name `176_intake_rename_and_packages`, then:

```sql
NOTIFY pgrst, 'reload schema';
```

- [ ] **Step 4: Verify**

```sql
select id, status, field_schema, package_key, package_name, package_amount_paise
from intake_sessions order by created_at desc;
```

Expected: 4 rows, all with non-null `package_key = 'standard'`, and `field_schema` populated where the tenant had config.

- [ ] **Step 5: Commit**

```bash
git add backend/supabase/migrations/176_intake_rename_and_packages.sql
git commit -m "feat: rename expert_handoff_sessions to intake_sessions, add snapshot columns"
```

---

### Task 2: Backend rename — modules, routes, prefix alias

Pure rename. No behaviour change. Every existing test must still pass at the end.

**Files:**
- Create: `backend/app/services/intake.py` (git mv from `services/expert_handoff.py`)
- Create: `backend/app/routes/intake.py` (git mv from `routes/expert_handoff.py`)
- Modify: `backend/app/main.py:19-20`, `backend/app/main.py:556-557`
- Modify: `backend/app/routes/app_settings.py:20`, `:93-105`, `:1586-1605`
- Modify: `backend/app/routes/webhook.py:312-313`
- Modify: `backend/app/services/ai_reply.py:925`, `:1313-1315`
- Modify: `backend/tests/test_expert_handoff.py`, `backend/tests/test_expert_handoff_webhook.py`
- Create: `backend/tests/test_intake_sessions_route.py` (git mv from `test_expert_handoff_sessions_route.py`)

**Interfaces:**
- Produces: `app.services.intake` exporting `get_intake_config(tenant_id, db=None) -> dict`, `save_intake_config(tenant_id, config, db=None) -> None`, `route_intake(lead_id, tenant_id, phone, body, db=None) -> bool`, `confirm_intake_payment(session_id, razorpay_payment_id, db=None) -> tuple[str, str, str, str] | None`, `resolve_intake_session(session_id, tenant_id, db=None) -> bool`, `get_paid_unresolved_session(lead_id, tenant_id, db=None) -> dict | None`, `get_session_tenant_id(session_id, db=None) -> str | None`.
- Produces: `app.routes.intake` exporting `router` and `public_router`.

- [ ] **Step 1: Move the files with git so history follows**

```bash
cd "/Users/prem/Documents/Aira AI"
git mv backend/app/services/expert_handoff.py backend/app/services/intake.py
git mv backend/app/routes/expert_handoff.py backend/app/routes/intake.py
git mv backend/tests/test_expert_handoff_sessions_route.py backend/tests/test_intake_sessions_route.py
```

- [ ] **Step 2: Rename symbols and table references inside the moved files**

In `backend/app/services/intake.py`:
- `get_expert_handoff_config` → `get_intake_config`
- `save_expert_handoff_config` → `save_intake_config`
- `detect_expert_handoff_intent` → `detect_intake_intent`
- `route_expert_handoff` → `route_intake`
- `confirm_expert_handoff_payment` → `confirm_intake_payment`
- `resolve_expert_handoff_session` → `resolve_intake_session`
- every `db.table("expert_handoff_sessions")` → `db.table("intake_sessions")` (5 occurrences: lines 143, 159, 167, 309, 334, 345, 388, 412 — grep to be sure)
- the `app_settings` key `"expert_handoff_config"` → `"intake_config"` (2 occurrences, lines 35 and 55)
- the notify_pool event type `"expert_handoff_paid"` → `"intake_paid"` and its message body → `f"Lead '{customer_name}' paid for a consultation — check Intake."`
- `reply_source` in `_send_and_log` stays `"expert_handoff"` — migration 173 added it as an existing enum-ish value and changing it would orphan historical message rows.

In `backend/app/routes/intake.py`:
- `list_expert_handoff_sessions` → `list_intake_sessions`
- imports updated to `from app.services.intake import confirm_intake_payment, get_session_tenant_id, resolve_intake_session`

- [ ] **Step 3: Update the four call sites outside those files**

`backend/app/main.py` lines 19-20:

```python
from app.routes.intake import public_router as intake_public_router
from app.routes import intake
```

`backend/app/main.py` lines 556-557 become four mounts — new prefix plus the legacy alias:

```python
app.include_router(intake_public_router, prefix="/api/v1/intake", tags=["intake-webhook"])
app.include_router(intake.router, prefix="/api/v1/intake", tags=["intake"], dependencies=_auth)
# Legacy prefix. Razorpay's dashboard has /api/v1/expert-handoff/razorpay-webhook
# registered externally; remove these two lines only after updating it there.
app.include_router(intake_public_router, prefix="/api/v1/expert-handoff", tags=["intake-webhook-legacy"])
app.include_router(intake.router, prefix="/api/v1/expert-handoff", tags=["intake-legacy"], dependencies=_auth)
```

`backend/app/routes/webhook.py` lines 312-313:

```python
from app.services.intake import route_intake
consumed = await route_intake(lead_id=lead_id, tenant_id=tenant_id, phone=phone, body=body, db=db)
```

`backend/app/services/ai_reply.py` line 1313:

```python
from app.services.intake import get_paid_unresolved_session
```

Rename `_expert_handoff_paid_prompt_block` → `_intake_paid_prompt_block` at line 925 and its call site at line 1315.

`backend/app/routes/app_settings.py`: rename `ExpertHandoffFieldUpdate` → `IntakeFieldUpdate`, `ExpertHandoffConfigUpdate` → `IntakeConfigUpdate`, the import on line 20, and both route paths from `/expert-handoff-config` to `/intake-config`.

- [ ] **Step 4: Update the moved tests' patch targets**

Every `@patch("app.routes.expert_handoff.get_supabase")` becomes `@patch("app.routes.intake.get_supabase")`, and every `@patch("app.services.expert_handoff.X")` becomes `@patch("app.services.intake.X")`. URLs in the moved tests stay `/api/v1/expert-handoff/...` — that is now the alias, and leaving them there proves the alias works.

- [ ] **Step 5: Prove nothing was missed**

```bash
cd "/Users/prem/Documents/Aira AI"
grep -rn "expert_handoff_sessions\|expert_handoff_config\|routes.expert_handoff\|services.expert_handoff" backend/app backend/tests
```

Expected: no output. Any hit is a missed rename.

- [ ] **Step 6: Run the full backend suite**

```bash
cd backend && pytest
```

Expected: PASS, same count as before the rename. This is a pure rename — a single failure means a call site was missed.

- [ ] **Step 7: Commit**

```bash
git add -A backend
git commit -m "refactor: rename expert_handoff modules to intake, alias legacy route prefix"
```

---

### Task 3: Config shape — packages and service noun

**Files:**
- Modify: `backend/app/services/intake.py` (the `_DEFAULT_CONFIG` block and `get_intake_config`)
- Modify: `backend/app/routes/app_settings.py` (`IntakeConfigUpdate`, `patch_intake_config`)
- Create: `backend/tests/test_intake_packages.py`

**Interfaces:**
- Consumes: `get_intake_config` / `save_intake_config` from Task 2.
- Produces: config dict with `packages: list[dict]` (each `{"key": str, "name": str, "amount_paise": int, "description": str}`) and `service_noun: str`. Produces `normalize_packages(config: dict) -> list[dict]` in `app.services.intake`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_intake_packages.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intake import normalize_packages


class NormalizePackagesTests(unittest.TestCase):
    def test_returns_configured_packages_unchanged(self):
        config = {
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": "30 min call"},
                {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min + report"},
            ],
            "amount_paise": 0,
        }

        result = normalize_packages(config)

        self.assertEqual([p["key"] for p in result], ["basic", "vip"])
        self.assertEqual(result[1]["amount_paise"], 500000)

    def test_legacy_single_fee_becomes_one_standard_package(self):
        config = {"packages": [], "amount_paise": 1000}

        result = normalize_packages(config)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "standard")
        self.assertEqual(result[0]["name"], "Consultation")
        self.assertEqual(result[0]["amount_paise"], 1000)

    def test_no_packages_and_no_fee_returns_empty(self):
        self.assertEqual(normalize_packages({"packages": [], "amount_paise": 0}), [])

    def test_does_not_mutate_the_input_config(self):
        config = {"packages": [], "amount_paise": 1000}
        normalize_packages(config)
        self.assertEqual(config["packages"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd backend && pytest tests/test_intake_packages.py -v
```

Expected: FAIL with `ImportError: cannot import name 'normalize_packages'`.

- [ ] **Step 3: Implement**

In `backend/app/services/intake.py`, replace `_DEFAULT_CONFIG` and add `normalize_packages` beneath it:

```python
_DEFAULT_CONFIG = {
    "enabled": False,
    "trigger_description": "",
    "offer_message": "",
    "fields": [],  # list of {"key": str, "label": str, "type": "text"|"date"|"choice", "options": list[str]?}
    "packages": [],  # list of {"key": str, "name": str, "amount_paise": int, "description": str}
    "service_noun": "consultation",
    "amount_paise": 0,  # legacy single fee; superseded by packages, kept for auto-migration
}


def normalize_packages(config: dict) -> list[dict]:
    """The tenant's packages, with the pre-packages single `amount_paise` config
    auto-migrated to one 'standard' package so an existing tenant keeps working
    without touching their settings."""
    packages = config.get("packages") or []
    if packages:
        return [dict(p) for p in packages]
    legacy_fee = config.get("amount_paise") or 0
    if legacy_fee > 0:
        return [{
            "key": "standard",
            "name": "Consultation",
            "amount_paise": legacy_fee,
            "description": "",
        }]
    return []
```

- [ ] **Step 4: Run the test**

```bash
cd backend && pytest tests/test_intake_packages.py -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Extend the settings Pydantic model**

In `backend/app/routes/app_settings.py`, add above `IntakeConfigUpdate`:

```python
class IntakePackageUpdate(BaseModel):
    key: str
    name: str
    amount_paise: int
    description: str = ""
```

and extend the config model:

```python
class IntakeConfigUpdate(BaseModel):
    enabled: bool | None = None
    trigger_description: str | None = None
    offer_message: str | None = None
    fields: list[IntakeFieldUpdate] | None = None
    packages: list[IntakePackageUpdate] | None = None
    service_noun: str | None = None
    amount_paise: int | None = None
```

In `patch_intake_config`, after the existing duplicate-field-key check, add:

```python
    if "packages" in patch:
        pkg_keys = [p["key"] for p in patch["packages"]]
        if len(pkg_keys) != len(set(pkg_keys)):
            raise HTTPException(status_code=400, detail="Duplicate package keys")
        if any(p["amount_paise"] < 1 for p in patch["packages"]):
            raise HTTPException(status_code=400, detail="Package amount must be >= 1 paise")
        if any(not p["name"].strip() for p in patch["packages"]):
            raise HTTPException(status_code=400, detail="Package name is required")
    if patch.get("enabled") and not (patch.get("packages") or current.get("packages") or current.get("amount_paise")):
        raise HTTPException(status_code=400, detail="Add at least one package before enabling")
    if "service_noun" in patch and not patch["service_noun"].strip():
        raise HTTPException(status_code=400, detail="service_noun cannot be blank")
```

- [ ] **Step 6: Write the settings-route test**

Append to `backend/tests/test_intake_packages.py`:

```python
from unittest.mock import patch as mock_patch
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class IntakeConfigRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_duplicate_package_keys(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 1000, "description": ""},
                {"key": "basic", "name": "Basic Again", "amount_paise": 2000, "description": ""},
            ]
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_enabling_with_no_packages(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={"enabled": True})
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_saves_valid_packages(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [{"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min"}],
            "service_noun": "reading",
        })
        self.assertEqual(res.status_code, 200)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["service_noun"], "reading")
        self.assertEqual(saved["packages"][0]["key"], "vip")
```

- [ ] **Step 7: Run the tests**

```bash
cd backend && pytest tests/test_intake_packages.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/intake.py backend/app/routes/app_settings.py backend/tests/test_intake_packages.py
git commit -m "feat: add packages and service_noun to intake config"
```

---

### Task 4: Package choice step in the WhatsApp flow

**Files:**
- Modify: `backend/app/services/intake.py` (`_ACTIVE_STATUSES`, `route_intake`, new helpers)
- Modify: `backend/tests/test_intake_packages.py`

**Interfaces:**
- Consumes: `normalize_packages` from Task 3.
- Produces: `package_list_message(packages: list[dict], service_noun: str) -> str` and `async match_package(message: str, packages: list[dict], tenant_id: str) -> dict | None` in `app.services.intake`.

- [ ] **Step 1: Write the failing test for the rendered message**

Append to `backend/tests/test_intake_packages.py`:

```python
from app.services.intake import package_list_message


class PackageListMessageTests(unittest.TestCase):
    def test_renders_names_and_rupee_prices_from_config(self):
        packages = [
            {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": "30 min call"},
            {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min + written report"},
        ]

        text = package_list_message(packages, "consultation")

        self.assertIn("Basic — ₹500", text)
        self.assertIn("30 min call", text)
        self.assertIn("VIP — ₹5000", text)
        self.assertIn("consultation", text)

    def test_uses_the_configured_service_noun(self):
        packages = [{"key": "b", "name": "Basic", "amount_paise": 1000, "description": ""}]
        self.assertIn("reading", package_list_message(packages, "reading"))

    def test_omits_the_dash_when_a_package_has_no_description(self):
        packages = [{"key": "b", "name": "Basic", "amount_paise": 1000, "description": ""}]
        self.assertNotIn("—  ", package_list_message(packages, "consultation"))
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd backend && pytest tests/test_intake_packages.py::PackageListMessageTests -v
```

Expected: FAIL with `ImportError: cannot import name 'package_list_message'`.

- [ ] **Step 3: Implement the renderer**

In `backend/app/services/intake.py`, add after `normalize_packages`:

```python
def _rupees(amount_paise: int) -> str:
    """Whole rupees when the amount is exact, two decimals otherwise."""
    if amount_paise % 100 == 0:
        return f"₹{amount_paise // 100}"
    return f"₹{amount_paise / 100:.2f}"


def package_list_message(packages: list[dict], service_noun: str) -> str:
    """Rendered in Python, never by the LLM: these are prices the customer will
    be held to, and a hallucinated figure is a real liability."""
    lines = []
    for p in packages:
        line = f"• {p['name']} — {_rupees(p['amount_paise'])}"
        if p.get("description"):
            line += f"\n  {p['description']}"
        lines.append(line)
    return (
        f"Here are our {service_noun} options:\n\n"
        + "\n".join(lines)
        + "\n\nWhich one would you like?"
    )
```

- [ ] **Step 4: Run the test**

```bash
cd backend && pytest tests/test_intake_packages.py::PackageListMessageTests -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Write the failing test for package matching**

Append to `backend/tests/test_intake_packages.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.intake import match_package

PACKAGES = [
    {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": ""},
    {"key": "premium", "name": "Premium", "amount_paise": 200000, "description": ""},
    {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": ""},
]


class MatchPackageTests(unittest.TestCase):
    def test_exact_name_matches_without_calling_the_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_package("VIP", PACKAGES, "t-1"))
        self.assertEqual(result["key"], "vip")
        llm.assert_not_called()

    def test_llm_resolves_a_vague_reply(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"key": "premium"}),
        ):
            result = asyncio.run(match_package("the middle one please", PACKAGES, "t-1"))
        self.assertEqual(result["key"], "premium")

    def test_llm_returning_an_unknown_key_is_treated_as_no_match(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"key": "platinum"}),
        ):
            result = asyncio.run(match_package("platinum", PACKAGES, "t-1"))
        self.assertIsNone(result)

    def test_llm_failure_is_no_match_not_a_crash(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(match_package("uhh", PACKAGES, "t-1"))
        self.assertIsNone(result)
```

- [ ] **Step 6: Run it and watch it fail**

```bash
cd backend && pytest tests/test_intake_packages.py::MatchPackageTests -v
```

Expected: FAIL with `ImportError: cannot import name 'match_package'`.

- [ ] **Step 7: Implement the matcher**

In `backend/app/services/intake.py`, add after `package_list_message`:

```python
_PACKAGE_MATCH_SYSTEM_PROMPT = """You match a customer's reply to one of a fixed list of
packages. You are given the packages (key and name) and the customer's message.

Respond with JSON only: {"key": "<the matching package key>"} or {"key": null} if the
message does not clearly indicate one of the listed packages.

Rules:
- The key MUST be one of the keys given. Never invent a key.
- If the customer is ambiguous or asking a question rather than choosing, return null.
- JSON only, no other text."""


async def match_package(message: str, packages: list[dict], tenant_id: str) -> dict | None:
    """Match a lead's free-text reply to one configured package. Exact name or key
    matches short-circuit the LLM. Fails closed: any error or unknown key returns
    None so the caller re-asks rather than charging the wrong amount."""
    if not packages:
        return None

    cleaned = message.strip().lower()
    for p in packages:
        if cleaned == p["name"].strip().lower() or cleaned == p["key"].strip().lower():
            return dict(p)

    package_list = "\n".join(f"- {p['key']}: {p['name']}" for p in packages)
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_PACKAGE_MATCH_SYSTEM_PROMPT,
            user_prompt=f"Packages:\n{package_list}\n\nCustomer message: {message}",
            temperature=0.0,
            max_tokens=50,
            tenant_id=tenant_id,
            purpose="intake_package_match",
        )
    except Exception as e:
        logger.warning(f"Intake package match failed, treating as no-match: {e}")
        return None

    key = data.get("key")
    for p in packages:
        if key == p["key"]:
            return dict(p)
    return None
```

- [ ] **Step 8: Run the test**

```bash
cd backend && pytest tests/test_intake_packages.py::MatchPackageTests -v
```

Expected: PASS, 4 tests.

- [ ] **Step 9: Wire the new status into the flow**

In `backend/app/services/intake.py`, extend `_ACTIVE_STATUSES`:

```python
_ACTIVE_STATUSES = (
    "offer_pending", "awaiting_package_choice", "collecting",
    "awaiting_confirmation", "awaiting_payment", "paid",
)
```

Replace the `if status == "offer_pending":` branch in `route_intake` so accepting the offer leads to the package question instead of straight to field collection:

```python
        if status == "offer_pending":
            if not _is_affirmative(body):
                _update_session(session["id"], {"status": "cancelled"}, db)
                return False
            packages = normalize_packages(config)
            if len(packages) == 1:
                # Single package: nothing to choose, snapshot it and collect fields.
                _update_session(session["id"], _package_patch(packages[0]) | {
                    "status": "collecting",
                    "field_schema": config["fields"],
                }, db)
                missing = missing_field_labels(config["fields"], session.get("collected_data") or {})
                prompt = f"Great! Could you share your {missing[0].lower()}?" if missing else _summary_text(config["fields"], {})
                await _send_and_log(phone, prompt, tenant_id, lead_id, db)
                return True
            _update_session(session["id"], {"status": "awaiting_package_choice"}, db)
            await _send_and_log(
                phone,
                package_list_message(packages, config["service_noun"]),
                tenant_id, lead_id, db,
            )
            return True

        if status == "awaiting_package_choice":
            packages = normalize_packages(config)
            chosen = await match_package(body, packages, tenant_id)
            if chosen is None:
                await _send_and_log(
                    phone,
                    "Sorry, I didn't catch which one — "
                    + package_list_message(packages, config["service_noun"]),
                    tenant_id, lead_id, db,
                )
                return True
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            patch = _package_patch(chosen) | {
                "collected_data": collected,
                "field_schema": config["fields"],
            }
            if missing:
                _update_session(session["id"], patch | {"status": "collecting"}, db)
                await _send_and_log(
                    phone,
                    f"{chosen['name']} it is. Could you share your {missing[0].lower()}?",
                    tenant_id, lead_id, db,
                )
            else:
                _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                await _send_and_log(phone, _summary_text(config["fields"], collected), tenant_id, lead_id, db)
            return True
```

Add the snapshot helper above `route_intake`:

```python
def _package_patch(package: dict) -> dict:
    """Snapshot the chosen package onto the session row. Repricing or renaming a
    package later must not rewrite what a past lead was actually offered."""
    return {
        "package_key": package["key"],
        "package_name": package["name"],
        "package_amount_paise": package["amount_paise"],
    }
```

- [ ] **Step 10: Run the whole backend suite**

```bash
cd backend && pytest
```

Expected: PASS. If `tests/test_expert_handoff.py` fails on the offer_pending transition, update its expectation to the new `awaiting_package_choice` status — that test is asserting the old flow and the flow deliberately changed.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/intake.py backend/tests/
git commit -m "feat: lead picks a package before intake fields are collected"
```

---

### Task 5: Payment link uses the package; webhook records the real amount

**Files:**
- Modify: `backend/app/services/intake.py` (`route_intake` awaiting_confirmation branch, `confirm_intake_payment`)
- Modify: `backend/app/routes/intake.py` (receipt text)
- Modify: `backend/app/services/ai_reply.py:925` (`_intake_paid_prompt_block`)
- Modify: `backend/tests/test_expert_handoff_webhook.py`

**Interfaces:**
- Consumes: `_package_patch`, `normalize_packages` from Task 4.
- Produces: `_intake_paid_prompt_block(service_noun: str) -> str` in `ai_reply.py` (was zero-arg).

- [ ] **Step 1: Use the snapshotted package for the payment link**

In `backend/app/services/intake.py`, in the `awaiting_confirmation` branch, replace the `create_payment_link` call and the following `_update_session`:

```python
            ref = f"IN-{uuid.uuid4().hex[:8].upper()}"
            collected = session.get("collected_data") or {}
            customer_name = collected.get("name", "Customer")
            amount_paise = session.get("package_amount_paise")
            if not amount_paise:
                logger.error(f"Intake session {session['id']} reached payment with no package amount")
                await _send_and_log(
                    phone,
                    "We've received your details — our team will send the payment link shortly.",
                    tenant_id, lead_id, db,
                )
                return True
            service_noun = config["service_noun"].capitalize()
            try:
                link = await create_payment_link(
                    booking_id=session["id"],
                    booking_ref=ref,
                    amount_paise=amount_paise,
                    customer_name=customer_name,
                    customer_phone=phone,
                    description=f"{service_noun} — {customer_name} ({ref})",
                    tenant_id=tenant_id,
                )
                _update_session(session["id"], {
                    "status": "awaiting_payment",
                    "amount_paise": amount_paise,
                    "payment_link": link["payment_link_url"],
                }, db)
```

- [ ] **Step 2: Write the failing test for webhook amount recording**

Append to `backend/tests/test_expert_handoff_webhook.py` (rename the file's class docstring references to Intake as you go):

```python
class IntakeWebhookAmountTests(unittest.TestCase):
    @patch("app.services.intake.get_supabase")
    def test_records_the_amount_from_the_webhook_not_the_session(self, mock_get_db):
        from app.services.intake import confirm_intake_payment

        db = MagicMock()
        existing = MagicMock()
        existing.data = {
            "id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1",
            "tenant_id": "t-1", "collected_data": {"name": "Cheran"},
            "package_amount_paise": 500000,
        }
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = existing
        mock_get_db.return_value = db

        confirm_intake_payment("sess-1", "pay_123", amount_paid_paise=200000, db=db)

        update_patch = db.table.return_value.update.call_args[0][0]
        self.assertEqual(update_patch["amount_paise"], 200000)
        self.assertTrue(update_patch["amount_mismatch"])
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd backend && pytest tests/test_expert_handoff_webhook.py::IntakeWebhookAmountTests -v
```

Expected: FAIL — `confirm_intake_payment() got an unexpected keyword argument 'amount_paid_paise'`.

- [ ] **Step 4: Add the column, then implement**

Migration 176 is already applied by this point, so this column needs its own follow-on migration. Create `backend/supabase/migrations/177_intake_amount_mismatch.sql`:

```sql
ALTER TABLE intake_sessions ADD COLUMN IF NOT EXISTS amount_mismatch boolean NOT NULL DEFAULT false;
```

Apply it via Supabase MCP (ask the user first) and run `NOTIFY pgrst, 'reload schema';`.

Then change `confirm_intake_payment`'s signature and update block in `backend/app/services/intake.py`:

```python
def confirm_intake_payment(
    session_id: str,
    razorpay_payment_id: str,
    amount_paid_paise: int | None = None,
    db=None,
) -> tuple[str, str, str, str] | None:
```

and inside, replace the update call:

```python
    expected = session.get("package_amount_paise")
    charged = amount_paid_paise if amount_paid_paise is not None else expected
    db.table("intake_sessions").update({
        "status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
        "paid_at": now_iso,
        "amount_paise": charged,
        # A lead can pay a link that was just superseded by a package change.
        # Record what actually arrived and flag the gap for staff rather than
        # trusting config.
        "amount_mismatch": bool(expected and charged and expected != charged),
    }).eq("id", session_id).execute()
```

- [ ] **Step 5: Pass the webhook amount through the route**

In `backend/app/routes/intake.py`, inside `razorpay_webhook`, before the `confirm_intake_payment` call:

```python
    amount_paid_paise = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("amount")
    )
    result = confirm_intake_payment(
        session_id, razorpay_payment_id, amount_paid_paise=amount_paid_paise
    )
```

- [ ] **Step 6: Substitute the service noun into the receipt**

Still in `backend/app/routes/intake.py`, replace the receipt block:

```python
    if result:
        phone, tenant_id, lead_id, customer_name = result
        service_noun = get_intake_config(tenant_id)["service_noun"]
        receipt = (
            f"Payment received, thank you {customer_name}! 🎉\n\n"
            f"Your {service_noun} is confirmed — our expert will be in touch here on WhatsApp shortly."
        )
```

Add `get_intake_config` to the file's imports from `app.services.intake`.

- [ ] **Step 7: Substitute the service noun into the AI prompt block**

In `backend/app/services/ai_reply.py`, change `_intake_paid_prompt_block` to take the noun:

```python
def _intake_paid_prompt_block(service_noun: str) -> str:
    """System-prompt section for a lead who already paid for a human expert
    session and is waiting to be contacted. Mirrors _escalation_prompt_block's
    "stay live, don't go silent" approach for the Intake flow."""
    return (
        f"\n\nPAID {service_noun.upper()} CONTEXT:\n"
        f"This customer has already paid for a one-on-one {service_noun} with our "
        "human expert. A team member has been notified.\n"
        "Rules:\n"
        "- Do NOT attempt to answer their original question yourself — that is "
        "what they paid the human expert for.\n"
        f"- Do NOT offer or re-sell the paid {service_noun} again.\n"
        "- If they ask when the expert will contact them, or say nobody has "
        "reached out yet: reassure them the expert has been notified and will "
        "be in touch here on WhatsApp soon.\n"
        "- Never promise a specific time or name a specific person.\n"
        "- Never claim the expert has already contacted them.\n"
        "- Otherwise, keep answering their other questions normally and helpfully.\n"
    )
```

And its call site at line ~1315:

```python
            from app.services.intake import get_paid_unresolved_session, get_intake_config
            if get_paid_unresolved_session(lead_id, tenant_id, db=db):
                system_prompt += _intake_paid_prompt_block(
                    get_intake_config(tenant_id, db=db)["service_noun"]
                )
```

- [ ] **Step 8: Run the full suite**

```bash
cd backend && pytest
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: package-priced payment links, webhook-recorded amounts, configurable service noun"
```

---

### Task 6: List endpoint — filters, search, keyset paging

**Files:**
- Modify: `backend/app/routes/intake.py` (`list_intake_sessions`)
- Modify: `backend/tests/test_intake_sessions_route.py`

**Interfaces:**
- Produces: `GET /api/v1/intake/sessions?status=&package=&q=&limit=&cursor=` returning `{"data": [...], "next_cursor": str | None}`. `cursor` is `"<created_at>|<id>"`.

- [ ] **Step 1: Write the failing tests**

Replace the body of `backend/tests/test_intake_sessions_route.py`'s test class with:

```python
class IntakeSessionsListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _db_returning(self, rows_data):
        db = MagicMock()
        rows = MagicMock()
        rows.data = rows_data
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = rows
        return db

    @patch("app.routes.intake.get_supabase")
    def test_status_all_returns_the_three_visible_statuses(self, mock_get_db):
        db = self._db_returning([])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/intake/sessions?status=all")

        self.assertEqual(res.status_code, 200)
        db.table.return_value.select.return_value.eq.return_value.in_.assert_called_with(
            "status", ["awaiting_payment", "paid", "resolved"]
        )

    @patch("app.routes.intake.get_supabase")
    def test_rejects_an_unknown_status(self, mock_get_db):
        res = self.client.get("/api/v1/intake/sessions?status=collecting")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_returns_a_next_cursor_when_the_page_is_full(self, mock_get_db):
        rows = [
            {"id": f"s-{i}", "created_at": f"2026-08-{i + 1:02d}T00:00:00Z", "status": "paid"}
            for i in range(50)
        ]
        mock_get_db.return_value = self._db_returning(rows)

        res = self.client.get("/api/v1/intake/sessions?status=all&limit=50")

        self.assertEqual(res.json()["next_cursor"], "2026-08-50T00:00:00Z|s-49")

    @patch("app.routes.intake.get_supabase")
    def test_no_next_cursor_on_a_short_page(self, mock_get_db):
        mock_get_db.return_value = self._db_returning([
            {"id": "s-1", "created_at": "2026-08-01T00:00:00Z", "status": "paid"}
        ])

        res = self.client.get("/api/v1/intake/sessions?status=all&limit=50")

        self.assertIsNone(res.json()["next_cursor"])

    @patch("app.routes.intake.get_supabase")
    def test_rejects_a_malformed_cursor(self, mock_get_db):
        res = self.client.get("/api/v1/intake/sessions?status=all&cursor=garbage")
        self.assertEqual(res.status_code, 400)
```

- [ ] **Step 2: Run and watch them fail**

```bash
cd backend && pytest tests/test_intake_sessions_route.py -v
```

Expected: FAIL — the route still requires `bucket` and returns no `next_cursor`.

- [ ] **Step 3: Implement**

Replace `list_intake_sessions` in `backend/app/routes/intake.py`:

```python
VISIBLE_STATUSES = ["awaiting_payment", "paid", "resolved"]

SESSION_COLUMNS = (
    "id, lead_id, status, collected_data, field_schema, amount_paise, "
    "amount_mismatch, package_key, package_name, package_amount_paise, "
    "payment_link, paid_at, created_at, leads(name, phone)"
)


def _statuses_for(status: str) -> list[str]:
    if status == "all":
        return VISIBLE_STATUSES
    if status in VISIBLE_STATUSES:
        return [status]
    raise HTTPException(
        status_code=400,
        detail=f"status must be 'all' or one of {VISIBLE_STATUSES}",
    )


def _build_query(db, tenant_id: str, status: str, package: str | None, q: str | None, cursor: str | None, limit: int):
    query = (
        db.table("intake_sessions")
        .select(SESSION_COLUMNS)
        .eq("tenant_id", tenant_id)
        .in_("status", _statuses_for(status))
    )
    if package:
        query = query.eq("package_key", package)
    if q:
        # Matches the lead's name or phone. PostgREST needs the embedded-table
        # syntax here because name/phone live on `leads`, not on the session.
        escaped = q.replace(",", "")
        query = query.or_(f"name.ilike.*{escaped}*,phone.ilike.*{escaped}*", foreign_table="leads")
    if cursor:
        parts = cursor.split("|")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Malformed cursor")
        created_at, last_id = parts
        # Keyset, not offset: rows arriving mid-scroll would make offset paging
        # duplicate and skip rows.
        query = query.or_(
            f"created_at.lt.{created_at},and(created_at.eq.{created_at},id.lt.{last_id})"
        )
    return query.order("created_at", desc=True).order("id", desc=True).limit(limit)


@router.get("/sessions")
def list_intake_sessions(
    status: str = Query("all"),
    package: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    ctx: dict = Depends(require_conversations_view),
):
    db = get_supabase()
    result = _build_query(db, ctx["tenant_id"], status, package, q, cursor, limit).execute()
    rows = result.data or []
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = f"{last['created_at']}|{last['id']}"
    return {"data": rows, "next_cursor": next_cursor}
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && pytest tests/test_intake_sessions_route.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Verify the search filter against live data**

Ask the user before touching live Supabase, then confirm the PostgREST embedded-filter syntax actually works — mocked tests cannot prove this:

```bash
curl -s "$BACKEND_URL/api/v1/intake/sessions?status=all&q=Cheran" -H "Authorization: Bearer $TOKEN" | head -c 400
```

Expected: the Cheran row, HTTP 200. If PostgREST rejects the embedded `or_`, fall back to filtering `q` in Python over the fetched page and note the limitation in the plan.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/intake.py backend/tests/test_intake_sessions_route.py
git commit -m "feat: intake sessions list with status/package filters and keyset paging"
```

---

### Task 7: CSV export

**Files:**
- Create: `backend/app/services/intake_csv.py`
- Create: `backend/tests/test_intake_csv.py`
- Modify: `backend/app/routes/intake.py`

**Interfaces:**
- Consumes: `SESSION_COLUMNS`, `_build_query` from Task 6.
- Produces: `build_csv_headers(rows: list[dict]) -> list[tuple[str, str]]` returning `(field_key, header_label)` pairs, and `build_csv_row(row: dict, field_keys: list[str]) -> list[str]`, both in `app.services.intake_csv`. Produces `GET /api/v1/intake/sessions.csv`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_intake_csv.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intake_csv import build_csv_headers, build_csv_row


class BuildCsvHeadersTests(unittest.TestCase):
    def test_unions_keys_across_rows_with_snapshot_labels(self):
        rows = [
            {"created_at": "2026-08-01T00:00:00Z",
             "field_schema": [{"key": "name", "label": "Full Name"}, {"key": "dob", "label": "Date of Birth"}],
             "collected_data": {"name": "Cheran", "dob": "06.06.2000"}},
            {"created_at": "2026-08-10T00:00:00Z",
             "field_schema": [{"key": "name", "label": "Full Name"}, {"key": "gender", "label": "Gender"}],
             "collected_data": {"name": "Priya", "gender": "Female"}},
        ]

        headers = build_csv_headers(rows)

        self.assertEqual(headers, [("name", "Full Name"), ("dob", "Date of Birth"), ("gender", "Gender")])

    def test_newest_snapshot_wins_when_a_label_was_renamed(self):
        rows = [
            {"created_at": "2026-08-01T00:00:00Z",
             "field_schema": [{"key": "city", "label": "Place of Birth"}],
             "collected_data": {"city": "chidambaram"}},
            {"created_at": "2026-08-10T00:00:00Z",
             "field_schema": [{"key": "city", "label": "City"}],
             "collected_data": {"city": "chennai"}},
        ]

        self.assertEqual(build_csv_headers(rows), [("city", "City")])

    def test_two_keys_sharing_a_label_get_the_key_appended(self):
        rows = [
            {"created_at": "2026-08-01T00:00:00Z",
             "field_schema": [{"key": "city", "label": "Place"}, {"key": "town", "label": "Place"}],
             "collected_data": {"city": "a", "town": "b"}},
        ]

        self.assertEqual(build_csv_headers(rows), [("city", "Place (city)"), ("town", "Place (town)")])

    def test_key_with_no_snapshot_falls_back_to_a_prettified_key(self):
        rows = [{"created_at": "2026-08-01T00:00:00Z", "field_schema": None,
                 "collected_data": {"time_of_birth": "10.45"}}]

        self.assertEqual(build_csv_headers(rows), [("time_of_birth", "Time Of Birth")])


class BuildCsvRowTests(unittest.TestCase):
    def test_fixed_columns_then_fields_in_header_order(self):
        row = {
            "leads": {"name": "Cheran", "phone": "+918056110957"},
            "status": "paid", "package_name": "VIP", "amount_paise": 500000,
            "created_at": "2026-08-01T00:00:00Z", "paid_at": "2026-08-01T01:00:00Z",
            "collected_data": {"name": "Cheran", "dob": "06.06.2000"},
        }

        result = build_csv_row(row, ["dob", "gender"])

        self.assertEqual(result[0], "Cheran")
        self.assertEqual(result[1], "+918056110957")
        self.assertEqual(result[2], "paid")
        self.assertEqual(result[3], "VIP")
        self.assertEqual(result[4], "5000.00")
        self.assertEqual(result[-2:], ["06.06.2000", ""])

    def test_lead_name_falls_back_to_collected_data(self):
        row = {
            "leads": {"name": None, "phone": "+91"}, "status": "paid",
            "package_name": None, "amount_paise": None,
            "created_at": "", "paid_at": None,
            "collected_data": {"name": "Cheran"},
        }

        self.assertEqual(build_csv_row(row, [])[0], "Cheran")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and watch it fail**

```bash
cd backend && pytest tests/test_intake_csv.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.intake_csv'`.

- [ ] **Step 3: Implement**

Create `backend/app/services/intake_csv.py`:

```python
"""Pure CSV assembly for intake sessions. No I/O so the header-union and
label-collision rules stay directly unit-testable."""

FIXED_HEADERS = ["Lead", "Phone", "Status", "Package", "Amount charged", "Submitted", "Paid at"]


def _prettify(key: str) -> str:
    return " ".join(word.capitalize() for word in key.split("_"))


def build_csv_headers(rows: list[dict]) -> list[tuple[str, str]]:
    """(field_key, header_label) pairs, in first-seen order across rows.

    A key's label comes from the most recent row whose snapshot defines it, so a
    renamed field reads under its current name while a deleted one keeps the
    name it was collected under. Keys colliding on a label get the key appended
    so the columns stay distinguishable."""
    ordered_keys: list[str] = []
    labels: dict[str, str] = {}
    label_source_date: dict[str, str] = {}

    for row in sorted(rows, key=lambda r: r.get("created_at") or ""):
        created = row.get("created_at") or ""
        schema = {f["key"]: f["label"] for f in (row.get("field_schema") or [])}
        for key in (row.get("collected_data") or {}):
            if key not in ordered_keys:
                ordered_keys.append(key)
            if key in schema and created >= label_source_date.get(key, ""):
                labels[key] = schema[key]
                label_source_date[key] = created

    resolved = {key: labels.get(key) or _prettify(key) for key in ordered_keys}
    counts: dict[str, int] = {}
    for label in resolved.values():
        counts[label] = counts.get(label, 0) + 1

    return [
        (key, f"{label} ({key})" if counts[label] > 1 else label)
        for key, label in resolved.items()
    ]


def build_csv_row(row: dict, field_keys: list[str]) -> list[str]:
    leads = row.get("leads") or {}
    collected = row.get("collected_data") or {}
    amount = row.get("amount_paise")
    return [
        leads.get("name") or collected.get("name") or "",
        leads.get("phone") or "",
        row.get("status") or "",
        row.get("package_name") or "",
        f"{amount / 100:.2f}" if amount else "",
        row.get("created_at") or "",
        row.get("paid_at") or "",
        *[str(collected.get(key) or "") for key in field_keys],
    ]
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && pytest tests/test_intake_csv.py -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Add the endpoint**

In `backend/app/routes/intake.py`:

```python
import csv
import io

from fastapi.responses import StreamingResponse

from app.services.intake_csv import FIXED_HEADERS, build_csv_headers, build_csv_row

CSV_MAX_ROWS = 5000


@router.get("/sessions.csv")
def export_intake_sessions_csv(
    status: str = Query("all"),
    package: str | None = Query(None),
    q: str | None = Query(None),
    ctx: dict = Depends(require_conversations_view),
):
    """Honours the active filter and search; ignores the client's column picker,
    which is a viewing preference, not a data one."""
    db = get_supabase()
    result = _build_query(db, ctx["tenant_id"], status, package, q, None, CSV_MAX_ROWS).execute()
    rows = result.data or []
    if len(rows) == CSV_MAX_ROWS:
        logger.warning(
            f"Intake CSV for tenant {ctx['tenant_id']} hit the {CSV_MAX_ROWS}-row cap"
        )

    headers = build_csv_headers(rows)
    field_keys = [key for key, _ in headers]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIXED_HEADERS + [label for _, label in headers])
    for row in rows:
        writer.writerow(build_csv_row(row, field_keys))
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="intake-{status}.csv"'},
    )
```

- [ ] **Step 6: Write the endpoint test**

Append to `backend/tests/test_intake_csv.py`:

```python
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class IntakeCsvRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.intake.get_supabase")
    def test_streams_a_csv_with_fixed_and_dynamic_headers(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = [{
            "id": "s-1", "status": "paid", "created_at": "2026-08-01T00:00:00Z",
            "paid_at": "2026-08-01T01:00:00Z", "amount_paise": 1000,
            "package_name": "Basic",
            "field_schema": [{"key": "dob", "label": "Date of Birth"}],
            "collected_data": {"dob": "06.06.2000"},
            "leads": {"name": "Cheran", "phone": "+918056110957"},
        }]
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/intake/sessions.csv?status=paid")

        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        body = res.text
        self.assertIn("Lead,Phone,Status,Package,Amount charged,Submitted,Paid at,Date of Birth", body)
        self.assertIn("Cheran,+918056110957,paid,Basic,10.00", body)
```

- [ ] **Step 7: Run the tests**

```bash
cd backend && pytest tests/test_intake_csv.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/intake_csv.py backend/app/routes/intake.py backend/tests/test_intake_csv.py
git commit -m "feat: intake CSV export with snapshot-derived headers"
```

---

### Task 8: Staff package override endpoint

**Files:**
- Modify: `backend/app/routes/intake.py`
- Modify: `backend/app/services/intake.py`
- Modify: `backend/tests/test_intake_packages.py`

**Interfaces:**
- Consumes: `normalize_packages`, `_package_patch` from Task 4.
- Produces: `async change_session_package(session_id: str, tenant_id: str, package_key: str, db=None) -> dict | None` in `app.services.intake`, returning the updated row or `None` if the session is missing, already paid, or the key is unknown. Produces `PATCH /api/v1/intake/sessions/{id}/package`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_intake_packages.py`:

```python
class ChangeSessionPackageTests(unittest.TestCase):
    def _db_with_session(self, status):
        db = MagicMock()
        existing = MagicMock()
        existing.data = {
            "id": "s-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": status,
            "collected_data": {"name": "Cheran"}, "package_key": "basic",
        }
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = existing
        return db

    def test_refuses_to_change_a_paid_session(self):
        from app.services.intake import change_session_package
        db = self._db_with_session("paid")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "vip", db=db))
        self.assertIsNone(result)
        db.table.return_value.update.assert_not_called()

    def test_refuses_an_unknown_package_key(self):
        from app.services.intake import change_session_package
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "platinum", db=db))
        self.assertIsNone(result)

    def test_snapshots_the_new_package_on_an_unpaid_session(self):
        from app.services.intake import change_session_package
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            asyncio.run(change_session_package("s-1", "t-1", "vip", db=db))
        update_patch = db.table.return_value.update.call_args[0][0]
        self.assertEqual(update_patch["package_key"], "vip")
        self.assertEqual(update_patch["package_amount_paise"], 500000)
```

- [ ] **Step 2: Run and watch it fail**

```bash
cd backend && pytest tests/test_intake_packages.py::ChangeSessionPackageTests -v
```

Expected: FAIL with `ImportError: cannot import name 'change_session_package'`.

- [ ] **Step 3: Implement**

In `backend/app/services/intake.py`:

```python
_PACKAGE_CHANGEABLE_STATUSES = (
    "awaiting_package_choice", "collecting", "awaiting_confirmation", "awaiting_payment",
)


async def change_session_package(session_id: str, tenant_id: str, package_key: str, db=None) -> dict | None:
    """Re-point an unpaid session at a different package and clear the stale
    payment link. Returns None if the session is missing, already paid, or the
    key is not configured — the caller turns that into a 404/400."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    row = (
        db.table("intake_sessions")
        .select("id,tenant_id,lead_id,status,collected_data,package_key")
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    session = (row.data if row else None) or None
    if not session or session["status"] not in _PACKAGE_CHANGEABLE_STATUSES:
        return None

    config = get_intake_config(tenant_id, db=db)
    chosen = next((p for p in normalize_packages(config) if p["key"] == package_key), None)
    if chosen is None:
        return None

    # The old Razorpay link stays live until Razorpay processes the cancel, so
    # confirm_intake_payment records the amount that actually arrives rather
    # than assuming this one. See D16.
    patch = _package_patch(chosen) | {"payment_link": None, "amount_paise": None}
    db.table("intake_sessions").update(patch).eq("id", session_id).eq("tenant_id", tenant_id).execute()
    return {**session, **patch}
```

- [ ] **Step 4: Run the test**

```bash
cd backend && pytest tests/test_intake_packages.py::ChangeSessionPackageTests -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Add the route**

In `backend/app/routes/intake.py`:

```python
class PackageChange(BaseModel):
    package_key: str


@router.patch("/sessions/{session_id}/package")
async def change_package(
    session_id: str,
    payload: PackageChange,
    ctx: dict = Depends(require_conversations_reply),
):
    updated = await change_session_package(session_id, ctx["tenant_id"], payload.package_key)
    if updated is None:
        raise HTTPException(
            status_code=400,
            detail="Session not found, already paid, or unknown package",
        )
    return updated
```

Add `from pydantic import BaseModel` and `change_session_package` to the imports.

- [ ] **Step 6: Run the full suite**

```bash
cd backend && pytest
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: staff can change an unpaid intake session's package"
```

---

### Task 9: Settings — package builder, service noun, tab rename

**Files:**
- Modify: `frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx` (rename to `IntakeConfigPanel.tsx`)
- Modify: `frontend/app/dashboard/settings/page.tsx:527-528`
- Modify: `frontend/components/AppHeader.tsx:122`, `:330`

**Interfaces:**
- Consumes: `PATCH /api/v1/settings/intake-config` from Task 3.
- Produces: `IntakeConfigPanel` component export.

- [ ] **Step 1: Rename the panel file and component**

```bash
cd "/Users/prem/Documents/Aira AI"
git mv frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx frontend/app/dashboard/settings/IntakeConfigPanel.tsx
```

Rename the exported component `ExpertHandoffConfigPanel` → `IntakeConfigPanel`, the interfaces `HandoffField` → `IntakeField` and `ExpertHandoffConfig` → `IntakeConfig`, and both fetch URLs from `/api/v1/settings/expert-handoff-config` to `/api/v1/settings/intake-config`. Update the import and usage in `frontend/app/dashboard/settings/page.tsx`.

- [ ] **Step 2: Extend the config type and default**

In `IntakeConfigPanel.tsx`:

```tsx
interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
}

interface IntakeConfig {
  enabled: boolean;
  trigger_description: string;
  offer_message: string;
  fields: IntakeField[];
  packages: IntakePackage[];
  service_noun: string;
  amount_paise: number;
}

const DEFAULT: IntakeConfig = {
  enabled: false,
  trigger_description: "",
  offer_message: "",
  fields: [],
  packages: [],
  service_noun: "consultation",
  amount_paise: 0,
};
```

- [ ] **Step 3: Add package edit handlers**

Alongside the existing `addField` / `updateField` / `removeField`:

```tsx
function addPackage() {
  setDraft({
    ...draft,
    packages: [
      ...draft.packages,
      { key: `package_${draft.packages.length + 1}`, name: "", amount_paise: 0, description: "" },
    ],
  });
}

function updatePackage(index: number, patch: Partial<IntakePackage>) {
  const packages = draft.packages.map((p, i) => (i === index ? { ...p, ...patch } : p));
  setDraft({ ...draft, packages });
}

function removePackage(index: number) {
  setDraft({ ...draft, packages: draft.packages.filter((_, i) => i !== index) });
}
```

The `key` is derived from the name on blur using the existing `slugify` helper, so the client never types a key:

```tsx
function commitPackageName(index: number, name: string) {
  updatePackage(index, { name, key: slugify(name) || `package_${index + 1}` });
}
```

- [ ] **Step 4: Replace the single fee input with the package builder**

Delete the "Consultation fee (₹)" block and `feeText` state, and render in its place:

```tsx
<div className="space-y-3">
  <div className="flex items-center justify-between">
    <div className="font-label text-sm font-semibold text-ink">Packages</div>
    {canManage && (
      <button
        type="button"
        onClick={addPackage}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 font-label text-xs font-bold text-ink hover:bg-surface-subtle"
      >
        <Plus size={14} /> Add package
      </button>
    )}
  </div>

  {draft.packages.map((pkg, index) => (
    <div key={index} className="rounded-2xl border border-border p-3 space-y-2">
      <div className="flex gap-2">
        <input
          value={pkg.name}
          onChange={(e) => updatePackage(index, { name: e.target.value })}
          onBlur={(e) => commitPackageName(index, e.target.value)}
          placeholder="Package name (e.g. VIP)"
          disabled={!canManage}
          className="flex-1 rounded-xl border border-border px-3 py-2 font-body text-sm"
        />
        <input
          type="number"
          min={1}
          value={pkg.amount_paise ? pkg.amount_paise / 100 : ""}
          onChange={(e) =>
            updatePackage(index, { amount_paise: Math.round(Number(e.target.value) * 100) })
          }
          placeholder="₹"
          disabled={!canManage}
          className="w-28 rounded-xl border border-border px-3 py-2 font-body text-sm"
        />
        {canManage && (
          <button type="button" onClick={() => removePackage(index)} aria-label="Remove package">
            <Trash2 size={14} className="text-ink-muted hover:text-red-600" />
          </button>
        )}
      </div>
      <input
        value={pkg.description}
        onChange={(e) => updatePackage(index, { description: e.target.value })}
        placeholder="What's included (shown to the lead with the price)"
        disabled={!canManage}
        className="w-full rounded-xl border border-border px-3 py-2 font-body text-sm"
      />
    </div>
  ))}

  {draft.packages.length === 0 && (
    <p className="font-body text-xs text-ink-muted italic">
      No packages yet — add at least one before enabling.
    </p>
  )}
</div>

<div className="space-y-1">
  <div className="font-label text-sm font-semibold text-ink">What you call it</div>
  <p className="font-body text-xs text-ink-muted">
    The word used in messages the customer receives — the payment receipt, the Razorpay
    description, and how the assistant refers to it. Example: consultation, reading, session.
  </p>
  <input
    value={draft.service_noun}
    onChange={(e) => setDraft({ ...draft, service_noun: e.target.value })}
    disabled={!canManage}
    className="w-full rounded-xl border border-border px-3 py-2 font-body text-sm"
  />
</div>
```

- [ ] **Step 5: Rename the settings tab**

`frontend/components/AppHeader.tsx` line 122:

```tsx
    if (tab === "channels") tabLabel = "Integrations";
```

line 330:

```tsx
              { key: "channels", label: "Integrations" },
```

`frontend/app/dashboard/settings/page.tsx` line 527 comment:

```tsx
          {/* TAB 2: Integrations — messaging channels, Meta Ads, Razorpay */}
```

The tab `key` stays `"channels"` — it appears in URLs.

- [ ] **Step 6: Verify**

```bash
cd frontend && npm run lint && npm run typecheck
```

Expected: both PASS with no output errors. Removing `feeText` leaves an unused `useEffect` — delete it or lint fails.

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: package builder and service noun in intake settings; rename tab to Integrations"
```

---

### Task 10: Frontend API client and types

**Files:**
- Modify: `frontend/lib/api.ts:972-982`, `:2026-2037`

**Interfaces:**
- Consumes: the endpoints from Tasks 6, 7, 8.
- Produces: `IntakeSession`, `IntakeField`, `IntakeStatus`, `IntakePage` types and `api.intake.{listSessions, resolveSession, changePackage, csvPath}`.

- [ ] **Step 1: Replace the type**

```ts
export type IntakeStatus = "awaiting_payment" | "paid" | "resolved";

export interface IntakeField {
  key: string;
  label: string;
  type: "text" | "date" | "choice";
}

export interface IntakeSession {
  id: string;
  lead_id: string;
  status: IntakeStatus;
  collected_data: Record<string, string>;
  field_schema: IntakeField[] | null;
  amount_paise: number | null;
  amount_mismatch: boolean;
  package_key: string | null;
  package_name: string | null;
  package_amount_paise: number | null;
  payment_link: string | null;
  paid_at: string | null;
  created_at: string;
  leads: { name: string | null; phone: string | null } | null;
}

export interface IntakePage {
  data: IntakeSession[];
  next_cursor: string | null;
}
```

- [ ] **Step 2: Replace the client block**

```ts
  intake: {
    listSessions: (params: {
      status: IntakeStatus | "all";
      packageKey?: string;
      q?: string;
      cursor?: string;
    }) => {
      const search = new URLSearchParams({ status: params.status, limit: "50" });
      if (params.packageKey) search.set("package", params.packageKey);
      if (params.q) search.set("q", params.q);
      if (params.cursor) search.set("cursor", params.cursor);
      return apiFetch<IntakePage>(`/api/v1/intake/sessions?${search}`);
    },
    resolveSession: (sessionId: string) =>
      apiFetch<{ status: string }>(`/api/v1/intake/sessions/${sessionId}/resolve`, {
        method: "PATCH",
      }),
    changePackage: (sessionId: string, packageKey: string) =>
      apiFetch<IntakeSession>(`/api/v1/intake/sessions/${sessionId}/package`, {
        method: "PATCH",
        body: JSON.stringify({ package_key: packageKey }),
      }),
    csvPath: (params: { status: IntakeStatus | "all"; packageKey?: string; q?: string }) => {
      const search = new URLSearchParams({ status: params.status });
      if (params.packageKey) search.set("package", params.packageKey);
      if (params.q) search.set("q", params.q);
      return `/api/v1/intake/sessions.csv?${search}`;
    },
  },
```

Delete the old `expertHandoff` block and the `ExpertHandoffSession` interface.

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run typecheck
```

Expected: FAIL, pointing at `frontend/app/dashboard/consultations/*` — those files still import the deleted names. That is expected and Task 11 fixes it. Do not commit yet.

---

### Task 11: The Intake table

**Files:**
- Create: `frontend/app/dashboard/intake/columns.ts`
- Create: `frontend/app/dashboard/intake/IntakeTable.tsx`
- Create: `frontend/app/dashboard/intake/page.tsx`
- Modify: `frontend/app/dashboard/consultations/page.tsx` (becomes a redirect)
- Delete: `frontend/app/dashboard/consultations/ConsultationDetails.tsx`

**Interfaces:**
- Consumes: `api.intake`, `IntakeSession` from Task 10.
- Produces: `deriveColumns(rows: IntakeSession[]): { key: string; label: string }[]` in `columns.ts`; `IntakeTable` and the page component.

- [ ] **Step 1: Write the column-derivation module**

Create `frontend/app/dashboard/intake/columns.ts`:

```ts
import { IntakeSession } from "@/lib/api";

export interface FieldColumn {
  key: string;
  label: string;
}

function prettify(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Union of every field key present across the given rows, first-seen order.
 * A key's label comes from the most recent row whose snapshot defines it, so a
 * renamed field reads under its current name while a deleted one keeps the name
 * it was collected under. Mirrors backend build_csv_headers — the two must agree
 * or the export and the screen disagree about what a column means.
 */
export function deriveColumns(rows: IntakeSession[]): FieldColumn[] {
  const order: string[] = [];
  const labels = new Map<string, string>();
  const labelDate = new Map<string, string>();

  const sorted = [...rows].sort((a, b) => a.created_at.localeCompare(b.created_at));

  for (const row of sorted) {
    const schema = new Map((row.field_schema ?? []).map((f) => [f.key, f.label]));
    for (const key of Object.keys(row.collected_data ?? {})) {
      if (!order.includes(key)) order.push(key);
      const snapshotLabel = schema.get(key);
      if (snapshotLabel && row.created_at >= (labelDate.get(key) ?? "")) {
        labels.set(key, snapshotLabel);
        labelDate.set(key, row.created_at);
      }
    }
  }

  const resolved = order.map((key) => ({ key, label: labels.get(key) ?? prettify(key) }));
  const counts = new Map<string, number>();
  for (const { label } of resolved) counts.set(label, (counts.get(label) ?? 0) + 1);

  return resolved.map(({ key, label }) => ({
    key,
    label: (counts.get(label) ?? 0) > 1 ? `${label} (${key})` : label,
  }));
}
```

- [ ] **Step 2: Write the table component**

Create `frontend/app/dashboard/intake/IntakeTable.tsx`:

```tsx
"use client";
import { useEffect, useRef } from "react";
import { IntakeSession } from "@/lib/api";
import { FieldColumn } from "./columns";

const STATUS_BADGE: Record<string, string> = {
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  resolved: "bg-stone-100 text-stone-600 border-stone-200",
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  resolved: "Resolved",
};

interface IntakeTableProps {
  rows: IntakeSession[];
  columns: FieldColumn[];
  visibleKeys: Set<string>;
  selectedId: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  onSelect: (row: IntakeSession) => void;
  onLoadMore: () => void;
}

export function IntakeTable({
  rows, columns, visibleKeys, selectedId, hasMore, loadingMore, onSelect, onLoadMore,
}: IntakeTableProps) {
  const sentinel = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) onLoadMore();
      },
      { rootMargin: "200px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  const shown = columns.filter((c) => visibleKeys.has(c.key));

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border">
            <th className="sticky left-0 z-10 bg-surface px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Lead
            </th>
            <th className="sticky left-[160px] z-10 bg-surface px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Phone
            </th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Status</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Package</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Amount</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Submitted</th>
            {shown.map((col) => (
              <th key={col.key} className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSelected = row.id === selectedId;
            const rowBg = isSelected ? "bg-primary-light/40" : "bg-surface";
            return (
              <tr
                key={row.id}
                onClick={() => onSelect(row)}
                className={`cursor-pointer border-b border-border-subtle hover:bg-surface-subtle ${isSelected ? "bg-primary-light/40" : ""}`}
              >
                <td className={`sticky left-0 z-10 ${rowBg} whitespace-nowrap px-4 py-3 font-label text-sm font-semibold text-ink`}>
                  {row.leads?.name || row.collected_data?.name || "Unknown lead"}
                </td>
                <td className={`sticky left-[160px] z-10 ${rowBg} whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted`}>
                  {row.leads?.phone || "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span className={`inline-flex rounded-full border px-2.5 py-1 font-label text-[10px] font-bold ${STATUS_BADGE[row.status]}`}>
                    {STATUS_LABEL[row.status]}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">{row.package_name || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                  {row.amount_paise ? `₹${(row.amount_paise / 100).toFixed(0)}` : "—"}
                  {row.amount_mismatch && (
                    <span className="ml-1 font-label text-[10px] font-bold text-amber-700" title="Amount paid differs from the package price">
                      ⚠
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted">
                  {new Date(row.created_at).toLocaleDateString()}
                </td>
                {shown.map((col) => (
                  <td key={col.key} className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                    {row.collected_data?.[col.key] || "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div ref={sentinel} className="h-8" />
      {loadingMore && (
        <p className="py-3 text-center font-body text-xs text-ink-muted">Loading more…</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write the page shell**

Create `frontend/app/dashboard/intake/page.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { API_URL, IntakeSession, IntakeStatus, api, getAuthHeaders } from "@/lib/api";
import { IntakeTable } from "./IntakeTable";
import { IntakeDrawer } from "./IntakeDrawer";
import { ColumnPicker } from "./ColumnPicker";
import { deriveColumns } from "./columns";

type Filter = IntakeStatus | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting_payment", label: "Awaiting Payment" },
  { key: "paid", label: "Paid" },
  { key: "resolved", label: "Resolved" },
];

export default function IntakePage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<IntakeSession[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<IntakeSession | null>(null);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());

  const columns = useMemo(() => deriveColumns(rows), [rows]);
  const visibleKeys = useMemo(
    () => new Set(columns.filter((c) => !hiddenKeys.has(c.key)).map((c) => c.key)),
    [columns, hiddenKeys]
  );

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.intake.listSessions({ status: filter, q: query || undefined });
      setRows(page.data);
      setCursor(page.next_cursor);
    } finally {
      setLoading(false);
    }
  }, [filter, query]);

  useEffect(() => {
    setSelected(null);
    loadFirstPage();
  }, [loadFirstPage]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.intake.listSessions({
        status: filter,
        q: query || undefined,
        cursor,
      });
      setRows((prev) => [...prev, ...page.data]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, filter, loadingMore, query]);

  async function downloadCsv() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}${api.intake.csvPath({ status: filter, q: query || undefined })}`, {
      headers: auth,
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `intake-${filter}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <h1 className="font-display text-lg font-bold text-ink">Intake</h1>

        <div className="flex gap-1 rounded-xl border border-border bg-surface-subtle p-1">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded-lg px-3 py-1.5 font-label text-xs font-bold transition-all ${
                filter === key ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name or phone"
          className="rounded-xl border border-border px-3 py-2 font-body text-sm"
        />

        <div className="ml-auto flex items-center gap-2">
          <ColumnPicker columns={columns} hiddenKeys={hiddenKeys} onChange={setHiddenKeys} />
          <button
            type="button"
            onClick={downloadCsv}
            className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 font-label text-xs font-bold text-white hover:bg-primary/90"
          >
            <Download size={12} /> Download CSV
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-3 p-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-xl bg-border-subtle" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center font-body text-sm text-ink-muted">
            {query ? "No leads match that search." : "No intake leads yet."}
          </p>
        ) : (
          <IntakeTable
            rows={rows}
            columns={columns}
            visibleKeys={visibleKeys}
            selectedId={selected?.id ?? null}
            hasMore={Boolean(cursor)}
            loadingMore={loadingMore}
            onSelect={setSelected}
            onLoadMore={loadMore}
          />
        )}
      </div>

      {selected && (
        <IntakeDrawer
          session={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            setSelected(null);
            loadFirstPage();
          }}
        />
      )}
    </div>
  );
}
```

Note the deliberate absence of `usePolling`: a 30s background refresh would reset the accumulated infinite-scroll pages. The drawer's actions call `loadFirstPage` explicitly instead.

- [ ] **Step 4: Turn the old route into a redirect**

Replace the whole of `frontend/app/dashboard/consultations/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default function ConsultationsRedirect() {
  redirect("/dashboard/intake");
}
```

Delete `frontend/app/dashboard/consultations/ConsultationDetails.tsx`.

- [ ] **Step 5: Verify**

```bash
cd frontend && npm run typecheck
```

Expected: FAIL only on the not-yet-created `./IntakeDrawer` and `./ColumnPicker`. Tasks 12 and 13 close those.

---

### Task 12: Column picker

**Files:**
- Create: `frontend/app/dashboard/intake/ColumnPicker.tsx`

**Interfaces:**
- Consumes: `FieldColumn` from Task 11.
- Produces: `ColumnPicker({ columns, hiddenKeys, onChange })`.

- [ ] **Step 1: Write the component**

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { Columns3 } from "lucide-react";
import { FieldColumn } from "./columns";

const STORAGE_KEY = "intake:hidden-columns";

interface ColumnPickerProps {
  columns: FieldColumn[];
  hiddenKeys: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function ColumnPicker({ columns, hiddenKeys, onChange }: ColumnPickerProps) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) onChange(new Set(JSON.parse(stored) as string[]));
    // Restore once on mount; onChange is stable enough for this one-shot read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function toggle(key: string) {
    const next = new Set(hiddenKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
  }

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1.5 font-label text-xs font-bold text-ink hover:bg-surface-subtle"
      >
        <Columns3 size={12} /> Columns
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 max-h-72 w-56 overflow-y-auto rounded-2xl border border-border bg-white p-2 shadow-lg">
          {columns.length === 0 ? (
            <p className="p-2 font-body text-xs text-ink-muted">No field columns yet.</p>
          ) : (
            columns.map((col) => (
              <label
                key={col.key}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-subtle"
              >
                <input
                  type="checkbox"
                  checked={!hiddenKeys.has(col.key)}
                  onChange={() => toggle(col.key)}
                />
                <span className="font-body text-sm text-ink">{col.label}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify**

```bash
cd frontend && npm run lint
```

Expected: PASS. Any unused import fails this — remove it rather than disabling the rule.

---

### Task 13: Intake drawer

**Files:**
- Create: `frontend/app/dashboard/intake/IntakeDrawer.tsx`

**Interfaces:**
- Consumes: `api.intake.resolveSession`, `api.intake.changePackage` from Task 10.
- Produces: `IntakeDrawer({ session, onClose, onChanged })`.

- [ ] **Step 1: Write the component**

```tsx
"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, Copy, Loader2, Phone, X } from "lucide-react";
import { API_URL, IntakeSession, api, getAuthHeaders } from "@/lib/api";

interface IntakePackageOption {
  key: string;
  name: string;
  amount_paise: number;
}

function labelFor(session: IntakeSession, key: string): string {
  const snapshot = (session.field_schema ?? []).find((f) => f.key === key);
  if (snapshot) return snapshot.label;
  return key.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

interface IntakeDrawerProps {
  session: IntakeSession;
  onClose: () => void;
  onChanged: () => void;
}

export function IntakeDrawer({ session, onClose, onChanged }: IntakeDrawerProps) {
  const [busy, setBusy] = useState(false);
  const [packages, setPackages] = useState<IntakePackageOption[]>([]);
  const entries = Object.entries(session.collected_data ?? {});
  const canChangePackage = session.status === "awaiting_payment";

  useEffect(() => {
    if (!canChangePackage) return;
    (async () => {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const config = await res.json();
        setPackages(config.packages ?? []);
      }
    })();
  }, [canChangePackage]);

  async function resolve() {
    setBusy(true);
    try {
      await api.intake.resolveSession(session.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function changePackage(key: string) {
    setBusy(true);
    try {
      await api.intake.changePackage(session.id, key);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/20" onClick={onClose}>
      <aside
        className="h-full w-[420px] overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        aria-label="Intake details"
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="font-display text-base font-bold text-ink">
              {session.leads?.name || session.collected_data?.name || "Unknown lead"}
            </h2>
            <div className="mt-0.5 flex items-center gap-1 font-body text-xs text-ink-muted">
              <Phone size={11} />
              {session.leads?.phone || "—"}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={16} className="text-ink-muted" />
          </button>
        </div>

        <div className="mb-4 space-y-1 rounded-2xl border border-border p-3">
          <div className="flex justify-between font-body text-sm">
            <span className="text-ink-muted">Package</span>
            <span className="text-ink">{session.package_name || "—"}</span>
          </div>
          <div className="flex justify-between font-body text-sm">
            <span className="text-ink-muted">Amount</span>
            <span className="text-ink">
              {session.amount_paise ? `₹${(session.amount_paise / 100).toFixed(0)}` : "—"}
            </span>
          </div>
          {session.amount_mismatch && (
            <p className="font-body text-xs text-amber-700">
              Paid amount differs from the package price — the lead likely paid a superseded link.
            </p>
          )}
          {session.paid_at && (
            <div className="flex justify-between font-body text-sm">
              <span className="text-ink-muted">Paid at</span>
              <span className="text-ink">{new Date(session.paid_at).toLocaleString()}</span>
            </div>
          )}
          {session.payment_link && (
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(session.payment_link ?? "")}
              className="mt-1 inline-flex items-center gap-1 font-label text-xs font-bold text-primary"
            >
              <Copy size={11} /> Copy payment link
            </button>
          )}
        </div>

        {canChangePackage && packages.length > 1 && (
          <div className="mb-4">
            <label className="mb-1 block font-label text-xs font-bold text-ink-muted" htmlFor="package-select">
              Change package
            </label>
            <select
              id="package-select"
              value={session.package_key ?? ""}
              disabled={busy}
              onChange={(e) => changePackage(e.target.value)}
              className="w-full rounded-xl border border-border px-3 py-2 font-body text-sm"
            >
              {packages.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name} — ₹{(p.amount_paise / 100).toFixed(0)}
                </option>
              ))}
            </select>
            <p className="mt-1 font-body text-xs text-ink-muted">
              Clears the current link. The lead is sent a new one on their next message.
            </p>
          </div>
        )}

        {entries.length === 0 ? (
          <p className="font-body text-xs italic text-ink-muted">No details collected yet.</p>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {entries.map(([key, value]) => (
                <tr key={key} className="border-b border-border-subtle last:border-0">
                  <td className="whitespace-nowrap py-2 pr-4 align-top font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                    {labelFor(session, key)}
                  </td>
                  <td className="py-2 font-body text-sm text-ink">{value || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {session.status === "paid" && (
          <button
            type="button"
            onClick={resolve}
            disabled={busy}
            className="mt-5 inline-flex w-full items-center justify-center gap-1 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90 disabled:opacity-60"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
            Mark Resolved
          </button>
        )}
      </aside>
    </div>
  );
}
```

- [ ] **Step 2: Update the sidebar and more-menu entries**

`frontend/components/sidebar.tsx` lines 211-223 — replace every `/dashboard/consultations` with `/dashboard/intake` and the visible label `Consultations` with `Intake`. Keep the `Headset` icon and the permission/feature gates unchanged.

`frontend/components/MoreMenu.tsx` line 38:

```tsx
  { href: "/dashboard/intake", icon: Headset, label: "Intake", permissionAny: ["conversations.view", "conversations.reply"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run lint && npm run typecheck && npm run build
```

Expected: all three PASS.

- [ ] **Step 4: Prove nothing still points at the old page**

```bash
cd "/Users/prem/Documents/Aira AI"
grep -rn "expertHandoff\|ExpertHandoffSession\|dashboard/consultations" frontend/app frontend/components frontend/lib
```

Expected: exactly one hit — the redirect stub at `frontend/app/dashboard/consultations/page.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: intake table with column picker, CSV export, and detail drawer"
```

---

### Task 14: End-to-end verification

No code. This task is the evidence that the previous thirteen actually work. Do not report the feature done before every box here is ticked with real output.

**Files:** none.

- [ ] **Step 1: Full backend suite**

```bash
cd backend && pytest
```

Record the pass count. Expected: PASS, zero failures.

- [ ] **Step 2: Frontend gates**

```bash
cd frontend && npm run lint && npm run typecheck && npm run build
```

Expected: all PASS.

- [ ] **Step 3: Prove the legacy Razorpay webhook path still routes**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BACKEND_URL/api/v1/expert-handoff/razorpay-webhook" \
  -H "Content-Type: application/json" -d '{}'
```

Expected: `400` (invalid JSON body rejected by the handler), **not** `404`. A 404 means the alias mount is missing and live payments would break.

- [ ] **Step 4: Configure three packages on the astrology tenant**

In Settings → Automations → Paid Expert Handoff, add Basic / Premium / VIP with distinct low test prices (₹10 / ₹11 / ₹12) and set the service noun. Save. Confirm the save returns 200 and reload the page to confirm persistence.

- [ ] **Step 5: Live WhatsApp run**

From a real handset, run the full flow: trigger message → offer → the package list arrives with all three names and correct prices → reply "premium" → fields collected → confirm → payment link for ₹11 → pay it.

Confirm each of:
- the package list message shows prices matching config exactly
- the receipt uses the configured service noun
- the row appears in Intake as Paid, package Premium, amount ₹11
- the bell notification fires and says "check Intake"

- [ ] **Step 6: Live package-change check**

Start a second lead, get to `awaiting_payment` on Basic, then change the package to VIP in the drawer. Confirm the payment link clears and a new one is issued on the lead's next message.

- [ ] **Step 7: Field-drift check — the thing this was built for**

Add two fields (Gender, Age) to the tenant config. Run one more lead through. Then confirm in the Intake table:
- the older rows show `—` under Gender and Age
- the new row shows values
- no row's existing labels changed

- [ ] **Step 8: CSV check**

Download the CSV for `All` and open it. Confirm the header row carries the fixed columns plus every field key across all rows, that hidden columns are still present in the file, and that the paid/awaiting rows are distinguishable by the Status column.

- [ ] **Step 9: Screenshots**

Capture and review — do not just describe them:
- the Intake table with the wide field set, scrolled fully left and fully right, showing the sticky Lead/Phone columns holding position
- the drawer open on a paid row
- the Settings tab row showing `Integrations`

- [ ] **Step 10: Record the migration in the decisions log**

Append to `.agents/decisions/log.md` a dated entry naming migrations 176 and 177, the table rename, the legacy route alias and the condition for removing it, and the packages/service-noun config change.

- [ ] **Step 11: Commit**

```bash
git add .agents/decisions/log.md
git commit -m "docs: record intake rename and packages migration"
```

---

## Deferred, deliberately

- **Per-package field sets.** D18 keeps one shared field list. The per-row `field_schema` snapshot means adding this later is additive.
- **Removing the legacy `/api/v1/expert-handoff` prefix.** Blocked on updating the webhook URL in the Razorpay dashboard by hand. Until then both prefixes serve.
- **Renaming `reply_source = "expert_handoff"` on message rows.** Changing it would orphan historical rows written under the old value for no user-visible gain.
- **A tenant-renamable page label.** D2 chose a fixed "Intake". If a client pushes back on the word, that becomes its own small change.
