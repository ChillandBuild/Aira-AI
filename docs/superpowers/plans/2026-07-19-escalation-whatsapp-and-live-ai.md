# Escalation WhatsApp Alerts + Live AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify the team on WhatsApp when the AI escalates a conversation, and stop the AI going silent on the customer while they wait for a human.

**Architecture:** Reuses the existing `pending_whatsapp_alerts` delayed-send queue with a new `alert_type` discriminator, so escalation alerts share one scheduler job and one incident path with the existing segment-change alerts. Escalation stops setting `ai_enabled = False`; instead the AI receives an escalation context block plus tenant business hours in its system prompt, so it answers situationally ("contacted shortly" in-hours, "call you tomorrow" out-of-hours).

**Tech Stack:** FastAPI (`backend/app/`), Next.js 14 (`frontend/app/dashboard/`), Supabase (Postgres + RLS), Meta WhatsApp Cloud API, pytest, Python `zoneinfo`.

**Spec:** `docs/superpowers/specs/2026-07-19-escalation-whatsapp-alerts-design.md`

## Global Constraints

- Backend tests: `cd backend && pytest`. Frontend verification is **both** `cd frontend && npm run lint` **and** `npm run typecheck` — CI runs `next lint`, and `tsc` alone passes code that CI rejects (unused imports, `any`).
- `notification_config` and `business_hours` are JSON blobs in the `app_settings` key/value table (`tenant_id`, `key`, `value`, `is_secret`), upserted with `on_conflict="tenant_id,key"`. They are **not** columns. Only `pending_whatsapp_alerts` needs a migration.
- Every new notification / business-hours code path must be wrapped so it can never prevent a handover from being created or an AI reply from being sent. Fail open, log an incident.
- Segment codes are `A=Hot, B=Warm, C=Cold, D=Disqualified`.
- Brand color for active interactive UI state is `primary` (violet `#5b21b6`). Emerald is reserved for "Approved"/status-positive semantics — do not use it for toggles or active states.
- Phone numbers are E.164: `^\+[1-9]\d{6,14}$`.
- Default timezone is `Asia/Kolkata`.
- New settings cards follow the existing pattern in `NotificationConfigPanel.tsx`: `card rounded-3xl`, the local `Toggle` component, `font-label`/`font-body` type classes.

---

### Task 1: Migration for escalation alert columns

**Files:**
- Create: `backend/supabase/migrations/142_escalation_whatsapp_alerts.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: `pending_whatsapp_alerts` columns `alert_type text NOT NULL DEFAULT 'segment_change'`, `handover_id uuid NULL`, `assigned_to_at_queue uuid NULL`, `escalation_reason text NULL`, and `to_segment` relaxed to nullable. Tasks 4 and 5 write and read these.

- [ ] **Step 1: Write the migration**

```sql
-- Extend pending_whatsapp_alerts to carry escalation alerts alongside
-- segment-change alerts. One queue, one scheduler job, one incident path.

ALTER TABLE public.pending_whatsapp_alerts
    ADD COLUMN IF NOT EXISTS alert_type text NOT NULL DEFAULT 'segment_change',
    ADD COLUMN IF NOT EXISTS handover_id uuid REFERENCES public.chat_handovers(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS assigned_to_at_queue uuid,
    ADD COLUMN IF NOT EXISTS escalation_reason text;

-- Escalation rows have no segment transition, so to_segment can no longer be
-- mandatory. Existing rows are unaffected.
ALTER TABLE public.pending_whatsapp_alerts
    ALTER COLUMN to_segment DROP NOT NULL;

ALTER TABLE public.pending_whatsapp_alerts
    ADD CONSTRAINT pending_wa_alert_type_check
    CHECK (alert_type IN ('segment_change', 'escalation'));

-- A segment_change row must carry a segment; an escalation row must carry a handover.
ALTER TABLE public.pending_whatsapp_alerts
    ADD CONSTRAINT pending_wa_shape_check
    CHECK (
        (alert_type = 'segment_change' AND to_segment IS NOT NULL)
        OR (alert_type = 'escalation' AND handover_id IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS idx_pending_wa_handover
    ON public.pending_whatsapp_alerts (handover_id)
    WHERE handover_id IS NOT NULL;
```

The `DEFAULT 'segment_change'` is what backfills every existing row correctly — no separate `UPDATE` is needed.

- [ ] **Step 2: Apply the migration**

Apply via the Supabase MCP `apply_migration` tool (name: `142_escalation_whatsapp_alerts`) or the SQL editor.

- [ ] **Step 3: Verify the schema**

```sql
SELECT column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'pending_whatsapp_alerts'
ORDER BY ordinal_position;
```

Expected: `alert_type` present with default `'segment_change'::text`, `to_segment` now `is_nullable = YES`, and `handover_id` / `assigned_to_at_queue` / `escalation_reason` present and nullable.

- [ ] **Step 4: Commit**

```bash
git add backend/supabase/migrations/142_escalation_whatsapp_alerts.sql
git commit -m "feat(db): add escalation columns to pending_whatsapp_alerts"
```

---

### Task 2: Escalation notification config block

**Files:**
- Modify: `backend/app/services/notification_config.py:9-62`
- Modify: `backend/app/routes/notifications.py`
- Test: `backend/tests/test_notification_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `get_notification_config(tenant_id, db=None)` now returns a `"whatsapp_escalation_notifications"` key: `{"enabled": bool, "recipient_phones": list[str], "template_id": str | None, "target_segments": list[str], "delay_minutes": int}`. Task 4 reads it.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_notification_config.py`:

```python
def test_escalation_block_defaults_when_absent():
    """A stored blob with no escalation key still returns full defaults."""
    import json
    from unittest.mock import MagicMock
    from app.services.notification_config import get_notification_config

    db = MagicMock()
    stored = json.dumps({"push_enabled": False})
    (db.table.return_value.select.return_value.eq.return_value.eq.return_value
     .maybe_single.return_value.execute.return_value.data) = {"value": stored}

    cfg = get_notification_config("tenant-1", db=db)
    esc = cfg["whatsapp_escalation_notifications"]
    assert esc["enabled"] is False
    assert esc["target_segments"] == ["A"]
    assert esc["delay_minutes"] == 3
    assert esc["recipient_phones"] == []
    assert esc["template_id"] is None


def test_escalation_block_merges_partial_stored_value():
    """A partial stored escalation block keeps defaults for missing keys."""
    import json
    from unittest.mock import MagicMock
    from app.services.notification_config import get_notification_config

    db = MagicMock()
    stored = json.dumps({
        "whatsapp_escalation_notifications": {"enabled": True, "template_id": "tmpl-9"}
    })
    (db.table.return_value.select.return_value.eq.return_value.eq.return_value
     .maybe_single.return_value.execute.return_value.data) = {"value": stored}

    esc = get_notification_config("tenant-1", db=db)["whatsapp_escalation_notifications"]
    assert esc["enabled"] is True
    assert esc["template_id"] == "tmpl-9"
    assert esc["delay_minutes"] == 3          # default survived
    assert esc["target_segments"] == ["A"]    # default survived
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_notification_config.py -k escalation -v`
Expected: FAIL with `KeyError: 'whatsapp_escalation_notifications'`

- [ ] **Step 3: Add the default and the merge line**

In `backend/app/services/notification_config.py`, add to `_NOTIFICATION_CONFIG_DEFAULT` immediately after the `whatsapp_notifications` entry:

```python
    "whatsapp_escalation_notifications": {
        "enabled": False,
        "recipient_phones": [],
        "template_id": None,
        "target_segments": ["A"],
        "delay_minutes": 3,
    },
```

In `get_notification_config`, add to the `merged` seed dict:

```python
        "whatsapp_escalation_notifications": dict(
            _NOTIFICATION_CONFIG_DEFAULT["whatsapp_escalation_notifications"]
        ),
```

and add this line in the deep-merge body, right after the `whatsapp_notifications` merge:

```python
                merged["whatsapp_escalation_notifications"] = {
                    **merged["whatsapp_escalation_notifications"],
                    **(stored.get("whatsapp_escalation_notifications") or {}),
                }
```

**Both** edits are required. Adding the default without the merge line makes the block silently revert to defaults on every read.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_notification_config.py -v`
Expected: PASS, including the pre-existing tests.

- [ ] **Step 5: Add route validation**

In `backend/app/routes/notifications.py`, extend the config Pydantic model with the new block and validate it in the save path, mirroring how `whatsapp_notifications` is handled:

```python
import re

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_escalation_block(block: dict) -> None:
    """Raise HTTPException(400) if the escalation notification block is malformed."""
    phones = block.get("recipient_phones") or []
    bad_phones = [p for p in phones if not _E164.match(p)]
    if bad_phones:
        raise HTTPException(status_code=400, detail=f"Invalid phone numbers: {bad_phones}")

    segs = block.get("target_segments") or []
    bad_segs = [s for s in segs if s not in {"A", "B", "C", "D"}]
    if bad_segs:
        raise HTTPException(status_code=400, detail=f"Invalid segments: {bad_segs}")

    delay = block.get("delay_minutes", 3)
    if not isinstance(delay, int) or not (0 <= delay <= 1440):
        raise HTTPException(status_code=400, detail="delay_minutes must be an integer 0-1440")
```

Call `_validate_escalation_block(payload["whatsapp_escalation_notifications"])` in the save handler when the key is present.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/notification_config.py backend/app/routes/notifications.py backend/tests/test_notification_config.py
git commit -m "feat(notifications): add whatsapp_escalation_notifications config block"
```

---

### Task 3: Business hours service and routes

**Files:**
- Create: `backend/app/services/business_hours.py`
- Modify: `backend/app/routes/app_settings.py` (add routes next to `/inbox-config` at line 761)
- Test: `backend/tests/test_business_hours.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `get_business_hours(tenant_id: str, db=None) -> dict`
  - `save_business_hours(tenant_id: str, config: dict) -> None`
  - `is_within_business_hours(cfg: dict, now: datetime | None = None) -> bool`
  - `describe_hours(cfg: dict) -> str`
  - `next_open_description(cfg: dict, now: datetime | None = None) -> str`
  - Routes `GET /api/v1/settings/business-hours` and `PATCH /api/v1/settings/business-hours`

  Task 7 consumes all four helpers; Task 9 consumes the routes.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_business_hours.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone

from app.services.business_hours import (
    is_within_business_hours,
    describe_hours,
    next_open_description,
)


def _cfg(**overrides):
    base = {
        "enabled": True,
        "timezone": "Asia/Kolkata",
        "open_time": "09:00",
        "close_time": "19:00",
        "working_days": [1, 2, 3, 4, 5, 6],
    }
    base.update(overrides)
    return base


# 2026-07-20 is a Monday. 06:30 UTC == 12:00 IST (in hours).
MON_MIDDAY_UTC = datetime(2026, 7, 20, 6, 30, tzinfo=timezone.utc)
# 2026-07-20 22:00 UTC == 03:30 IST Tuesday (out of hours).
MON_NIGHT_UTC = datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc)
# 2026-07-19 is a Sunday. 06:30 UTC == 12:00 IST.
SUN_MIDDAY_UTC = datetime(2026, 7, 19, 6, 30, tzinfo=timezone.utc)


def test_inside_window_on_working_day_is_open():
    assert is_within_business_hours(_cfg(), now=MON_MIDDAY_UTC) is True


def test_outside_window_is_closed():
    assert is_within_business_hours(_cfg(), now=MON_NIGHT_UTC) is False


def test_non_working_day_is_closed():
    assert is_within_business_hours(_cfg(), now=SUN_MIDDAY_UTC) is False


def test_disabled_config_is_always_closed():
    assert is_within_business_hours(_cfg(enabled=False), now=MON_MIDDAY_UTC) is False


def test_timezone_is_respected():
    """22:00 UTC is out of hours in IST even though it is mid-evening in UTC."""
    assert is_within_business_hours(_cfg(), now=MON_NIGHT_UTC) is False
    assert is_within_business_hours(
        _cfg(timezone="UTC", open_time="20:00", close_time="23:00"), now=MON_NIGHT_UTC
    ) is True


def test_midnight_spanning_window():
    cfg = _cfg(open_time="20:00", close_time="04:00")
    # 22:00 UTC == 03:30 IST, inside a 20:00->04:00 window.
    assert is_within_business_hours(cfg, now=MON_NIGHT_UTC) is True


def test_describe_hours_contiguous_days():
    assert describe_hours(_cfg()) == "Monday to Saturday, 9:00 AM to 7:00 PM IST"


def test_next_open_is_tomorrow_after_close_on_a_working_day():
    # 15:00 UTC == 20:30 IST Monday, after close; Tuesday is a working day.
    after_close = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    assert next_open_description(_cfg(), now=after_close) == "tomorrow"


def test_next_open_is_later_today_before_opening():
    # 02:00 UTC == 07:30 IST Monday, before the 09:00 open.
    before_open = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    assert next_open_description(_cfg(), now=before_open) == "later today"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_business_hours.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.business_hours'`

- [ ] **Step 3: Write the service**

Create `backend/app/services/business_hours.py`:

```python
import json
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_DEFAULT: dict = {
    "enabled": True,
    "timezone": "Asia/Kolkata",
    "open_time": "09:00",
    "close_time": "19:00",
    "working_days": [1, 2, 3, 4, 5, 6],  # ISO weekday, Mon=1 .. Sun=7
}

_DAY_NAMES = {
    1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
    5: "Friday", 6: "Saturday", 7: "Sunday",
}


def get_business_hours(tenant_id: str, db=None) -> dict:
    """Return business_hours from app_settings, merged with defaults."""
    db = db or get_supabase()
    merged = dict(_DEFAULT)
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "business_hours")
            .maybe_single()
            .execute()
        )
        if row and row.data and row.data.get("value"):
            stored = json.loads(row.data["value"])
            if isinstance(stored, dict):
                merged.update(stored)
    except Exception as e:
        logger.warning(f"get_business_hours failed for {tenant_id}: {e}")
    return merged


def save_business_hours(tenant_id: str, config: dict) -> None:
    """Persist business_hours to app_settings."""
    db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "business_hours",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


def _parse_hhmm(value: str, fallback: str) -> time:
    try:
        hh, mm = (value or fallback).split(":")
        return time(int(hh), int(mm))
    except Exception:
        hh, mm = fallback.split(":")
        return time(int(hh), int(mm))


def _tz(cfg: dict) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _local_now(cfg: dict, now: datetime | None) -> datetime:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(_tz(cfg))


def is_within_business_hours(cfg: dict, now: datetime | None = None) -> bool:
    """True when the tenant's office is currently open.

    False when disabled, on a non-working day, or outside the open/close window.
    Handles windows that span midnight (open 20:00, close 04:00).
    """
    if not cfg.get("enabled"):
        return False
    local = _local_now(cfg, now)
    if local.isoweekday() not in (cfg.get("working_days") or []):
        return False

    open_t = _parse_hhmm(cfg.get("open_time"), "09:00")
    close_t = _parse_hhmm(cfg.get("close_time"), "19:00")
    current = local.time()

    if open_t == close_t:
        return False
    if open_t < close_t:
        return open_t <= current < close_t
    return current >= open_t or current < close_t


def _fmt12(value: str, fallback: str) -> str:
    t = _parse_hhmm(value, fallback)
    suffix = "AM" if t.hour < 12 else "PM"
    hour12 = t.hour % 12 or 12
    return f"{hour12}:{t.minute:02d} {suffix}"


def describe_hours(cfg: dict) -> str:
    """Human-readable office hours for the AI prompt, e.g.
    'Monday to Saturday, 9:00 AM to 7:00 PM IST'."""
    days = sorted(cfg.get("working_days") or [])
    if not days:
        return "not currently published"

    if days == list(range(days[0], days[-1] + 1)) and len(days) > 1:
        day_str = f"{_DAY_NAMES[days[0]]} to {_DAY_NAMES[days[-1]]}"
    else:
        day_str = ", ".join(_DAY_NAMES[d] for d in days)

    tz_label = datetime.now(_tz(cfg)).tzname() or ""
    open_s = _fmt12(cfg.get("open_time"), "09:00")
    close_s = _fmt12(cfg.get("close_time"), "19:00")
    return f"{day_str}, {open_s} to {close_s} {tz_label}".strip()


def next_open_description(cfg: dict, now: datetime | None = None) -> str:
    """When the office next opens, phrased for a customer:
    'later today', 'tomorrow', or 'on Monday'."""
    working = set(cfg.get("working_days") or [])
    if not working:
        return "as soon as we reopen"

    local = _local_now(cfg, now)
    open_t = _parse_hhmm(cfg.get("open_time"), "09:00")

    if local.isoweekday() in working and local.time() < open_t:
        return "later today"

    for offset in range(1, 8):
        candidate = local + timedelta(days=offset)
        if candidate.isoweekday() in working:
            return "tomorrow" if offset == 1 else f"on {_DAY_NAMES[candidate.isoweekday()]}"
    return "as soon as we reopen"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_business_hours.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 5: Add the routes**

In `backend/app/routes/app_settings.py`, add next to the `/inbox-config` routes (around line 790), following the same dependency and validation shape:

```python
class BusinessHoursUpdate(BaseModel):
    enabled: Optional[bool] = None
    timezone: Optional[str] = None
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    working_days: Optional[List[int]] = None


@router.get("/business-hours")
async def get_business_hours_route(ctx: dict = Depends(require_settings_read)):
    from app.services.business_hours import get_business_hours
    return get_business_hours(ctx["tenant_id"])


@router.patch("/business-hours")
async def patch_business_hours(
    payload: BusinessHoursUpdate, ctx: dict = Depends(require_settings_manage)
):
    from zoneinfo import ZoneInfo
    from app.services.business_hours import get_business_hours, save_business_hours

    tenant_id = ctx["tenant_id"]
    current = get_business_hours(tenant_id)
    patch = payload.model_dump(exclude_none=True)

    if "working_days" in patch:
        bad = [d for d in patch["working_days"] if d not in {1, 2, 3, 4, 5, 6, 7}]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid working_days: {bad}")

    for key in ("open_time", "close_time"):
        if key in patch:
            try:
                hh, mm = patch[key].split(":")
                if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                    raise ValueError
            except Exception:
                raise HTTPException(status_code=400, detail=f"{key} must be HH:MM")

    if "timezone" in patch:
        try:
            ZoneInfo(patch["timezone"])
        except Exception:
            raise HTTPException(status_code=400, detail="Unknown timezone")

    merged = {**current, **patch}
    save_business_hours(tenant_id, merged)
    return merged
```

Confirm `BaseModel`, `Optional`, `List`, and `HTTPException` are already imported in the file; add any that are missing.

- [ ] **Step 6: Verify the routes respond**

Run: `cd backend && uvicorn app.main:app --reload`, then in another shell hit `GET /api/v1/settings/business-hours` with a valid auth header.
Expected: the default JSON blob (`enabled: true`, `Asia/Kolkata`, `09:00`, `19:00`, days 1-6).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/business_hours.py backend/app/routes/app_settings.py backend/tests/test_business_hours.py
git commit -m "feat(settings): add tenant business hours config and helpers"
```

---

### Task 4: Queue escalation WhatsApp alerts

**Files:**
- Modify: `backend/app/services/whatsapp_notify.py`
- Test: `backend/tests/test_escalation_whatsapp.py`

**Interfaces:**
- Consumes: `get_notification_config(...)["whatsapp_escalation_notifications"]` from Task 2; the columns from Task 1.
- Produces:
  - `queue_escalation_whatsapp_alert(db, tenant_id: str, lead_id: str, handover_id: str, reason: str, assigned_to: str | None) -> None`
  - `_build_escalation_components(template: dict, lead: dict, reason: str) -> list[dict] | None`

  Task 5 consumes `_build_escalation_components`; Task 6 calls `queue_escalation_whatsapp_alert`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_escalation_whatsapp.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from unittest.mock import MagicMock

from app.services import whatsapp_notify


def _esc_config(**overrides):
    base = {
        "enabled": True,
        "recipient_phones": ["+15550001111"],
        "template_id": "tmpl-esc",
        "target_segments": ["A"],
        "delay_minutes": 3,
    }
    base.update(overrides)
    return base


def _make_db(esc_config: dict | None, lead_segment: str = "A"):
    """Fake Supabase client: app_settings returns the escalation config,
    leads returns a row with the given segment, and inserts are recorded."""
    db = MagicMock()
    inserts: list[dict] = []
    pwa_table = MagicMock()
    pwa_table.insert.side_effect = lambda row: (inserts.append(row), MagicMock())[1]

    def table_selector(name):
        if name == "app_settings":
            t = MagicMock()
            value = json.dumps(
                {"whatsapp_escalation_notifications": esc_config}
            ) if esc_config is not None else None
            data = {"value": value} if value is not None else None
            (t.select.return_value.eq.return_value.eq.return_value
             .maybe_single.return_value.execute.return_value.data) = data
            return t
        if name == "leads":
            t = MagicMock()
            (t.select.return_value.eq.return_value.limit.return_value
             .execute.return_value.data) = [{"id": "lead-1", "segment": lead_segment}]
            return t
        if name == "pending_whatsapp_alerts":
            return pwa_table
        return MagicMock()

    db.table.side_effect = table_selector
    db._inserts = inserts
    return db


def test_queue_noop_when_disabled():
    db = _make_db(_esc_config(enabled=False))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "user asked for human", None
    )
    assert db._inserts == []


def test_queue_noop_when_segment_not_targeted():
    db = _make_db(_esc_config(target_segments=["A"]), lead_segment="C")
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db._inserts == []


def test_queue_noop_without_template_or_phones():
    db = _make_db(_esc_config(template_id=None))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db._inserts == []

    db2 = _make_db(_esc_config(recipient_phones=[]))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db2, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db2._inserts == []


def test_queue_happy_path_records_row_with_snapshot():
    db = _make_db(_esc_config())
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "user asked for human", "caller-7"
    )
    assert len(db._inserts) == 1
    row = db._inserts[0]
    assert row["alert_type"] == "escalation"
    assert row["handover_id"] == "ho-1"
    assert row["assigned_to_at_queue"] == "caller-7"
    assert row["escalation_reason"] == "user asked for human"
    assert row["status"] == "pending"
    assert row["to_segment"] is None
    assert "send_at" in row


def test_build_escalation_components_maps_four_variables():
    template = {"body_text": "Lead {{1}} ({{2}}) escalated: {{3}} — {{4}}"}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+919999999999"}
    comps = whatsapp_notify._build_escalation_components(template, lead, "user asked for human")
    params = comps[0]["parameters"]
    assert [p["text"] for p in params] == [
        "Asha",
        "+919999999999",
        "user asked for human",
        "https://aira.ai/dashboard/conversations?lead_id=lead-1",
    ]


def test_build_escalation_components_returns_none_without_variables():
    template = {"body_text": "A lead needs attention."}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+91999"}
    assert whatsapp_notify._build_escalation_components(template, lead, "reason") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_escalation_whatsapp.py -v`
Expected: FAIL with `AttributeError: module 'app.services.whatsapp_notify' has no attribute 'queue_escalation_whatsapp_alert'`

- [ ] **Step 3: Implement both functions**

Add to `backend/app/services/whatsapp_notify.py`, after `_build_components`:

```python
def _build_escalation_components(template: dict, lead: dict, reason: str) -> list[dict] | None:
    """Map ordinal {{n}} placeholders to escalation values.

    Returns None when the template has no variables — nothing safe to send.
    """
    body_text = template.get("body_text") or ""
    indices = sorted(set(int(m) for m in re.findall(r"\{\{(\d+)\}\}", body_text)))
    if not indices:
        return None

    candidate_values = [
        lead.get("name") or "Lead",
        lead.get("phone") or "",
        (reason or "")[:120],
        f"https://aira.ai/dashboard/conversations?lead_id={lead['id']}",
    ]
    values = candidate_values[: len(indices)]
    return [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]


def queue_escalation_whatsapp_alert(
    db,
    tenant_id: str,
    lead_id: str,
    handover_id: str,
    reason: str,
    assigned_to: str | None,
) -> None:
    """Queue a delayed WhatsApp alert for a newly created chat handover.

    No cooldown check is needed: _trigger_chat_escalation returns early when an
    open handover already exists, so there is exactly one alert per handover.
    Never raises — escalation must not fail because of a notification.
    """
    try:
        cfg = get_notification_config(tenant_id, db=db).get(
            "whatsapp_escalation_notifications"
        ) or {}

        if not cfg.get("enabled"):
            return
        template_id = cfg.get("template_id")
        recipient_phones = cfg.get("recipient_phones") or []
        if not template_id or not recipient_phones:
            return

        lead_res = (
            db.table("leads")
            .select("id,segment")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        lead = (lead_res.data or [None])[0]
        if not lead:
            return
        if lead.get("segment") not in (cfg.get("target_segments") or []):
            return

        delay_minutes = cfg.get("delay_minutes")
        if delay_minutes is None:
            delay_minutes = 3
        send_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

        db.table("pending_whatsapp_alerts").insert({
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "handover_id": handover_id,
            "assigned_to_at_queue": assigned_to,
            "escalation_reason": reason,
            "alert_type": "escalation",
            "to_segment": None,
            "from_segment": None,
            "send_at": send_at.isoformat(),
            "status": "pending",
        }).execute()

        logger.info(
            "Queued escalation WhatsApp alert lead=%s handover=%s send_at=%s",
            lead_id, handover_id, send_at,
        )
    except Exception as e:
        logger.exception(
            "queue_escalation_whatsapp_alert failed tenant=%s lead=%s", tenant_id, lead_id
        )
        _log_incident(db, tenant_id, {
            "lead_id": lead_id,
            "handover_id": handover_id,
            "reason": "escalation_queue_failed",
            "error": str(e)[:500],
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_escalation_whatsapp.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/whatsapp_notify.py backend/tests/test_escalation_whatsapp.py
git commit -m "feat(notifications): queue escalation WhatsApp alerts"
```

---

### Task 5: Send escalation alerts with cancel-if-claimed

**Files:**
- Modify: `backend/app/services/whatsapp_notify.py:163-291` (`process_due_whatsapp_alerts`)
- Test: `backend/tests/test_escalation_whatsapp.py`

**Interfaces:**
- Consumes: `_build_escalation_components` and the queued row shape from Task 4.
- Produces: `_process_escalation_alert(db, alert: dict) -> None`, called by `process_due_whatsapp_alerts` when `alert["alert_type"] == "escalation"`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_escalation_whatsapp.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch


def _alert_row(**overrides):
    row = {
        "id": "alert-1",
        "tenant_id": "tenant-1",
        "lead_id": "lead-1",
        "handover_id": "ho-1",
        "assigned_to_at_queue": None,
        "escalation_reason": "user asked for human",
        "alert_type": "escalation",
        "to_segment": None,
    }
    row.update(overrides)
    return row


def _make_process_db(handover_row, esc_config=None, updates=None):
    """Fake client for process_due_whatsapp_alerts covering one escalation alert."""
    db = MagicMock()
    updates = updates if updates is not None else []

    def table_selector(name):
        t = MagicMock()
        if name == "pending_whatsapp_alerts":
            (t.select.return_value.eq.return_value.lte.return_value.order
             .return_value.limit.return_value.execute.return_value.data) = [_alert_row()]
            t.update.side_effect = lambda payload: (
                updates.append(payload), MagicMock()
            )[1]
        elif name == "chat_handovers":
            (t.select.return_value.eq.return_value.limit.return_value
             .execute.return_value.data) = [handover_row] if handover_row else []
        elif name == "app_settings":
            value = json.dumps({
                "whatsapp_escalation_notifications": esc_config or _esc_config()
            })
            (t.select.return_value.eq.return_value.eq.return_value.maybe_single
             .return_value.execute.return_value.data) = {"value": value}
        elif name == "leads":
            (t.select.return_value.eq.return_value.eq.return_value.limit
             .return_value.execute.return_value.data) = [
                {"id": "lead-1", "name": "Asha", "phone": "+919999999999", "segment": "A"}
            ]
        elif name == "message_templates":
            (t.select.return_value.eq.return_value.eq.return_value.eq.return_value
             .limit.return_value.execute.return_value.data) = [{
                "id": "tmpl-esc", "name": "escalation_v1", "language": "en",
                "body_text": "Lead {{1}} ({{2}}) escalated: {{3}} — {{4}}",
                "status": "APPROVED",
             }]
        return t

    db.table.side_effect = table_selector
    db._updates = updates
    return db


def test_cancelled_when_handover_resolved():
    db = _make_process_db({"id": "ho-1", "status": "resolved", "assigned_to": None})
    with patch.object(whatsapp_notify, "get_supabase", return_value=db), \
         patch.object(whatsapp_notify, "_dispatch_alerts", new=AsyncMock()) as dispatch:
        asyncio.run(whatsapp_notify.process_due_whatsapp_alerts())
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_cancelled_when_handover_claimed():
    db = _make_process_db({"id": "ho-1", "status": "pending", "assigned_to": "caller-9"})
    with patch.object(whatsapp_notify, "get_supabase", return_value=db), \
         patch.object(whatsapp_notify, "_dispatch_alerts", new=AsyncMock()) as dispatch:
        asyncio.run(whatsapp_notify.process_due_whatsapp_alerts())
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_sent_when_still_pending_and_unclaimed():
    db = _make_process_db({"id": "ho-1", "status": "pending", "assigned_to": None})
    with patch.object(whatsapp_notify, "get_supabase", return_value=db), \
         patch.object(whatsapp_notify, "_dispatch_alerts", new=AsyncMock()) as dispatch:
        asyncio.run(whatsapp_notify.process_due_whatsapp_alerts())
    dispatch.assert_called_once()
    assert {"status": "sent"} in db._updates
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_escalation_whatsapp.py -k "cancelled or sent_when" -v`
Expected: FAIL — the escalation branch does not exist, so the segment-change path runs and cancels or errors on the `None` `to_segment`.

- [ ] **Step 3: Add the escalation branch**

In `backend/app/services/whatsapp_notify.py`, extract the escalation handling into its own coroutine and dispatch to it from the loop.

At the top of the per-alert `try` block inside `process_due_whatsapp_alerts`, right after the row is marked `processing`, insert:

```python
                if alert.get("alert_type") == "escalation":
                    await _process_escalation_alert(db, alert)
                    continue
```

Then add the new coroutine after `process_due_whatsapp_alerts`:

```python
async def _process_escalation_alert(db, alert: dict) -> None:
    """Send one due escalation alert, unless the handover was claimed or resolved."""
    alert_id = alert["id"]
    tenant_id = alert["tenant_id"]
    lead_id = alert["lead_id"]
    handover_id = alert.get("handover_id")

    def _cancel():
        db.table("pending_whatsapp_alerts").update(
            {"status": "cancelled"}
        ).eq("id", alert_id).execute()

    ho_res = (
        db.table("chat_handovers")
        .select("id,status,assigned_to")
        .eq("id", handover_id)
        .limit(1)
        .execute()
    )
    handover = (ho_res.data or [None])[0]
    if not handover:
        _cancel()
        return
    if handover.get("status") != "pending":
        _cancel()          # resolved before the delay elapsed
        return
    if handover.get("assigned_to") != alert.get("assigned_to_at_queue"):
        _cancel()          # claimed by a teammate
        return

    cfg = get_notification_config(tenant_id, db=db).get(
        "whatsapp_escalation_notifications"
    ) or {}
    template_id = cfg.get("template_id")
    recipient_phones = cfg.get("recipient_phones") or []
    if not cfg.get("enabled") or not template_id or not recipient_phones:
        _cancel()
        return

    lead_res = (
        db.table("leads")
        .select("id,name,phone,score,segment")
        .eq("id", lead_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    lead = (lead_res.data or [None])[0]
    if not lead:
        _cancel()
        _log_incident(db, tenant_id, {"lead_id": lead_id, "reason": "lead_not_found"})
        return

    template_res = (
        db.table("message_templates")
        .select("id,name,language,body_text,status")
        .eq("id", template_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "APPROVED")
        .limit(1)
        .execute()
    )
    template = (template_res.data or [None])[0]
    if not template:
        db.table("pending_whatsapp_alerts").update(
            {"status": "failed"}
        ).eq("id", alert_id).execute()
        _log_incident(db, tenant_id, {
            "lead_id": lead_id,
            "template_id": template_id,
            "reason": "escalation_template_not_found_or_not_approved",
        })
        return

    components = _build_escalation_components(
        template, lead, alert.get("escalation_reason") or ""
    )
    if components is None:
        db.table("pending_whatsapp_alerts").update(
            {"status": "failed"}
        ).eq("id", alert_id).execute()
        return

    await _dispatch_alerts(recipient_phones, template, components, tenant_id, lead_id)
    db.table("pending_whatsapp_alerts").update(
        {"status": "sent"}
    ).eq("id", alert_id).execute()
```

Also add `alert_type`, `handover_id`, `assigned_to_at_queue`, and `escalation_reason` to whatever column list the main query selects — it currently uses `select("*")`, so no change is needed there. Confirm this before moving on.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_escalation_whatsapp.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the regression guard**

Run: `cd backend && pytest tests/test_whatsapp_notifications.py -v`
Expected: PASS, unchanged — the segment-change path must be untouched.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/whatsapp_notify.py backend/tests/test_escalation_whatsapp.py
git commit -m "feat(notifications): send escalation alerts, cancel if claimed or resolved"
```

---

### Task 6: Wire escalation, and stop pausing the AI

**Files:**
- Modify: `backend/app/services/ai_reply.py:777-806` (`_trigger_chat_escalation`), and the import at line 20
- Modify: `backend/app/routes/chat_handovers.py:136-140` (`resolve_handover`)
- Test: `backend/tests/test_escalation_ai_live.py`

**Interfaces:**
- Consumes: `queue_escalation_whatsapp_alert` from Task 4.
- Produces: escalated leads keep `ai_enabled = True`; `needs_human_attention` remains the sole escalation marker. Task 7 keys its prompt block off `needs_human_attention`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_escalation_ai_live.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inspect

from app.services import ai_reply
from app.routes import chat_handovers


def test_escalation_does_not_disable_ai():
    """_trigger_chat_escalation must not set ai_enabled False — an escalated
    customer should never get silence while waiting for a human."""
    src = inspect.getsource(ai_reply._trigger_chat_escalation)
    assert '"ai_enabled": False' not in src
    assert '"needs_human_attention": True' in src


def test_resolve_does_not_reenable_ai():
    """resolve_handover must not set ai_enabled True — escalation no longer
    disables it, so writing True would clobber a manual admin mute."""
    src = inspect.getsource(chat_handovers.resolve_handover)
    assert '"ai_enabled": True' not in src
    assert '"needs_human_attention": False' in src


def test_escalation_queues_whatsapp_alert():
    """The handover insert is followed by a queued escalation alert."""
    src = inspect.getsource(ai_reply._trigger_chat_escalation)
    assert "queue_escalation_whatsapp_alert" in src


def test_hot_lead_helper_import_removed():
    """should_escalate_hot_lead was dead config — it must not be imported."""
    src = Path(ai_reply.__file__).read_text(encoding="utf-8")
    assert "should_escalate_hot_lead" not in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_escalation_ai_live.py -v`
Expected: FAIL on all four — `ai_enabled: False` is present, `queue_escalation_whatsapp_alert` is not, and the dead import remains.

- [ ] **Step 3: Update `_trigger_chat_escalation`**

In `backend/app/services/ai_reply.py`, change the lead update (currently lines 777-781) to drop `ai_enabled`:

```python
    db.table("leads").update({
        "needs_human_attention": True,
        "escalation_reason": reason,
    }).eq("id", lead_id).execute()
```

Then, after the existing `notify_pool` try/except block (which ends around line 806), append:

```python
    try:
        from app.services.whatsapp_notify import queue_escalation_whatsapp_alert
        queue_escalation_whatsapp_alert(
            db,
            tenant_id=tenant_id,
            lead_id=lead_id,
            handover_id=handover_id,
            reason=reason,
            assigned_to=assigned_to,
        )
    except Exception:
        logger.exception("Escalation WhatsApp queue failed for lead %s", lead_id)
```

Remove `should_escalate_hot_lead` from the import block at line 19-21.

- [ ] **Step 4: Update `resolve_handover`**

In `backend/app/routes/chat_handovers.py`, change the block at lines 136-140 to:

```python
            db.table("leads").update({
                "needs_human_attention": False,
                "escalation_reason": None,
            }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_escalation_ai_live.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && pytest -q`
Expected: PASS. If a pre-existing test asserts `ai_enabled` is set to `False` on escalation, update it — that assertion encodes the behavior this task deliberately removes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_reply.py backend/app/routes/chat_handovers.py backend/tests/test_escalation_ai_live.py
git commit -m "feat(escalation): keep AI live during handover, queue WhatsApp alert"
```

---

### Task 7: Escalation-aware AI prompt

**Files:**
- Modify: `backend/app/services/ai_reply.py:999` (lead select) and `:1158-1162` (prompt assembly)
- Test: `backend/tests/test_escalation_ai_live.py`

**Interfaces:**
- Consumes: `get_business_hours`, `is_within_business_hours`, `describe_hours`, `next_open_description` from Task 3.
- Produces: `_escalation_prompt_block(bh: dict) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_escalation_ai_live.py`:

```python
from datetime import datetime, timezone


def _bh(**overrides):
    base = {
        "enabled": True, "timezone": "Asia/Kolkata",
        "open_time": "09:00", "close_time": "19:00",
        "working_days": [1, 2, 3, 4, 5, 6],
    }
    base.update(overrides)
    return base


def test_prompt_block_marks_office_open_in_hours(monkeypatch):
    import app.services.business_hours as bh_mod
    monkeypatch.setattr(bh_mod, "is_within_business_hours", lambda cfg, now=None: True)

    block = ai_reply._escalation_prompt_block(_bh())
    assert "currently OPEN" in block
    assert "contact them shortly" in block
    assert "Monday to Saturday" in block


def test_prompt_block_marks_office_closed_out_of_hours(monkeypatch):
    import app.services.business_hours as bh_mod
    monkeypatch.setattr(bh_mod, "is_within_business_hours", lambda cfg, now=None: False)
    monkeypatch.setattr(bh_mod, "next_open_description", lambda cfg, now=None: "tomorrow")

    block = ai_reply._escalation_prompt_block(_bh())
    assert "currently CLOSED" in block
    assert "will call them tomorrow" in block


def test_prompt_block_forbids_specific_promises():
    block = ai_reply._escalation_prompt_block(_bh())
    assert "Never promise a specific time" in block
    assert "Never claim someone has already called" in block


def test_lead_select_includes_needs_human_attention():
    """The prompt block keys off needs_human_attention, so it must be selected."""
    src = Path(ai_reply.__file__).read_text(encoding="utf-8")
    assert "needs_human_attention" in src.split("def generate_ai_reply")[1][:3000]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_escalation_ai_live.py -k prompt -v`
Expected: FAIL with `AttributeError: module 'app.services.ai_reply' has no attribute '_escalation_prompt_block'`

- [ ] **Step 3: Add the prompt block helper**

Add to `backend/app/services/ai_reply.py`, near the other prompt helpers:

```python
def _escalation_prompt_block(bh: dict) -> str:
    """System-prompt section telling the AI this lead is already escalated and
    how to answer while they wait, based on whether the office is open."""
    from app.services.business_hours import (
        is_within_business_hours, describe_hours, next_open_description,
    )

    is_open = is_within_business_hours(bh)
    status = "OPEN" if is_open else "CLOSED"
    if is_open:
        guidance = (
            "Reassure them that the team has their request and will contact them shortly."
        )
    else:
        guidance = (
            f"Tell them the team will call them {next_open_description(bh)}, "
            "and state the office hours."
        )

    return (
        "\n\nESCALATION CONTEXT:\n"
        "This customer has already been escalated to the human team. A team member "
        f"has been notified and will follow up. The office is currently {status}. "
        f"Our office hours are {describe_hours(bh)}.\n"
        "If the customer asks to speak to a person, asks about their request, or says "
        f"nobody has contacted them yet: {guidance}\n"
        "Rules:\n"
        "- Never promise a specific time, a named person, or a callback within N minutes.\n"
        "- Never claim someone has already called or messaged them.\n"
        "- Never say the request was resolved.\n"
        "- Otherwise keep answering their questions normally and helpfully.\n"
    )
```

- [ ] **Step 4: Select the flag and inject the block**

At `backend/app/services/ai_reply.py:999`, add `needs_human_attention` to the lead select:

```python
        .select("ai_enabled,score,segment,phone,converted_at,tenant_id,assigned_to,name,blocked_at,needs_human_attention")
```

Then in the prompt assembly, immediately after `system_prompt += _ACCURACY_RULE` (line 1158) and **before** `chat_messages` is built (line 1164), add:

```python
        if lead_data.get("needs_human_attention"):
            try:
                from app.services.business_hours import get_business_hours
                system_prompt += _escalation_prompt_block(
                    get_business_hours(tenant_id, db=db)
                )
            except Exception:
                logger.exception(
                    "Escalation prompt block failed for lead %s — replying without it",
                    lead_id,
                )
```

The `try/except` is load-bearing: a business-hours fault must degrade to a normal reply, never to no reply.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_escalation_ai_live.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 6: Verify the trigger-F loop is harmless**

The new holding replies contain "our team will contact you", which matches `_AI_ESCALATION_RE` and raises trigger F on every turn. Confirm this creates no duplicates:

Run: `cd backend && pytest tests/ -q -k "escalation or handover"`
Expected: PASS. `_trigger_chat_escalation` returns early when an open handover exists (`ai_reply.py:774`), so no duplicate handover and no duplicate alert. Do not "fix" the repeated trigger — it is expected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_escalation_ai_live.py
git commit -m "feat(ai): situational replies for escalated leads using business hours"
```

---

### Task 8: Escalation WhatsApp settings card

**Files:**
- Modify: `frontend/lib/api.ts` (the `NotificationConfig` type)
- Modify: `frontend/app/dashboard/settings/NotificationConfigPanel.tsx`

**Interfaces:**
- Consumes: the config block from Task 2, served by the existing `api.notifications.getConfig()` / `saveConfig()`.
- Produces: no new exports.

- [ ] **Step 1: Extend the type**

In `frontend/lib/api.ts`, add to the `NotificationConfig` type, mirroring `whatsapp_notifications`:

```ts
  whatsapp_escalation_notifications: {
    enabled: boolean;
    recipient_phones: string[];
    template_id: string | null;
    target_segments: string[];
    delay_minutes: number;
  };
```

- [ ] **Step 2: Add the card**

In `NotificationConfigPanel.tsx`, add helper functions beside the existing `toggleWhatsappSegment` / `addPhone` / `removePhone`, operating on `whatsapp_escalation_notifications`:

```tsx
  function toggleEscalationSegment(segment: (typeof SEGMENTS)[number]) {
    if (!cfg) return;
    const block = cfg.whatsapp_escalation_notifications;
    const active = block.target_segments.includes(segment);
    patch({
      whatsapp_escalation_notifications: {
        ...block,
        target_segments: active
          ? block.target_segments.filter((s) => s !== segment)
          : [...block.target_segments, segment],
      },
    });
  }

  function addEscalationPhone() {
    if (!cfg) return;
    const trimmed = escPhoneInput.trim();
    if (!E164_REGEX.test(trimmed)) {
      setEscPhoneError("Enter a valid number in E.164 format, e.g. +919876543210");
      return;
    }
    const block = cfg.whatsapp_escalation_notifications;
    if (block.recipient_phones.includes(trimmed)) {
      setEscPhoneError("This number is already added.");
      return;
    }
    patch({
      whatsapp_escalation_notifications: {
        ...block,
        recipient_phones: [...block.recipient_phones, trimmed],
      },
    });
    setEscPhoneInput("");
    setEscPhoneError(null);
  }

  function removeEscalationPhone(phone: string) {
    if (!cfg) return;
    const block = cfg.whatsapp_escalation_notifications;
    patch({
      whatsapp_escalation_notifications: {
        ...block,
        recipient_phones: block.recipient_phones.filter((p) => p !== phone),
      },
    });
  }
```

Add the matching state beside the existing `phoneInput` / `phoneError`:

```tsx
  const [escPhoneInput, setEscPhoneInput] = useState("");
  const [escPhoneError, setEscPhoneError] = useState<string | null>(null);
```

Then render a new card immediately after the closing `</div>` of the existing WhatsApp segment notifications block, structurally identical to it, with these copy differences:

- Heading: `WhatsApp escalation alerts`
- Subheading: `Message your team on WhatsApp when a conversation is escalated to a human.`
- Segment label: `Alert for segments`
- Delay label: `Delay before sending (minutes)`
- Delay helper text (**different semantics — do not copy the segment version**): `How long to wait before alerting. If a teammate claims or resolves the handover first, the message is not sent.`

Reuse `Toggle`, `SEGMENTS`, `SEGMENT_LABELS`, `SEGMENT_STYLES`, `E164_REGEX`, and `approvedTemplates`. Derive its own `selectedTemplate` from `cfg.whatsapp_escalation_notifications.template_id`.

- [ ] **Step 3: Verify — lint and typecheck**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: both PASS. Lint is not optional — CI runs `next lint`, and `tsc` alone will not catch unused imports or implicit `any`.

- [ ] **Step 4: Verify in the browser**

Run `cd frontend && npm run dev`, open Settings, toggle the new card on, add a phone, pick a template, save, reload.
Expected: values persist across the reload.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/dashboard/settings/NotificationConfigPanel.tsx
git commit -m "feat(settings): WhatsApp escalation alerts card"
```

---

### Task 9: Business hours settings card

**Files:**
- Create: `frontend/app/dashboard/settings/BusinessHoursPanel.tsx`
- Modify: the settings page that renders the other panels (find it with: `grep -rl "NotificationConfigPanel" frontend/app`)

**Interfaces:**
- Consumes: `GET`/`PATCH /api/v1/settings/business-hours` from Task 3.
- Produces: `export function BusinessHoursPanel({ canManage }: { canManage?: boolean })`.

- [ ] **Step 1: Build the panel**

Create `frontend/app/dashboard/settings/BusinessHoursPanel.tsx`, following the fetch/dirty/save shape of `InboxConfigPanel.tsx` (which uses `API_URL` + `getAuthHeaders` directly):

```tsx
"use client";
import { useEffect, useState, useCallback } from "react";
import { Clock, Save, Loader2, CheckCircle2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type BusinessHours = {
  enabled: boolean;
  timezone: string;
  open_time: string;
  close_time: string;
  working_days: number[];
};

const DEFAULT: BusinessHours = {
  enabled: true,
  timezone: "Asia/Kolkata",
  open_time: "09:00",
  close_time: "19:00",
  working_days: [1, 2, 3, 4, 5, 6],
};

const DAYS: { value: number; label: string }[] = [
  { value: 1, label: "Mon" }, { value: 2, label: "Tue" }, { value: 3, label: "Wed" },
  { value: 4, label: "Thu" }, { value: 5, label: "Fri" }, { value: 6, label: "Sat" },
  { value: 7, label: "Sun" },
];

const TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "UTC"];

export function BusinessHoursPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<BusinessHours>(DEFAULT);
  const [draft, setDraft] = useState<BusinessHours>(DEFAULT);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/business-hours`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setDraft(data);
      }
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(config);

  async function handleSave() {
    if (!canManage) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/business-hours`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify(draft),
      });
      if (!res.ok) throw new Error("Save failed");
      const saved = await res.json();
      setConfig(saved);
      setDraft(saved);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("idle");
    }
  }

  function toggleDay(day: number) {
    setDraft({
      ...draft,
      working_days: draft.working_days.includes(day)
        ? draft.working_days.filter((d) => d !== day)
        : [...draft.working_days, day].sort((a, b) => a - b),
    });
  }

  return (
    <div className="card rounded-3xl">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center bg-violet-100">
          <Clock size={18} className="text-violet-600" />
        </div>
        <div>
          <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem" }}>
            Business Hours
          </h2>
          <p className="font-body text-sm text-ink-muted mt-0.5">
            When your team is reachable. The AI uses this to tell escalated customers
            when to expect a call.
          </p>
        </div>
      </div>

      <div className="mt-6 space-y-5">
        <label className="flex items-center gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
          <input
            type="checkbox"
            checked={draft.enabled}
            disabled={!canManage}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            className="accent-violet-600"
          />
          <div>
            <div className="font-label text-sm font-semibold text-ink">Enable business hours</div>
            <div className="font-body text-xs text-ink-muted mt-0.5">
              When off, the AI always treats the office as closed.
            </div>
          </div>
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">Opens</label>
            <input
              type="time"
              value={draft.open_time}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, open_time: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">Closes</label>
            <input
              type="time"
              value={draft.close_time}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, close_time: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">Timezone</label>
            <select
              value={draft.timezone}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm text-ink focus:outline-none focus:border-primary"
            >
              {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
            </select>
          </div>
        </div>

        <div>
          <div className="font-label text-sm font-semibold text-ink mb-2">Working days</div>
          <div className="flex flex-wrap gap-2">
            {DAYS.map(({ value, label }) => {
              const active = draft.working_days.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={active}
                  disabled={!canManage}
                  onClick={() => toggleDay(value)}
                  className={`px-3 py-1.5 rounded-full font-label text-xs font-semibold border transition-colors ${
                    active
                      ? "bg-primary text-white border-primary"
                      : "bg-white text-ink-muted border-border hover:border-violet-300"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex justify-end pt-2 border-t border-border">
          <button
            onClick={handleSave}
            disabled={!canManage || saveState !== "idle" || !isDirty}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
              saveState === "saved"
                ? "bg-emerald-100 text-emerald-700 cursor-default"
                : canManage && isDirty
                ? "bg-primary text-white hover:bg-primary/90"
                : "bg-surface-subtle text-ink-muted cursor-default"
            }`}
          >
            {saveState === "saving" ? (
              <><Loader2 size={14} className="animate-spin" />Saving…</>
            ) : saveState === "saved" ? (
              <><CheckCircle2 size={14} />Saved</>
            ) : (
              <><Save size={14} />Save Changes</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Render it**

Import and render `<BusinessHoursPanel canManage={...} />` in the settings page, immediately before `<NotificationConfigPanel />`, passing the same `canManage` value the sibling panels receive.

- [ ] **Step 3: Verify — lint and typecheck**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: both PASS.

- [ ] **Step 4: Verify in the browser**

Run `cd frontend && npm run dev`. Change the close time and deselect Saturday, save, reload.
Expected: values persist. Deselecting every day should still save (the backend treats an empty `working_days` as always closed).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/BusinessHoursPanel.tsx frontend/app/dashboard/settings/
git commit -m "feat(settings): business hours panel"
```

---

### Task 10: Remove the dead Segments control

**Files:**
- Modify: `frontend/app/dashboard/settings/InboxConfigPanel.tsx:6-20, 30-34, 178-194`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. `inbox_config.segments` stays in the database untouched; only the UI and the PATCH payload stop referencing it.

- [ ] **Step 1: Remove the control**

In `InboxConfigPanel.tsx`:

1. Delete `segments: string[];` from the `InboxConfig` type (line 9).
2. Delete `segments: ["A"],` from `DEFAULT` (line 17).
3. Delete the entire `SEGMENT_LABELS` constant (lines 30-34).
4. Delete the entire `{/* Segments */}` block (lines 178-194).

Because `draft` is sent wholesale as the PATCH body, removing the field from the type and `DEFAULT` is sufficient to stop sending it. The backend still accepts and stores the key for older clients — no API change is needed.

- [ ] **Step 2: Verify — lint and typecheck**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: both PASS. Lint will catch `SEGMENT_LABELS` if you removed its usage but not its declaration.

- [ ] **Step 3: Verify in the browser**

Run `cd frontend && npm run dev`, open Settings → Inbox Escalation.
Expected: no "Segments to Escalate" section; triggers and channels still save and reload correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/settings/InboxConfigPanel.tsx
git commit -m "refactor(settings): remove dead Segments to Escalate control"
```

---

### Task 11: Update subsystem notes

**Files:**
- Modify: `.agents/context/subsystem-notes.md` (the "Chat escalation" section, around line 78-80)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Update the notes**

The existing bullets state escalation sets `ai_enabled` false and that handovers only notify the pool. Both are now wrong. Replace the "Chat escalation" bullets with:

```markdown
## Chat escalation (ai_reply.py / chat_handovers.py)
- **Trigger-only:** A=fallback, B=AI/LLM error, C=user asked for human (always fires), D=repeated question, F=AI said team will follow up. `_TRIGGER_PRIORITY = ["C","B","A","D","F"]`. **Trigger E (score-hot) was DROPPED** — no score/segment chat escalation. The dead `inbox_config.segments` UI control was removed 2026-07-19; the column remains but nothing reads it.
- **No auto-assign:** handovers land UNASSIGNED in a shared pool visible to admin + every telecaller (caller scope = `assigned_to == me OR needs_human_attention`). `needs_human_attention` set on escalation, cleared on resolve.
- **The AI does NOT pause on escalation (2026-07-19).** Escalation no longer sets `ai_enabled=False`, and `resolve_handover` no longer sets it `True` — `ai_enabled` is now a purely manual admin control. Instead, `generate_ai_reply` injects `_escalation_prompt_block()` (office OPEN/CLOSED + hours from `services/business_hours.py`) so the AI answers "contacted shortly" in-hours and "call you tomorrow" out-of-hours. **Accepted risk:** the AI can reply alongside a live human agent; the per-lead `ai_enabled` toggle is the escape hatch.
- **Trigger F fires on every turn once escalated** — the holding replies contain "our team will contact you", which matches `_AI_ESCALATION_RE`. This is harmless and expected: `_trigger_chat_escalation` returns early when an open handover exists, so no duplicate handover or alert. Do not "fix" it.
- **WhatsApp escalation alerts (2026-07-19):** `queue_escalation_whatsapp_alert` parks a row in `pending_whatsapp_alerts` (`alert_type='escalation'`) at `now + delay_minutes`; the scheduler cancels it if the handover was resolved or `assigned_to` changed from `assigned_to_at_queue`. Config lives in `notification_config.whatsapp_escalation_notifications` (an app_settings JSON blob, not columns).
```

- [ ] **Step 2: Commit**

```bash
git add .agents/context/subsystem-notes.md
git commit -m "docs: update chat escalation subsystem notes"
```

---

## Final verification

- [ ] **Backend suite**

Run: `cd backend && pytest -q`
Expected: all PASS, including `test_whatsapp_notifications.py` and `test_notify_service.py` unchanged.

- [ ] **Frontend**

Run: `cd frontend && npm run lint && npm run typecheck && npm run build`
Expected: all three PASS.

- [ ] **End-to-end smoke test**

1. Settings → enable WhatsApp escalation alerts, add your own number, pick an approved template, set delay to 1 minute.
2. Settings → Business Hours: set close time to a minute from now.
3. Send a message from a test WhatsApp lead saying "I want to talk to a person".
4. Expected: a handover appears in the inbox, **the AI still replies** with a reassurance, and ~1 minute later your phone receives the WhatsApp alert.
5. Repeat, but claim the handover in the dashboard within the delay window.
6. Expected: no WhatsApp arrives; the queued row is `cancelled`.
7. Wait until after the close time and message again.
8. Expected: the AI's reply now references the office hours and a next-day callback.
