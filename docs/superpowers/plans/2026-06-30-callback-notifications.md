# Scheduled Callback Notifications + Configurable Push Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify telecallers/admins about scheduled callbacks (due reminder, claimable broadcast, claim notice), retire the auto-reassignment pipeline in favor of a claimable-only model, and give the admin a tenant-wide, configurable push-notification settings panel.

**Architecture:** A new 1-minute scheduler service (`callback_notifications.py`) scans pending callbacks: it sends a "due now" push to the assigned caller at the scheduled time, and — after a configurable threshold (default 15 min) — broadcasts a "claimable" push to a configurable audience (all telecallers + admin / telecallers only / admin only), **with no shift check**. Two new `follow_up_jobs` guard columns ensure each event fires once. A new `notification_config` JSON in `app_settings` (read via `get_notification_config`) gates push delivery through a single chokepoint in `notify_user` (master switch + per-event push toggles + quiet hours), keeping the in-app bell always intact. The existing off-shift auto-reassignment job is removed.

**Tech Stack:** FastAPI (`backend/app/`), Supabase (Postgres via `supabase-py`), APScheduler, pywebpush (VAPID), Next.js 14 (`frontend/app/dashboard/`), pytest.

## Global Constraints

- Every Supabase query MUST be scoped by `tenant_id`.
- Notification/scheduler code is **best-effort: it must never raise into the caller.** Wrap external work in try/except and log warnings, matching `notify.py` and `main.py` job wrappers.
- All new Python function signatures MUST have type annotations.
- Times stored/compared in UTC ISO-8601 (`datetime.now(timezone.utc).isoformat()`). Quiet-hours comparisons use IST (UTC + 5:30), matching the shift logic in `assignment.py`.
- Settings UI is **owner-only** (the settings page already enforces `role === "owner"`); the config endpoints MUST use `require_owner`.
- New migration number is **122** (highest existing is 121).
- Per-event config gates the **push layer only** — the in-app `app_notifications` row is ALWAYS written so nothing is silently lost.
- Notification dedupe for callback flows is enforced by the `follow_up_jobs` guard columns, NOT by `notify_user`'s `dedupe_lead_id`.

## notification_config schema (canonical — referenced by multiple tasks)

```python
_NOTIFICATION_CONFIG_DEFAULT = {
    "push_enabled": True,                       # master push switch
    "events": {                                 # per-event PUSH toggle (in-app always on)
        "callback_due": True,
        "callback_claimable": True,
        "callback_taken_over": True,
        "lead_assigned": True,
        "lead_replied": True,
        "handover_new": True,
    },
    "claimable_threshold_minutes": 15,          # 1..120
    "claimable_audience": "telecallers_and_admin",  # | "telecallers_only" | "admin_only" | "specific"
    "claimable_caller_ids": [],                 # caller IDs; used ONLY when audience == "specific"
    "quiet_hours": {
        "enabled": False,
        "start_hour": 22,                       # IST 0..23 (inclusive start)
        "end_hour": 8,                          # IST 0..23 (exclusive end); wraps midnight
    },
}
```

`claimable_audience == "specific"` sends the claimable broadcast only to the telecallers whose caller IDs are listed in `claimable_caller_ids` (admin is not auto-included in this mode). The admin chooses these telecallers in the settings panel.

---

## File Structure

- `backend/supabase/migrations/122_callback_notification_guards.sql` — **Create.** Guard columns + index on `follow_up_jobs`.
- `backend/app/services/notification_config.py` — **Create.** Config defaults, `get/save_notification_config`, `push_allowed`, `_in_quiet_hours`.
- `backend/app/services/notify.py` — **Modify.** Gate push via `push_allowed`; add `_enrolled_caller_user_ids` + `notify_callback_claimable(audience=...)`.
- `backend/app/services/callback_notifications.py` — **Create.** `process_callback_notifications()` (due + claimable passes; no shift check).
- `backend/app/services/assignment.py` — **Modify.** Delete `process_callback_reassignments` (retired).
- `backend/app/main.py` — **Modify.** Add `callback-notifications` job; remove `callback-reassignment` job + wrapper; update startup log.
- `backend/app/routes/follow_ups.py` — **Modify.** `reschedule_callback` resets the guard columns.
- `backend/app/routes/leads.py` — **Modify.** `takeover_lead` uses `notify_user` (adds push to claim notice).
- `backend/app/routes/notifications.py` — **Modify.** Add `GET/PUT /config`.
- `frontend/lib/api.ts` — **Modify.** Add `api.notifications.getConfig/saveConfig`.
- `frontend/app/dashboard/settings/NotificationConfigPanel.tsx` — **Create.** The settings panel.
- `frontend/app/dashboard/settings/page.tsx` — **Modify.** Add a "Notifications" tab rendering the panel.
- Tests: `backend/tests/test_notification_config.py`, `backend/tests/test_callback_notifications.py` — **Create.** `backend/tests/test_notify_service.py` — **Modify.**

---

### Task 1: Migration — callback notification guard columns

**Files:**
- Create: `backend/supabase/migrations/122_callback_notification_guards.sql`

**Interfaces:**
- Produces: nullable `timestamptz` columns `due_notified_at`, `claimable_notified_at` on `follow_up_jobs`. NULL = not yet notified for the current slot.

- [ ] **Step 1: Write the migration**

Create `backend/supabase/migrations/122_callback_notification_guards.sql`:

```sql
-- Guard columns so callback notifications fire exactly once per scheduled slot.
-- Reset to NULL on reschedule (see reschedule_callback) so a new slot re-arms them.
ALTER TABLE follow_up_jobs
  ADD COLUMN IF NOT EXISTS due_notified_at       timestamptz,
  ADD COLUMN IF NOT EXISTS claimable_notified_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_follow_up_jobs_callback_scan
  ON follow_up_jobs(tenant_id, cadence, status, scheduled_for);
```

- [ ] **Step 2: Apply to Supabase and verify**

Apply via the Supabase SQL editor/CLI (this project applies SQL directly; there is no local migration runner in pytest). Verify:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'follow_up_jobs'
  AND column_name IN ('due_notified_at', 'claimable_notified_at');
```

Expected: two rows.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/122_callback_notification_guards.sql
git commit -m "feat(db): add callback notification guard columns to follow_up_jobs"
```

---

### Task 2: notification_config service (defaults, get/save, push_allowed)

**Files:**
- Create: `backend/app/services/notification_config.py`
- Test: `backend/tests/test_notification_config.py`

**Interfaces:**
- Produces:
  - `get_notification_config(tenant_id: str, db=None) -> dict` — merged with defaults (deep-merges `events` and `quiet_hours`).
  - `save_notification_config(tenant_id: str, config: dict) -> None`
  - `_in_quiet_hours(quiet: dict, ist_hour: int) -> bool` — handles midnight wrap.
  - `push_allowed(tenant_id: str, event_type: str, *, db=None) -> bool` — master switch AND per-event toggle AND not in quiet hours.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_notification_config.py`:

```python
from unittest.mock import MagicMock, patch


def test_in_quiet_hours_wraps_midnight():
    from app.services.notification_config import _in_quiet_hours
    q = {"enabled": True, "start_hour": 22, "end_hour": 8}
    assert _in_quiet_hours(q, 23) is True
    assert _in_quiet_hours(q, 2) is True
    assert _in_quiet_hours(q, 8) is False
    assert _in_quiet_hours(q, 12) is False


def test_in_quiet_hours_same_day_window():
    from app.services.notification_config import _in_quiet_hours
    q = {"enabled": True, "start_hour": 9, "end_hour": 17}
    assert _in_quiet_hours(q, 12) is True
    assert _in_quiet_hours(q, 18) is False


def test_get_config_merges_defaults_for_missing_subkeys():
    from app.services import notification_config as nc
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "value": '{"claimable_threshold_minutes": 20, "events": {"lead_replied": false}}'
    }
    cfg = nc.get_notification_config("t-1", db=db)
    assert cfg["claimable_threshold_minutes"] == 20
    assert cfg["events"]["lead_replied"] is False          # override kept
    assert cfg["events"]["callback_due"] is True            # default filled in
    assert cfg["push_enabled"] is True                      # default filled in
    assert cfg["quiet_hours"]["start_hour"] == 22           # default subtree filled in


def test_push_allowed_respects_master_and_event_toggle():
    from app.services import notification_config as nc
    base = {
        "push_enabled": True,
        "events": {"callback_due": False, "lead_assigned": True},
        "quiet_hours": {"enabled": False, "start_hour": 22, "end_hour": 8},
    }
    with patch.object(nc, "get_notification_config", return_value={**nc._NOTIFICATION_CONFIG_DEFAULT, **base}):
        assert nc.push_allowed("t-1", "lead_assigned") is True
        assert nc.push_allowed("t-1", "callback_due") is False   # event off
        assert nc.push_allowed("t-1", "unlisted_type") is True   # unknown → allowed


def test_push_allowed_false_when_master_off():
    from app.services import notification_config as nc
    cfg = {**nc._NOTIFICATION_CONFIG_DEFAULT, "push_enabled": False}
    with patch.object(nc, "get_notification_config", return_value=cfg):
        assert nc.push_allowed("t-1", "lead_assigned") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notification_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.notification_config'`.

- [ ] **Step 3: Implement the module**

Create `backend/app/services/notification_config.py`:

```python
import json
import logging
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_NOTIFICATION_CONFIG_DEFAULT: dict = {
    "push_enabled": True,
    "events": {
        "callback_due": True,
        "callback_claimable": True,
        "callback_taken_over": True,
        "lead_assigned": True,
        "lead_replied": True,
        "handover_new": True,
    },
    "claimable_threshold_minutes": 15,
    "claimable_audience": "telecallers_and_admin",
    "claimable_caller_ids": [],
    "quiet_hours": {"enabled": False, "start_hour": 22, "end_hour": 8},
}


def get_notification_config(tenant_id: str, db=None) -> dict:
    """Return notification_config from app_settings, deep-merged with defaults."""
    db = db or get_supabase()
    merged = {
        **_NOTIFICATION_CONFIG_DEFAULT,
        "events": dict(_NOTIFICATION_CONFIG_DEFAULT["events"]),
        "quiet_hours": dict(_NOTIFICATION_CONFIG_DEFAULT["quiet_hours"]),
    }
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "notification_config")
            .maybe_single()
            .execute()
        )
        if row and row.data:
            stored = json.loads(row.data["value"])
            if isinstance(stored, dict):
                merged["events"] = {**merged["events"], **(stored.get("events") or {})}
                merged["quiet_hours"] = {**merged["quiet_hours"], **(stored.get("quiet_hours") or {})}
                for k in ("push_enabled", "claimable_threshold_minutes", "claimable_audience", "claimable_caller_ids"):
                    if k in stored:
                        merged[k] = stored[k]
    except Exception as e:
        logger.warning(f"get_notification_config failed for {tenant_id}: {e}")
    return merged


def save_notification_config(tenant_id: str, config: dict) -> None:
    """Persist notification_config to app_settings."""
    db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "notification_config",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


def _in_quiet_hours(quiet: dict, ist_hour: int) -> bool:
    """True if ist_hour falls inside the configured quiet window. Handles midnight wrap."""
    if not quiet.get("enabled"):
        return False
    start = quiet.get("start_hour", 22)
    end = quiet.get("end_hour", 8)
    if start == end:
        return False
    if start < end:
        return start <= ist_hour < end
    return ist_hour >= start or ist_hour < end


def push_allowed(tenant_id: str, event_type: str, *, db=None) -> bool:
    """Whether a web push for this event type may be delivered right now.

    Gates on master switch, per-event toggle (unknown types default allowed),
    and quiet hours (IST). In-app notifications are NEVER gated by this.
    """
    cfg = get_notification_config(tenant_id, db=db)
    if not cfg.get("push_enabled"):
        return False
    if not cfg.get("events", {}).get(event_type, True):
        return False
    quiet = cfg.get("quiet_hours", {})
    if quiet.get("enabled"):
        ist_hour = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).hour
        if _in_quiet_hours(quiet, ist_hour):
            return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notification_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification_config.py backend/tests/test_notification_config.py
git commit -m "feat(notify): add tenant notification_config (toggles, threshold, audience, quiet hours)"
```

---

### Task 3: gate notify_user push + add claimable fan-out

**Files:**
- Modify: `backend/app/services/notify.py`
- Test: `backend/tests/test_notify_service.py`

**Interfaces:**
- Consumes: `push_allowed` from Task 2; existing `notify_user`, `_owner_user_id`.
- Produces:
  - `notify_user` now skips `send_user_push` when `push_allowed(tenant_id, type)` is False (in-app row still written).
  - `_enrolled_caller_user_ids(db, tenant_id: str) -> list[str]` — all `active=True` callers, any status.
  - `_caller_user_ids_by_ids(db, tenant_id: str, caller_ids: list[str]) -> list[str]` — user_ids for a specific set of active caller IDs.
  - `notify_callback_claimable(tenant_id: str, *, title: str, message: str, lead_id: str, audience: str = "telecallers_and_admin", caller_ids: list[str] | None = None, exclude_user_ids: list[str] | None = None, db=None) -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_notify_service.py`:

```python
def test_notify_user_skips_push_when_disabled():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db), \
         patch("app.services.notification_config.push_allowed", return_value=False), \
         patch("app.services.web_push.send_user_push") as push:
        notify.notify_user("t-1", "u-1", "callback_due", "Due", "Call now", db=db)
    assert len(captured) == 1           # in-app row still written
    push.assert_not_called()            # push suppressed


def test_notify_user_sends_push_when_allowed():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db), \
         patch("app.services.notification_config.push_allowed", return_value=True), \
         patch("app.services.web_push.send_user_push") as push:
        notify.notify_user("t-1", "u-1", "callback_due", "Due", "Call now", db=db)
    push.assert_called_once()


def test_enrolled_caller_ids_ignores_status():
    from app.services import notify
    db = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": "u-active"}, {"user_id": "u-loggedout"}, {"user_id": None},
    ]
    db.table.return_value = t
    assert set(notify._enrolled_caller_user_ids(db, "t-1")) == {"u-active", "u-loggedout"}


def test_notify_callback_claimable_audience_admin_only():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2"]), \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="admin_only", db=db)
    assert sent == ["u-owner"]


def test_notify_callback_claimable_excludes_owner():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2"]), \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="telecallers_and_admin",
                                         exclude_user_ids=["u-c1"], db=db)
    assert set(sent) == {"u-c2", "u-owner"}


def test_notify_callback_claimable_specific_callers_only():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2", "u-c3"]), \
         patch.object(notify, "_caller_user_ids_by_ids", return_value=["u-c2", "u-c3"]) as by_ids, \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="specific", caller_ids=["c2", "c3"], db=db)
    assert set(sent) == {"u-c2", "u-c3"}   # only the chosen callers; no owner
    by_ids.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notify_service.py -k "push or enrolled or claimable" -v`
Expected: FAIL (`send_user_push` still called when disabled; `_enrolled_caller_user_ids`/`notify_callback_claimable` missing).

- [ ] **Step 3: Gate the push in notify_user**

In `backend/app/services/notify.py`, replace the push block inside `notify_user` (currently lines ~45-59) with:

```python
        try:
            from app.services.notification_config import push_allowed
            if push_allowed(tenant_id, type, db=db):
                from app.services.web_push import send_user_push
                push_body = re.sub(r"\s*\[(lead_id|handover_id):.*?\]", "", message)
                send_user_push(
                    tenant_id,
                    user_id,
                    title=title,
                    body=push_body,
                    url=push_url or "/dashboard",
                    tag=f"{type}:{dedupe_lead_id}" if dedupe_lead_id else type,
                    data={"type": type, "lead_id": dedupe_lead_id},
                    db=db,
                )
        except Exception as push_err:
            logger.warning("notify_user push failed (type=%s user=%s): %s", type, user_id, push_err)
```

- [ ] **Step 4: Add the claimable helpers**

In `backend/app/services/notify.py`, after `_owner_user_id` (~line 127), add:

```python
def _enrolled_caller_user_ids(db, tenant_id: str) -> list[str]:
    """user_ids of every enrolled caller (active=True), regardless of online status.

    Push reaches anyone with a push_subscriptions row (app installed), so we must
    NOT filter on caller.status — a logged-out caller with the app still gets push.
    """
    callers = (
        db.table("callers")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("active", True)
        .execute()
    )
    return [c["user_id"] for c in (callers.data or []) if c.get("user_id")]


def _caller_user_ids_by_ids(db, tenant_id: str, caller_ids: list[str]) -> list[str]:
    """user_ids for a specific set of active caller IDs (for the 'specific' audience)."""
    if not caller_ids:
        return []
    res = (
        db.table("callers")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("active", True)
        .in_("id", caller_ids)
        .execute()
    )
    return [c["user_id"] for c in (res.data or []) if c.get("user_id")]


def notify_callback_claimable(
    tenant_id: str,
    *,
    title: str,
    message: str,
    lead_id: str,
    audience: str = "telecallers_and_admin",
    caller_ids: list[str] | None = None,
    exclude_user_ids: list[str] | None = None,
    db=None,
) -> None:
    """Broadcast a claimable callback (in-app + push) to the configured audience.

    audience:
      "telecallers_and_admin" → all enrolled callers + owner
      "telecallers_only"      → all enrolled callers
      "admin_only"            → owner
      "specific"              → only the callers in caller_ids (owner NOT auto-added)
    Reuses notify_user so each recipient gets bell + push (push still subject to
    push_allowed). Dedupe across re-runs is handled by claimable_notified_at, so
    we do NOT pass dedupe_lead_id. Best-effort: never raises.
    """
    db = db or get_supabase()
    exclude = set(exclude_user_ids or [])
    try:
        recipients: set[str] = set()
        if audience == "specific":
            recipients |= set(_caller_user_ids_by_ids(db, tenant_id, caller_ids or []))
        else:
            if audience in ("telecallers_and_admin", "telecallers_only"):
                recipients |= set(_enrolled_caller_user_ids(db, tenant_id))
            if audience in ("telecallers_and_admin", "admin_only"):
                owner = _owner_user_id(db, tenant_id)
                if owner:
                    recipients.add(owner)
        for uid in recipients - exclude:
            notify_user(
                tenant_id, uid, "callback_claimable", title, message,
                db=db, push_url="/dashboard/telecalling/scheduled",
            )
    except Exception as e:
        logger.warning(f"notify_callback_claimable failed (lead={lead_id}): {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notify_service.py -v`
Expected: PASS (all existing + 5 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/notify.py backend/tests/test_notify_service.py
git commit -m "feat(notify): gate push by notification_config; add claimable broadcast with audience"
```

---

### Task 4: callback notification scanner (claimable-only model)

**Files:**
- Create: `backend/app/services/callback_notifications.py`
- Test: `backend/tests/test_callback_notifications.py`

**Interfaces:**
- Consumes: `get_supabase`; `get_telecalling_config` (from `assignment`); `get_notification_config` (from `notification_config`); `notify_user`, `notify_callback_claimable` (from `notify`).
- Produces: `process_callback_notifications() -> dict` → `{"due": int, "claimable": int}`.

**Behavior:**
- **Due pass:** pending callbacks with `scheduled_for <= now` and `due_notified_at IS NULL` → push `callback_due` to the lead's assigned caller; set `due_notified_at` regardless.
- **Claimable pass:** pending callbacks with `scheduled_for <= now - threshold` and `claimable_notified_at IS NULL` → broadcast via `notify_callback_claimable(audience=cfg.claimable_audience)` excluding the current owner; set `claimable_notified_at`. **No shift/availability check** — any overdue callback becomes claimable.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_callback_notifications.py`:

```python
from unittest.mock import MagicMock, patch


def _build_db(due_jobs, claimable_jobs, leads, callers, updates):
    def table_selector(name):
        t = MagicMock()
        if name == "app_settings":
            t.select.return_value.eq.return_value.execute.return_value.data = [{"tenant_id": "t-1"}]
        elif name == "follow_up_jobs":
            chain = t.select.return_value.eq.return_value.eq.return_value.eq.return_value.lte.return_value.is_.return_value.limit.return_value
            chain.execute.side_effect = [MagicMock(data=due_jobs), MagicMock(data=claimable_jobs)]

            def _update(payload):
                upd = MagicMock()
                def _eq1(*a, **k):
                    inner = MagicMock()
                    def _eq2(*a2, **k2):
                        updates.append(payload)
                        res = MagicMock(); res.execute.return_value.data = [{"id": "x"}]; return res
                    inner.eq.side_effect = _eq2
                    return inner
                upd.eq.side_effect = _eq1
                return upd
            t.update.side_effect = _update
        elif name == "leads":
            def _eq(col, val):
                inner = MagicMock()
                inner.eq.return_value.maybe_single.return_value.execute.return_value.data = leads.get(val)
                return inner
            t.select.return_value.eq.side_effect = _eq
        elif name == "callers":
            def _eq(col, val):
                inner = MagicMock()
                inner.maybe_single.return_value.execute.return_value.data = callers.get(val)
                return inner
            t.select.return_value.eq.side_effect = _eq
        return t

    db = MagicMock(); db.table.side_effect = table_selector
    return db


def _cfg(**over):
    base = {"claimable_threshold_minutes": 15, "claimable_audience": "telecallers_and_admin"}
    base.update(over)
    return base


def test_due_pass_pushes_to_assigned_and_sets_guard():
    from app.services import callback_notifications as cn
    updates, sent = [], []
    db = _build_db(
        [{"id": "j1", "lead_id": "l1"}], [],
        {"l1": {"id": "l1", "name": "Asha", "assigned_to": "c1"}},
        {"c1": {"user_id": "u1"}}, updates,
    )
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": True}), \
         patch.object(cn, "get_notification_config", return_value=_cfg()), \
         patch.object(cn, "notify_user", side_effect=lambda t, u, ty, *a, **k: sent.append((u, ty))), \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res["due"] == 1
    assert sent == [("u1", "callback_due")]
    assert any("due_notified_at" in u for u in updates)
    claim.assert_not_called()


def test_claimable_pass_broadcasts_regardless_of_shift():
    from app.services import callback_notifications as cn
    updates = []
    db = _build_db(
        [], [{"id": "j2", "lead_id": "l2"}],
        {"l2": {"id": "l2", "name": "Ravi", "assigned_to": "c2"}},
        {"c2": {"user_id": "u2"}}, updates,
    )
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": True}), \
         patch.object(cn, "get_notification_config", return_value=_cfg(claimable_audience="admin_only")), \
         patch.object(cn, "notify_user"), \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res["claimable"] == 1
    claim.assert_called_once()
    assert claim.call_args.kwargs["audience"] == "admin_only"
    assert claim.call_args.kwargs["exclude_user_ids"] == ["u2"]
    assert any("claimable_notified_at" in u for u in updates)


def test_disabled_tenant_skipped():
    from app.services import callback_notifications as cn
    updates = []
    db = _build_db([{"id": "j", "lead_id": "l"}], [], {}, {}, updates)
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": False}), \
         patch.object(cn, "get_notification_config", return_value=_cfg()), \
         patch.object(cn, "notify_user") as nu, \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res == {"due": 0, "claimable": 0}
    nu.assert_not_called(); claim.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_callback_notifications.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.callback_notifications'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/callback_notifications.py`:

```python
import logging
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase
from app.services.assignment import get_telecalling_config
from app.services.notification_config import get_notification_config
from app.services.notify import notify_user, notify_callback_claimable

logger = logging.getLogger(__name__)


def _resolve_user_id(db, caller_id: str, tenant_id: str) -> str | None:
    if not caller_id:
        return None
    res = (
        db.table("callers").select("user_id").eq("id", caller_id).maybe_single().execute()
    )
    return (res.data or {}).get("user_id") if res else None


def process_callback_notifications() -> dict:
    """Scheduler job: callback 'due' reminders + 'claimable' broadcasts (claimable-only model).

    Due:       at the scheduled slot, push the assigned caller.
    Claimable: threshold minutes later (config, default 15), broadcast to the configured
               audience regardless of shift. Guards prevent re-firing. Never raises.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    due_count = 0
    claimable_count = 0

    try:
        tenants = (
            db.table("app_settings").select("tenant_id").eq("key", "telecalling_config").execute()
        )
    except Exception as e:
        logger.error(f"callback notifications: tenant scan failed: {e}")
        return {"due": 0, "claimable": 0}

    seen: set[str] = set()
    for row in (tenants.data or []):
        tid = row.get("tenant_id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        try:
            if not get_telecalling_config(tid).get("enabled"):
                continue
            ncfg = get_notification_config(tid, db=db)
            threshold = int(ncfg.get("claimable_threshold_minutes", 15) or 15)
            audience = ncfg.get("claimable_audience", "telecallers_and_admin")
            audience_caller_ids = ncfg.get("claimable_caller_ids") or []
            claimable_cutoff_iso = (now - timedelta(minutes=threshold)).isoformat()

            # ── DUE PASS ──
            due_jobs = (
                db.table("follow_up_jobs")
                .select("id,lead_id")
                .eq("tenant_id", tid).eq("cadence", "callback").eq("status", "pending")
                .lte("scheduled_for", now_iso).is_("due_notified_at", "null")
                .limit(100).execute()
            )
            for job in (due_jobs.data or []):
                try:
                    lead = (
                        db.table("leads").select("id,name,assigned_to")
                        .eq("id", job["lead_id"]).eq("tenant_id", tid).maybe_single().execute()
                    )
                    ld = (lead.data or {}) if lead else {}
                    uid = _resolve_user_id(db, ld.get("assigned_to"), tid) if ld.get("assigned_to") else None
                    if uid:
                        notify_user(
                            tid, uid, "callback_due", "Callback due now",
                            f"Your scheduled callback with '{ld.get('name') or 'your lead'}' is due now.",
                            db=db, push_url="/dashboard/telecalling/scheduled",
                        )
                    db.table("follow_up_jobs").update({"due_notified_at": now_iso}) \
                        .eq("id", job["id"]).eq("tenant_id", tid).execute()
                    due_count += 1
                except Exception as e:
                    logger.warning(f"callback due notify failed for job {job['id']}: {e}")

            # ── CLAIMABLE PASS (no shift check) ──
            claimable_jobs = (
                db.table("follow_up_jobs")
                .select("id,lead_id")
                .eq("tenant_id", tid).eq("cadence", "callback").eq("status", "pending")
                .lte("scheduled_for", claimable_cutoff_iso).is_("claimable_notified_at", "null")
                .limit(100).execute()
            )
            for job in (claimable_jobs.data or []):
                try:
                    lead = (
                        db.table("leads").select("id,name,assigned_to")
                        .eq("id", job["lead_id"]).eq("tenant_id", tid).maybe_single().execute()
                    )
                    ld = (lead.data or {}) if lead else {}
                    exclude: list[str] = []
                    if ld.get("assigned_to"):
                        owner_uid = _resolve_user_id(db, ld.get("assigned_to"), tid)
                        if owner_uid:
                            exclude.append(owner_uid)
                    notify_callback_claimable(
                        tid,
                        title="Callback open to claim",
                        message=f"An overdue callback with '{ld.get('name') or 'a lead'}' is open to claim.",
                        lead_id=job["lead_id"],
                        audience=audience,
                        caller_ids=audience_caller_ids,
                        exclude_user_ids=exclude,
                        db=db,
                    )
                    db.table("follow_up_jobs").update({"claimable_notified_at": now_iso}) \
                        .eq("id", job["id"]).eq("tenant_id", tid).execute()
                    claimable_count += 1
                except Exception as e:
                    logger.warning(f"callback claimable notify failed for job {job['id']}: {e}")
        except Exception as e:
            logger.error(f"callback notifications failed for tenant {tid}: {e}")

    if due_count or claimable_count:
        logger.info(f"Callback notifications: {due_count} due, {claimable_count} claimable")
    return {"due": due_count, "claimable": claimable_count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_callback_notifications.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/callback_notifications.py backend/tests/test_callback_notifications.py
git commit -m "feat(callbacks): add due + claimable scanner (config-driven, no shift gate)"
```

---

### Task 5: Retire the auto-reassignment pipeline + wire the new job

**Files:**
- Modify: `backend/app/main.py` (remove `_process_callback_reassignments` wrapper ~219-228; remove its `add_job` ~363-369; add new job; update log ~391)
- Modify: `backend/app/services/assignment.py` (delete `process_callback_reassignments`, ~619-691)

**Interfaces:**
- Consumes: `process_callback_notifications` (Task 4).
- Produces: scheduler runs `callback-notifications` (1 min); `callback-reassignment` no longer exists.

- [ ] **Step 1: Remove the reassignment job wrapper in main.py**

Delete the entire `async def _process_callback_reassignments() -> None:` function (lines ~219-228).

- [ ] **Step 2: Replace the reassignment add_job with the notifications job**

In `lifespan`, replace the `callback-reassignment` `add_job(...)` block (~363-369) with:

```python
    _scheduler.add_job(
        _process_callback_notifications,
        trigger="interval",
        minutes=1,
        id="callback-notifications",
        replace_existing=True,
    )
```

- [ ] **Step 3: Add the new job wrapper in main.py**

Where `_process_callback_reassignments` used to be, add:

```python
async def _process_callback_notifications() -> None:
    """APScheduler job: callback 'due' reminders and 'claimable' broadcasts."""
    _heartbeats["callback-notifications"] = datetime.now(timezone.utc)
    try:
        from app.services.callback_notifications import process_callback_notifications
        result = process_callback_notifications()
        if result.get("due") or result.get("claimable"):
            logger.info(f"Callback notifications: {result['due']} due, {result['claimable']} claimable")
    except Exception as e:
        logger.error(f"Callback notifications error: {e}")
```

- [ ] **Step 4: Update the heartbeat dict and startup log**

In `main.py`, change the `_heartbeats` initializer key `"callback-reassignment": None,` (~line 36) to `"callback-notifications": None,`. Update the startup log line (~391) replacing `callback-reassign(1m)` with `callback-notify(1m)`.

- [ ] **Step 5: Delete the retired service function**

In `backend/app/services/assignment.py`, delete the whole `def process_callback_reassignments() -> int:` function (lines ~619-691). (`_in_shift_caller_ids` may now be unused; leave it — it is a harmless helper.)

- [ ] **Step 6: Verify imports + no dangling references**

Run: `cd backend && python -c "import app.main; import app.services.assignment; print('ok')"`
Expected: prints `ok`.

Run: `cd backend && grep -rn "process_callback_reassignments\|callback-reassignment" app/`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/services/assignment.py
git commit -m "feat(scheduler): replace callback auto-reassignment with claimable notifications job"
```

---

### Task 6: Reset guard columns on reschedule

**Files:**
- Modify: `backend/app/routes/follow_ups.py:377-386`

- [ ] **Step 1: Update the reschedule mutation**

In `reschedule_callback`, change the update payload to also null the guards:

```python
    update_res = (
        db.table("follow_up_jobs")
        .update({
            "scheduled_for": payload.scheduled_for,
            "status": "pending",
            "due_notified_at": None,
            "claimable_notified_at": None,
        })
        .eq("id", job_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
```

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "import app.routes.follow_ups; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routes/follow_ups.py
git commit -m "fix(callbacks): re-arm notification guards on reschedule"
```

---

### Task 7: Flow #3 — push on claim

**Files:**
- Modify: `backend/app/routes/leads.py:1238-1245` (inside `takeover_lead`)

- [ ] **Step 1: Replace the raw insert with notify_user**

```python
    if prev_caller_user_id:
        from app.services.notify import notify_user
        notify_user(
            tenant_id,
            prev_caller_user_id,
            "callback_taken_over",
            "Callback claimed",
            f"{me_name} claimed your callback for '{lead_data.get('name') or 'Unknown'}'.",
            db=db,
            push_url="/dashboard/telecalling/scheduled",
        )
```

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "import app.routes.leads; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routes/leads.py
git commit -m "feat(callbacks): web push (not just bell) when a callback is claimed"
```

---

### Task 8: Config API endpoints

**Files:**
- Modify: `backend/app/routes/notifications.py`

**Interfaces:**
- Consumes: `get_notification_config`, `save_notification_config`, `_NOTIFICATION_CONFIG_DEFAULT`; `require_owner`.
- Produces:
  - `GET /api/v1/notifications/config` → the merged config dict (owner-only).
  - `PUT /api/v1/notifications/config` → validates and saves; returns the saved config (owner-only).

- [ ] **Step 1: Add the Pydantic model and routes**

In `backend/app/routes/notifications.py`, add (adjust imports to match the file's existing style — it already imports `get_supabase` and tenant deps):

```python
from pydantic import BaseModel, Field
from app.dependencies.tenant import require_owner
from app.services.notification_config import (
    get_notification_config,
    save_notification_config,
    _NOTIFICATION_CONFIG_DEFAULT,
)

_VALID_AUDIENCE = {"telecallers_and_admin", "telecallers_only", "admin_only", "specific"}


class QuietHours(BaseModel):
    enabled: bool = False
    start_hour: int = Field(22, ge=0, le=23)
    end_hour: int = Field(8, ge=0, le=23)


class NotificationConfigIn(BaseModel):
    push_enabled: bool = True
    events: dict[str, bool] = {}
    claimable_threshold_minutes: int = Field(15, ge=1, le=120)
    claimable_audience: str = "telecallers_and_admin"
    claimable_caller_ids: list[str] = []
    quiet_hours: QuietHours = QuietHours()


@router.get("/config")
async def get_config(ctx: dict = Depends(require_owner)):
    return get_notification_config(ctx["tenant_id"])


@router.put("/config")
async def update_config(payload: NotificationConfigIn, ctx: dict = Depends(require_owner)):
    if payload.claimable_audience not in _VALID_AUDIENCE:
        raise HTTPException(status_code=422, detail="Invalid claimable_audience")
    # Whitelist event keys to the known set; ignore unknown keys.
    allowed_events = set(_NOTIFICATION_CONFIG_DEFAULT["events"].keys())
    events = {k: bool(v) for k, v in payload.events.items() if k in allowed_events}
    # caller_ids only meaningful for the "specific" audience; store [] otherwise.
    caller_ids = (
        [str(c) for c in payload.claimable_caller_ids]
        if payload.claimable_audience == "specific" else []
    )
    config = {
        "push_enabled": payload.push_enabled,
        "events": {**_NOTIFICATION_CONFIG_DEFAULT["events"], **events},
        "claimable_threshold_minutes": payload.claimable_threshold_minutes,
        "claimable_audience": payload.claimable_audience,
        "claimable_caller_ids": caller_ids,
        "quiet_hours": payload.quiet_hours.model_dump(),
    }
    save_notification_config(ctx["tenant_id"], config)
    return config
```

Update `_VALID_AUDIENCE` to include `"specific"`:

```python
_VALID_AUDIENCE = {"telecallers_and_admin", "telecallers_only", "admin_only", "specific"}
```

Ensure `HTTPException` and `Depends` are imported at the top of the file (add to the existing FastAPI import if missing).

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "import app.routes.notifications; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Manual smoke test**

Start the server, then (with an owner token) `GET /api/v1/notifications/config` returns the default config; `PUT` with `{"claimable_threshold_minutes": 20}` returns the merged config with `20`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/notifications.py
git commit -m "feat(api): notification config GET/PUT (owner-only)"
```

---

### Task 9: Frontend API client methods

**Files:**
- Modify: `frontend/lib/api.ts` (the `notifications:` object, ~line 1474)

**Interfaces:**
- Produces: `api.notifications.getConfig()` and `api.notifications.saveConfig(config)` returning/accepting `NotificationConfig`.

- [ ] **Step 1: Add the type and methods**

Add a `NotificationConfig` type near the other config types and extend the `notifications` API object:

```typescript
export type NotificationConfig = {
  push_enabled: boolean;
  events: Record<string, boolean>;
  claimable_threshold_minutes: number;
  claimable_audience: "telecallers_and_admin" | "telecallers_only" | "admin_only" | "specific";
  claimable_caller_ids: string[];
  quiet_hours: { enabled: boolean; start_hour: number; end_hour: number };
};
```

Inside `notifications: { ... }`:

```typescript
    getConfig: () => apiFetch<NotificationConfig>("/api/v1/notifications/config"),
    saveConfig: (config: NotificationConfig) =>
      apiFetch<NotificationConfig>("/api/v1/notifications/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
```

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api-client): notification config get/save"
```

---

### Task 10: Notifications settings panel + tab

**Files:**
- Create: `frontend/app/dashboard/settings/NotificationConfigPanel.tsx`
- Modify: `frontend/app/dashboard/settings/page.tsx` (add tab button + render)

**Interfaces:**
- Consumes: `api.notifications.getConfig/saveConfig`, `NotificationConfig`.

- [ ] **Step 1: Build the panel**

Create `frontend/app/dashboard/settings/NotificationConfigPanel.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";
import { Bell, Save, Loader2, CheckCircle2 } from "lucide-react";
import { api, NotificationConfig, Caller } from "@/lib/api";

const EVENT_LABELS: Record<string, string> = {
  callback_due: "Callback due reminder",
  callback_claimable: "Callback open to claim",
  callback_taken_over: "Your callback was claimed",
  lead_assigned: "New lead assigned",
  lead_replied: "Lead replied",
  handover_new: "Chat handover needed",
};

const AUDIENCE_OPTIONS: { value: NotificationConfig["claimable_audience"]; label: string }[] = [
  { value: "telecallers_and_admin", label: "Telecallers + Admin" },
  { value: "telecallers_only", label: "Telecallers only" },
  { value: "admin_only", label: "Admin only" },
  { value: "specific", label: "Specific telecallers" },
];

export function NotificationConfigPanel() {
  const [cfg, setCfg] = useState<NotificationConfig | null>(null);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [state, setState] = useState<"idle" | "dirty" | "saving" | "saved">("idle");

  useEffect(() => {
    api.notifications.getConfig().then(setCfg).catch(() => {});
    api.callers.list().then((res) => setCallers((res.data || []).filter((c) => c.active))).catch(() => {});
  }, []);

  function patch(next: Partial<NotificationConfig>) {
    setCfg((c) => (c ? { ...c, ...next } : c));
    setState("dirty");
  }

  async function save() {
    if (!cfg) return;
    setState("saving");
    try {
      const saved = await api.notifications.saveConfig(cfg);
      setCfg(saved);
      setState("saved");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState("dirty");
    }
  }

  if (!cfg) {
    return <div className="card rounded-3xl h-56 animate-pulse bg-border-subtle" />;
  }

  return (
    <div className="card rounded-3xl animate-slide-up">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center" style={{ background: "#ede9fe" }}>
          <Bell size={18} style={{ color: "#7c3aed" }} />
        </div>
        <div>
          <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem" }}>Push Notifications</h2>
          <p className="font-body text-sm text-ink-muted mt-0.5">
            Control which push alerts your team receives. The in-app bell always records every event.
          </p>
        </div>
      </div>

      {/* Master switch */}
      <div className="mt-6 flex items-center justify-between p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
        <div>
          <p className="font-body text-sm font-semibold text-ink">Enable push notifications</p>
          <p className="font-body text-xs text-ink-muted mt-0.5">Master switch for all phone/desktop pushes.</p>
        </div>
        <Toggle on={cfg.push_enabled} onClick={() => patch({ push_enabled: !cfg.push_enabled })} />
      </div>

      {/* Per-event toggles */}
      <div className="mt-4 space-y-2">
        <p className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Per-event push</p>
        {Object.keys(EVENT_LABELS).map((key) => {
          const on = cfg.events[key] ?? true;
          return (
            <div key={key} className="flex items-center justify-between p-3 rounded-xl bg-surface-subtle border border-border-subtle">
              <span className="font-body text-sm text-ink">{EVENT_LABELS[key]}</span>
              <Toggle
                on={on}
                disabled={!cfg.push_enabled}
                onClick={() => patch({ events: { ...cfg.events, [key]: !on } })}
              />
            </div>
          );
        })}
      </div>

      {/* Claimable threshold + audience */}
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
          <label className="font-body text-sm font-semibold text-ink">Claimable after (minutes)</label>
          <p className="font-body text-xs text-ink-muted mt-0.5 mb-2">How long after the slot a callback opens to claim.</p>
          <input
            type="number" min={1} max={120}
            value={cfg.claimable_threshold_minutes}
            onChange={(e) => patch({ claimable_threshold_minutes: Math.max(1, Math.min(120, parseInt(e.target.value) || 1)) })}
            className="w-24 px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
          />
        </div>
        <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
          <label className="font-body text-sm font-semibold text-ink">Claimable broadcast to</label>
          <p className="font-body text-xs text-ink-muted mt-0.5 mb-2">Who gets the "open to claim" alert.</p>
          <select
            value={cfg.claimable_audience}
            onChange={(e) => patch({ claimable_audience: e.target.value as NotificationConfig["claimable_audience"] })}
            className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm text-ink focus:outline-none focus:border-primary"
          >
            {AUDIENCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          {cfg.claimable_audience === "specific" && (
            <div className="mt-3 space-y-1.5 max-h-44 overflow-y-auto rounded-xl border border-border bg-white p-2">
              {callers.length === 0 ? (
                <p className="font-body text-xs text-ink-muted px-1 py-2">No telecallers found.</p>
              ) : (
                callers.map((c) => {
                  const checked = cfg.claimable_caller_ids.includes(c.id);
                  return (
                    <label key={c.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-subtle cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          patch({
                            claimable_caller_ids: checked
                              ? cfg.claimable_caller_ids.filter((id) => id !== c.id)
                              : [...cfg.claimable_caller_ids, c.id],
                          })
                        }
                        className="accent-primary"
                      />
                      <span className="font-body text-sm text-ink">{c.name}</span>
                    </label>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>

      {/* Quiet hours */}
      <div className="mt-4 p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-body text-sm font-semibold text-ink">Quiet hours</p>
            <p className="font-body text-xs text-ink-muted mt-0.5">Suppress pushes overnight (in-app bell still records them).</p>
          </div>
          <Toggle on={cfg.quiet_hours.enabled} onClick={() => patch({ quiet_hours: { ...cfg.quiet_hours, enabled: !cfg.quiet_hours.enabled } })} />
        </div>
        {cfg.quiet_hours.enabled && (
          <div className="mt-3 flex items-center gap-2">
            <HourSelect value={cfg.quiet_hours.start_hour} onChange={(h) => patch({ quiet_hours: { ...cfg.quiet_hours, start_hour: h } })} />
            <span className="text-ink-muted text-sm">to</span>
            <HourSelect value={cfg.quiet_hours.end_hour} onChange={(h) => patch({ quiet_hours: { ...cfg.quiet_hours, end_hour: h } })} />
            <span className="text-ink-muted text-xs">IST</span>
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center justify-end border-t border-border-subtle pt-5">
        <button
          onClick={save}
          disabled={state === "saving" || state === "idle" || state === "saved"}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
            state === "saved" ? "bg-emerald-100 text-emerald-700"
            : state === "dirty" ? "bg-primary text-white hover:bg-primary/90"
            : "bg-surface-subtle text-ink-muted cursor-default"
          }`}
        >
          {state === "saving" ? <><Loader2 size={14} className="animate-spin" />Saving…</>
            : state === "saved" ? <><CheckCircle2 size={14} />Saved</>
            : <><Save size={14} />Save Changes</>}
        </button>
      </div>
    </div>
  );
}

function Toggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled}
      className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 ${on ? "bg-green-600" : "bg-gray-300"} ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}
    >
      <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform ${on ? "translate-x-5" : "translate-x-0"}`} />
    </button>
  );
}

function HourSelect({ value, onChange }: { value: number; onChange: (h: number) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value))}
      className="px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
    >
      {Array.from({ length: 24 }, (_, h) => (
        <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
      ))}
    </select>
  );
}
```

- [ ] **Step 2: Add the Notifications tab to the settings page**

In `frontend/app/dashboard/settings/page.tsx`:

1. Add the import at the top:
```tsx
import { NotificationConfigPanel } from "./NotificationConfigPanel";
```

2. Add a tab button after the Automations button (~line 432), matching the existing button style:
```tsx
        <button
          onClick={() => router.push(`${pathname}?tab=notifications`)}
          className={cn(
            "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
            activeTab === "notifications"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Notifications
        </button>
```

3. Add the tab body after the Automations block (~line 884):
```tsx
          {/* TAB 6: Notifications */}
          {activeTab === "notifications" && (
            <div className="space-y-6">
              <NotificationConfigPanel />
            </div>
          )}
```

- [ ] **Step 3: Verify typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: exit 0, no errors.

- [ ] **Step 4: Manual visual check**

Run: `cd frontend && npm run dev`, open `/dashboard/settings?tab=notifications` as an owner. Toggle an event off, change the threshold, save, reload — values persist.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/NotificationConfigPanel.tsx frontend/app/dashboard/settings/page.tsx
git commit -m "feat(settings): add Notifications tab with push config panel"
```

---

### Task 11: Full regression pass

- [ ] **Step 1: Backend tests**

Run: `cd backend && pytest -q`
Expected: PASS (no regressions; new suites green).

- [ ] **Step 2: Frontend checks**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: typecheck clean, build succeeds.

- [ ] **Step 3: Commit (if any incidental fixes were needed)**

```bash
git add -A
git commit -m "test: green regression for callback notifications + push config"
```

---

## Known limitations (intentional, v1)

- **Timing precision:** the scanner runs every 1 minute, so "due now" can land up to ~60s late.
- **Push tag collapse:** without `dedupe_lead_id`, simultaneous same-type pushes to one device may collapse to the latest on the lock screen; the in-app bell keeps all.
- **Config read per notification:** `push_allowed` reads `notification_config` on each `notify_user`. Fine at current volume; add a short TTL cache if it becomes hot.
- **Delivery still device-gated:** admin config governs intent; a user only receives push if they granted browser permission and have a `push_subscriptions` row. A "X of Y team members have push enabled" indicator is a future add (needs a tenant-wide status endpoint).

## Self-Review

- **Spec coverage:** Flow #1 (due) → Task 4 + 5. Flow #2 (claimable, no shift, config audience/threshold, push to all enrolled) → Tasks 2(config)+3(notify)+4(scanner). Flow #3 (claim push) → Task 7. Retire reassignment → Task 5. Configurable settings (per-event toggles, threshold, audience, quiet hours, admin-only, new tab) → Tasks 2,8,9,10. Guard/reschedule → Tasks 1,6.
- **Type consistency:** `process_callback_notifications() -> {"due","claimable"}` consistent (Task 4/5). `notify_callback_claimable(..., audience, exclude_user_ids, db)` matches its call in Task 4. `get_notification_config(tenant_id, db=None)` / `push_allowed(tenant_id, event_type, *, db=None)` signatures consistent across Tasks 2,3,4. `claimable_audience` values `telecallers_and_admin|telecallers_only|admin_only` identical in config default, endpoint validation, notify fan-out, and frontend type.
- **Placeholder scan:** none; every code step is complete.

Dependency order is strictly top-to-bottom: 1 → 2 (config) → 3 (notify) → 4 (scanner) → 5 (wire/retire) → 6 → 7 → 8 → 9 → 10 → 11.
