# Silence Nudge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send one short, contextual WhatsApp follow-up when a lead goes quiet a configurable number of minutes after a live AI reply.

**Architecture:** A timer row is written to `silence_nudge_jobs` when an AI reply lands, cancelled when anything else happens in the thread, and drained by a 1-minute APScheduler job that runs a gate sequence before sending. Deliberately a separate subsystem from `reengagement_service.py`, whose per-lead-forever dedup is structurally incompatible with a repeatable nudge.

**Tech Stack:** FastAPI, Supabase (PostgREST client), APScheduler, Next.js 14, pytest.

**Spec:** [docs/superpowers/specs/2026-08-23-silence-nudge-design.md](../specs/2026-08-23-silence-nudge-design.md)

## Global Constraints

- **Migration number is 183.** Latest existing is `182_analytics_returning_ad_leads.sql`.
- **`reply_source` CHECK constraint must be extended before any code writes `'silence_nudge'`.** Current allowed set, from migration 173: `('knowledge','ai','automation','reengagement','expert_handoff')`. Omitting this caused a live duplicate-reply incident (2026-08-11). The list intentionally excludes `'autopilot'` — do not reinstate it.
- **Feature is OFF by default.** `silence_nudge_enabled` defaults to `"false"` for every tenant.
- **WhatsApp only in v1.** Telegram / Instagram / Facebook never arm a timer.
- **The arm hook must never break a reply.** Wrapped in `try/except` that logs and continues.
- **The nudge prompt must never emit links, URLs, prices, or offers.** Commits `24494b3d` and `5716c840` fixed exactly these leaks.
- **Never call `_build_base_prompt()` from the nudge path** — it carries catalog context.
- **RLS:** the `ensure_rls` event trigger (migration 175) enables RLS automatically on `CREATE TABLE`. Add **no** policies. Backend uses the service-role client; no route exposes this table.
- **Correctness note that de-risks hook placement:** the send-time race re-check (Task 6) is what guarantees correctness. Cancellation (Task 7) is an optimisation. A missed cancel site costs a wasted row, never a wrong send.
- All timestamps stored UTC ISO. Quiet hours are IST, reusing `IST_OFFSET` from `growth.py` — do not introduce a second timezone convention.
- Backend tests: `cd backend && pytest`. Frontend verify: `npm run lint` **and** `npm run typecheck` (lint alone is what CI runs; tsc alone passes code that fails CI).

---

### Task 1: Migration 183 — constraint fix and timer table

**Files:**
- Create: `backend/supabase/migrations/183_silence_nudge.sql`

**Interfaces:**
- Consumes: nothing
- Produces: table `silence_nudge_jobs` with columns `id, tenant_id, lead_id, anchor_message_id, step_index, fire_at, status, skip_reason, message_preview, created_at, sent_at`; `messages.reply_source` accepts `'silence_nudge'`

- [ ] **Step 1: Write the migration**

```sql
-- 183_silence_nudge.sql
-- A short contextual follow-up sent minutes after a live AI reply that went
-- unanswered. Separate from reengagement_steps: that engine dedups per
-- (lead, step) with no time bound (one send per lead forever), which is
-- structurally incompatible with a nudge that must fire again on the next lull.

-- The constraint extension comes FIRST and is not optional. expert_handoff
-- inserted an unlisted reply_source from migration 168 to 173; every insert
-- raised 23514, the exception escaped _send_and_log(), and webhook.py fell
-- through to generate_reply() — answering the same inbound message twice.
-- Live-caught 2026-08-11. 'autopilot' is deliberately absent (dropped in 173).
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN ('knowledge','ai','automation','reengagement','expert_handoff','silence_nudge'));

CREATE TABLE IF NOT EXISTS silence_nudge_jobs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  lead_id           uuid NOT NULL,
  -- The outbound message that started the clock. At fire time the newest
  -- message in the thread must still be this one, or the lead has replied.
  anchor_message_id uuid NOT NULL,
  step_index        int  NOT NULL DEFAULT 0,
  fire_at           timestamptz NOT NULL,
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','sent','cancelled','skipped','failed')),
  skip_reason       text,
  message_preview   text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  sent_at           timestamptz
);

CREATE INDEX IF NOT EXISTS idx_silence_nudge_due
  ON silence_nudge_jobs (fire_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_silence_nudge_lead_pending
  ON silence_nudge_jobs (lead_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_silence_nudge_cap
  ON silence_nudge_jobs (lead_id, sent_at) WHERE status = 'sent';

-- RLS is enabled automatically by the ensure_rls event trigger (migration 175).
-- No policies by design: anon and authenticated are denied outright, and the
-- backend reaches this table only through the service-role client. The absence
-- of policies IS the security posture — do not "fix" it with a permissive one.
```

- [ ] **Step 2: Apply the migration**

Apply via the Supabase MCP `apply_migration` tool against the project Render uses, with name `silence_nudge`.

- [ ] **Step 3: Verify both halves landed**

Run this via Supabase `execute_sql`:

```sql
SELECT pg_get_constraintdef(oid) AS def
FROM pg_constraint WHERE conname = 'messages_reply_source_check';

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'silence_nudge_jobs' ORDER BY ordinal_position;

SELECT relrowsecurity FROM pg_class WHERE relname = 'silence_nudge_jobs';
```

Expected: constraint def contains `silence_nudge`; 11 columns listed; `relrowsecurity` is `true`.

- [ ] **Step 4: Commit**

```bash
git add backend/supabase/migrations/183_silence_nudge.sql
git commit -m "feat(db): add silence_nudge_jobs and allow silence_nudge reply_source"
```

---

### Task 2: Shared automation guards

**Files:**
- Create: `backend/app/services/automation_guards.py`
- Create: `backend/tests/test_automation_guards.py`
- Modify: `backend/app/services/reengagement_service.py:245-280` (`_send_reengagement`)

**Interfaces:**
- Consumes: `app.config_dynamic.get_setting`
- Produces:
  - `master_switch_on(tenant_id: str) -> bool`
  - `lead_blocks_automated_outbound(lead: dict) -> str | None` — returns a skip reason, or `None` if sending is allowed

> **Scope correction against the spec.** Spec §10 said the shared guard covers gates 1–4. Implementation review shows `_send_reengagement()` checks only `phone`, `whatsapp_undeliverable`, and `opted_out` — it does **not** check `ai_enabled`, `converted_at`, or `blocked_at`. Extracting a guard that checked more would silently change re-engagement behaviour. So the shared guard covers **only the three genuinely identical checks**, and `silence_nudge.py` performs its own additional lead checks in Task 4. This is behaviour-preserving by construction.

- [ ] **Step 1: Write characterisation tests for the CURRENT behaviour**

Create `backend/tests/test_automation_guards.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _lead(**over):
    base = {"id": "lead-1", "name": "Asha", "phone": "919999999999",
            "opted_out": False, "whatsapp_undeliverable": False}
    base.update(over)
    return base


def _step():
    return {"id": "step-1", "message_type": "freeform",
            "message_content": "Hi there!", "fallback_template_name": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("lead,expected_reason", [
    (_lead(phone=None), "no phone"),
    (_lead(whatsapp_undeliverable=True), "whatsapp undeliverable"),
    (_lead(opted_out=True), "opted out"),
    (_lead(), None),
])
async def test_lead_gate_reasons(lead, expected_reason):
    from app.services.automation_guards import lead_blocks_automated_outbound
    assert lead_blocks_automated_outbound(lead) == expected_reason


def test_master_switch_defaults_on():
    from app.services import automation_guards as g
    with patch.object(g, "get_setting", return_value=None):
        assert g.master_switch_on("t1") is True


def test_master_switch_off_only_on_literal_false():
    from app.services import automation_guards as g
    with patch.object(g, "get_setting", return_value="false"):
        assert g.master_switch_on("t1") is False
    with patch.object(g, "get_setting", return_value="true"):
        assert g.master_switch_on("t1") is True


@pytest.mark.asyncio
async def test_reengagement_still_skips_blocked_leads_without_logging():
    """Characterisation: blocked leads write NO reengagement_logs row, so the
    step resumes for them later rather than being marked permanently processed."""
    from app.services import reengagement_service as svc
    logs = []
    db = MagicMock()

    def table_selector(name):
        t = MagicMock()
        if name == "reengagement_logs":
            def _insert(row):
                logs.append(row)
                res = MagicMock()
                res.execute.return_value.data = [{"id": "log-1"}]
                return res
            t.insert.side_effect = _insert
        else:
            t.insert.return_value.execute.return_value.data = [{"id": "x"}]
        return t

    db.table.side_effect = table_selector

    with patch.object(svc, "send_whatsapp", new=AsyncMock()) as wa, \
         patch.object(svc, "get_setting", return_value="true"):
        ok = await svc._send_reengagement(db, "t1", _lead(opted_out=True), _step())

    assert ok is False
    wa.assert_not_awaited()
    assert logs == []
```

- [ ] **Step 2: Run to verify the new-module tests fail**

Run: `cd backend && pytest tests/test_automation_guards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.automation_guards'`. The `test_reengagement_still_skips_blocked_leads_without_logging` test should PASS already (it characterises existing behaviour).

- [ ] **Step 3: Write the guard module**

Create `backend/app/services/automation_guards.py`:

```python
"""Gates shared by every automated AI-authored outbound path.

Deliberately narrow. It covers ONLY the three lead-level checks that
reengagement_service and silence_nudge genuinely share. reengagement does not
check ai_enabled/converted_at/blocked_at, so those are NOT here — widening this
module would silently change re-engagement behaviour.
"""
import logging

from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)


def master_switch_on(tenant_id: str) -> bool:
    """ai_auto_reply_enabled is the single master switch for every automated
    AI-authored outbound message, not just inbound replies. Callers decide
    whether an off switch consumes their job or leaves it queued."""
    return get_setting("ai_auto_reply_enabled", fallback="true", tenant_id=tenant_id) != "false"


def lead_blocks_automated_outbound(lead: dict) -> str | None:
    """Return a human-readable skip reason, or None if sending is allowed."""
    if not lead.get("phone"):
        return "no phone"
    if lead.get("whatsapp_undeliverable"):
        return "whatsapp undeliverable"
    if lead.get("opted_out"):
        return "opted out"
    return None
```

- [ ] **Step 4: Run the new tests**

Run: `cd backend && pytest tests/test_automation_guards.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Rewire `_send_reengagement` to call the guard**

In `backend/app/services/reengagement_service.py`, add the import at the top:

```python
from app.services.automation_guards import lead_blocks_automated_outbound, master_switch_on
```

Replace the three inline checks in `_send_reengagement` (the `ai_auto_reply_enabled` block at ~L258, the `whatsapp_undeliverable` block at ~L270, and the `opted_out` block at ~L276) with:

```python
    if not master_switch_on(tenant_id):
        logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} (ai_auto_reply disabled for tenant {tenant_id})")
        return False
    message_type = step["message_type"]

    # No log row on any of these skips: re-engagement should resume for this
    # lead+step once the blocker clears, not be permanently marked processed.
    block_reason = lead_blocks_automated_outbound(lead)
    if block_reason:
        logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} ({block_reason})")
        return False
```

Delete the now-dead `if not phone: return False` line — `lead_blocks_automated_outbound` covers it and returns the same `False`.

- [ ] **Step 6: Confirm re-engagement is unchanged**

Run: `cd backend && pytest tests/test_automation_guards.py tests/test_reengagement_service.py -v`
Expected: PASS, all tests, no failures in the pre-existing re-engagement suite.

> **If any re-engagement test fails here, stop.** Per spec §10 the fallback is to revert this rewire, duplicate the three checks inside `silence_nudge.py`, and log the duplication in `.agents/projects/active-backlog.md` as tech debt. A working re-engagement engine is worth more than a DRY one.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/automation_guards.py backend/tests/test_automation_guards.py backend/app/services/reengagement_service.py
git commit -m "refactor: extract shared automation guards from reengagement_service"
```

---

### Task 3: Config parsing and quiet-hours helpers

**Files:**
- Create: `backend/app/services/silence_nudge.py`
- Create: `backend/tests/test_silence_nudge.py`

**Interfaces:**
- Consumes: `app.config_dynamic.get_setting`, `app.services.growth.IST_OFFSET`
- Produces:
  - `_parse_delays(raw: str | None) -> list[int]`
  - `_parse_cap(raw: str | None) -> int`
  - `_parse_time(raw: str | None, fallback: time) -> time`
  - `_in_quiet_window(now_ist: time, start: time, end: time) -> bool`
  - `_next_window_end(now_utc: datetime, end: time) -> datetime`
  - `_now() -> datetime` — the module's single clock, so tests can pin it
  - `_quiet_window(tenant_id) -> tuple[time, time]`, `_delays_for(tenant_id) -> list[int]`, `_enabled_for(tenant_id) -> bool`
  - Constants `DEFAULT_DELAYS`, `DEFAULT_CAP`, `MAX_RUNGS`, `SILENCE_NUDGE_FALLBACK`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_silence_nudge.py`:

```python
import pytest
from datetime import datetime, time, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch


# ---------- config parsing ----------

@pytest.mark.parametrize("raw,expected", [
    ("5", [5]),
    ("5,60", [5, 60]),
    (" 5 , 60 ", [5, 60]),
    ("", [5]),
    (None, [5]),
    ("abc", [5]),          # unparseable -> safe default
    ("0", [5]),            # below floor -> safe default
    ("2000", [5]),         # above 1440 -> safe default
    ("60,5", [5]),         # not increasing -> safe default
    ("5,5", [5]),          # duplicates -> safe default
    ("5,60,120,240", [5, 60, 120]),  # capped at MAX_RUNGS
])
def test_parse_delays(raw, expected):
    from app.services.silence_nudge import _parse_delays
    assert _parse_delays(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1", 1), ("3", 3), ("10", 10),
    (None, 1), ("", 1), ("abc", 1), ("0", 1), ("99", 1),
])
def test_parse_cap(raw, expected):
    from app.services.silence_nudge import _parse_cap
    assert _parse_cap(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("21:00", time(21, 0)),
    ("09:30", time(9, 30)),
    ("nonsense", time(21, 0)),
    (None, time(21, 0)),
    ("25:00", time(21, 0)),
])
def test_parse_time_falls_back(raw, expected):
    from app.services.silence_nudge import _parse_time
    assert _parse_time(raw, time(21, 0)) == expected


# ---------- quiet window ----------

@pytest.mark.parametrize("now,inside", [
    (time(22, 0), True),    # after start, before midnight
    (time(3, 0), True),     # after midnight, before end
    (time(8, 59), True),    # just before end
    (time(9, 0), False),    # exactly end -> open
    (time(12, 0), False),   # midday
    (time(20, 59), False),  # just before start
    (time(21, 0), True),    # exactly start -> quiet
])
def test_in_quiet_window_wraps_midnight(now, inside):
    from app.services.silence_nudge import _in_quiet_window
    assert _in_quiet_window(now, time(21, 0), time(9, 0)) is inside


@pytest.mark.parametrize("now,inside", [
    (time(13, 0), True), (time(11, 59), False), (time(15, 0), False),
])
def test_in_quiet_window_same_day(now, inside):
    from app.services.silence_nudge import _in_quiet_window
    assert _in_quiet_window(now, time(12, 0), time(14, 0)) is inside


def test_in_quiet_window_disabled_when_start_equals_end():
    from app.services.silence_nudge import _in_quiet_window
    assert _in_quiet_window(time(3, 0), time(9, 0), time(9, 0)) is False


def test_next_window_end_is_same_morning_when_before_end():
    from app.services.silence_nudge import _next_window_end
    from app.services.growth import IST_OFFSET
    # 03:00 IST on the 10th -> 09:00 IST on the 10th
    now_utc = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc) - IST_OFFSET
    got_ist = _next_window_end(now_utc, time(9, 0)) + IST_OFFSET
    assert (got_ist.day, got_ist.hour, got_ist.minute) == (10, 9, 0)


def test_next_window_end_rolls_to_tomorrow_when_after_end():
    from app.services.silence_nudge import _next_window_end
    from app.services.growth import IST_OFFSET
    # 22:00 IST on the 10th -> 09:00 IST on the 11th
    now_utc = datetime(2026, 8, 10, 22, 0, tzinfo=timezone.utc) - IST_OFFSET
    got_ist = _next_window_end(now_utc, time(9, 0)) + IST_OFFSET
    assert (got_ist.day, got_ist.hour, got_ist.minute) == (11, 9, 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.silence_nudge'`

- [ ] **Step 3: Write the module**

Create `backend/app/services/silence_nudge.py`:

```python
"""Silence nudge — a short contextual follow-up sent minutes after a live AI
reply that went unanswered.

Separate from reengagement_service by design: that engine dedups per
(lead, step) with no time bound, which cannot express "fire again on the next
lull". See docs/superpowers/specs/2026-08-23-silence-nudge-design.md.
"""
import logging
from datetime import datetime, time, timedelta, timezone

from app.config_dynamic import get_setting
from app.services.growth import IST_OFFSET

logger = logging.getLogger(__name__)

DEFAULT_DELAYS = "5"
DEFAULT_CAP = 1
MAX_RUNGS = 3
MIN_DELAY_MINUTES = 1
MAX_DELAY_MINUTES = 1440
MAX_CAP = 10
DEFAULT_QUIET_START = time(21, 0)
DEFAULT_QUIET_END = time(9, 0)
SILENCE_NUDGE_FALLBACK = "Hey, can I help you with anything further?"


def _now() -> datetime:
    """Single clock for the whole module. Indirection so tests can pin it."""
    return datetime.now(timezone.utc)


def _parse_delays(raw: str | None) -> list[int]:
    """Comma-separated minutes, e.g. "5" or "5,60".

    The settings API rejects bad input on save; this is the runtime backstop for
    values edited straight into the DB. Any malformed config falls back to the
    single safe default rather than guessing.
    """
    fallback = [int(DEFAULT_DELAYS)]
    if not raw or not raw.strip():
        return fallback
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = int(part)
        except ValueError:
            logger.warning("silence_nudge: unparseable delay %r — using default", part)
            return fallback
        if not MIN_DELAY_MINUTES <= val <= MAX_DELAY_MINUTES:
            logger.warning("silence_nudge: delay %s out of range — using default", val)
            return fallback
        out.append(val)
    if not out or out != sorted(set(out)):
        logger.warning("silence_nudge: delays %r not strictly increasing — using default", raw)
        return fallback
    return out[:MAX_RUNGS]


def _parse_cap(raw: str | None) -> int:
    try:
        val = int((raw or "").strip())
    except ValueError:
        return DEFAULT_CAP
    return val if 1 <= val <= MAX_CAP else DEFAULT_CAP


def _parse_time(raw: str | None, fallback: time) -> time:
    try:
        hh, mm = (raw or "").strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return fallback


def _in_quiet_window(now_ist: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= now_ist < end
    return now_ist >= start or now_ist < end  # wraps midnight


def _next_window_end(now_utc: datetime, end: time) -> datetime:
    """The next moment the quiet window closes, in UTC."""
    now_ist = now_utc + IST_OFFSET
    candidate = now_ist.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= now_ist:
        candidate += timedelta(days=1)
    return candidate - IST_OFFSET


def _quiet_window(tenant_id: str) -> tuple[time, time]:
    return (
        _parse_time(get_setting("silence_nudge_quiet_start", tenant_id=tenant_id), DEFAULT_QUIET_START),
        _parse_time(get_setting("silence_nudge_quiet_end", tenant_id=tenant_id), DEFAULT_QUIET_END),
    )


def _delays_for(tenant_id: str) -> list[int]:
    return _parse_delays(get_setting("silence_nudge_delays", fallback=DEFAULT_DELAYS, tenant_id=tenant_id))


def _enabled_for(tenant_id: str) -> bool:
    return get_setting("silence_nudge_enabled", fallback="false", tenant_id=tenant_id) == "true"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: PASS, all parametrized cases.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/silence_nudge.py backend/tests/test_silence_nudge.py
git commit -m "feat: silence nudge config parsing and quiet-hours helpers"
```

---

### Task 4: Arm, cancel, and the gate sequence

**Files:**
- Modify: `backend/app/services/silence_nudge.py`
- Modify: `backend/tests/test_silence_nudge.py`

**Interfaces:**
- Consumes: `automation_guards.master_switch_on`, `automation_guards.lead_blocks_automated_outbound`
- Produces:
  - `arm(db, tenant_id: str, lead_id: str, anchor_message_id: str, step_index: int = 0) -> bool`
  - `cancel_pending(db, lead_id: str) -> None`
  - `maybe_arm_after_ai_reply(db, *, tenant_id, lead_id, channel, is_ai, sid, reply_source, inserted) -> bool`
  - `_evaluate_gates(db, job: dict, lead: dict) -> tuple[str, str | None]` returning action in `SEND` / `HOLD` / `SKIP`
  - Action constants `SEND = "send"`, `HOLD = "hold"`, `SKIP = "skip"`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_silence_nudge.py`:

```python
# ---------- db mock ----------

def _db(*, lead=None, newest_id="msg-anchor", handover=False,
        intake=False, sent_today=0, inserted_id="msg-new"):
    """Supabase mock covering every table silence_nudge touches."""
    db = MagicMock()
    state = {"inserted": [], "updated": []}

    def table_selector(name):
        t = MagicMock()
        if name == "leads":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
                [lead] if lead else []
            )
        elif name == "messages":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = (
                [{"id": newest_id}]
            )
            def _ins(row):
                state["inserted"].append(row)
                res = MagicMock()
                res.execute.return_value.data = [{"id": inserted_id}]
                return res
            t.insert.side_effect = _ins
        elif name == "chat_handovers":
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
                [{"id": "h1"}] if handover else []
            )
        elif name == "intake_sessions":
            t.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = (
                [{"id": "i1"}] if intake else []
            )
        elif name == "silence_nudge_jobs":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value.data = (
                [{"id": f"j{i}"} for i in range(sent_today)]
            )
            def _ins(row):
                state["inserted"].append(row)
                res = MagicMock()
                res.execute.return_value.data = [{"id": "job-new"}]
                return res
            t.insert.side_effect = _ins
            def _upd(row):
                state["updated"].append(row)
                return MagicMock()
            t.update.side_effect = _upd
        return t

    db.table.side_effect = table_selector
    db._state = state
    return db


def _job(step_index=0, anchor="msg-anchor"):
    return {"id": "job-1", "tenant_id": "t1", "lead_id": "lead-1",
            "anchor_message_id": anchor, "step_index": step_index,
            "fire_at": datetime.now(timezone.utc).isoformat(), "status": "pending"}


def _ok_lead(**over):
    base = {"id": "lead-1", "name": "Asha", "phone": "919999999999",
            "ai_enabled": True, "converted_at": None, "blocked_at": None,
            "opted_out": False, "whatsapp_undeliverable": False,
            "needs_human_attention": False,
            "last_inbound_at": datetime.now(timezone.utc).isoformat()}
    base.update(over)
    return base


# ---------- arming ----------

def test_arm_inserts_pending_job_at_first_delay():
    from app.services import silence_nudge as sn
    db = _db()
    with patch.object(sn, "get_setting", return_value="5"):
        assert sn.arm(db, "t1", "lead-1", "msg-anchor", step_index=0) is True
    row = [r for r in db._state["inserted"] if "fire_at" in r][0]
    assert row["status"] == "pending"
    assert row["step_index"] == 0
    assert row["anchor_message_id"] == "msg-anchor"
    fire_at = datetime.fromisoformat(row["fire_at"])
    delta = (fire_at - datetime.now(timezone.utc)).total_seconds()
    assert 240 < delta < 320  # ~5 minutes


def test_arm_beyond_last_rung_does_nothing():
    from app.services import silence_nudge as sn
    db = _db()
    with patch.object(sn, "get_setting", return_value="5"):
        assert sn.arm(db, "t1", "lead-1", "msg-anchor", step_index=1) is False
    assert db._state["inserted"] == []


@pytest.mark.parametrize("kwargs", [
    {"channel": "telegram"},
    {"is_ai": False},
    {"sid": None},
    {"reply_source": "reengagement"},
    {"reply_source": "expert_handoff"},
    {"inserted": None},
])
def test_maybe_arm_rejects_non_qualifying_replies(kwargs):
    from app.services import silence_nudge as sn
    db = _db()
    base = dict(tenant_id="t1", lead_id="lead-1", channel="whatsapp", is_ai=True,
                sid="sid-1", reply_source="ai", inserted={"id": "msg-new"})
    base.update(kwargs)
    with patch.object(sn, "get_setting", return_value="true"):
        assert sn.maybe_arm_after_ai_reply(db, **base) is False
    assert db._state["inserted"] == []


@pytest.mark.parametrize("source", ["ai", "knowledge"])
def test_maybe_arm_accepts_live_ai_replies(source):
    from app.services import silence_nudge as sn
    db = _db()
    def setting(key, fallback=None, tenant_id=None):
        return "true" if key == "silence_nudge_enabled" else "5"
    with patch.object(sn, "get_setting", side_effect=setting):
        assert sn.maybe_arm_after_ai_reply(
            db, tenant_id="t1", lead_id="lead-1", channel="whatsapp", is_ai=True,
            sid="sid-1", reply_source=source, inserted={"id": "msg-new"}) is True


def test_maybe_arm_noop_when_feature_disabled():
    from app.services import silence_nudge as sn
    db = _db()
    with patch.object(sn, "get_setting", return_value="false"):
        assert sn.maybe_arm_after_ai_reply(
            db, tenant_id="t1", lead_id="lead-1", channel="whatsapp", is_ai=True,
            sid="sid-1", reply_source="ai", inserted={"id": "msg-new"}) is False


# ---------- gates ----------

def _gate(db, lead, *, enabled="true", master="true", cap="1"):
    from app.services import silence_nudge as sn
    def setting(key, fallback=None, tenant_id=None):
        return {"silence_nudge_enabled": enabled,
                "ai_auto_reply_enabled": master,
                "silence_nudge_daily_cap": cap}.get(key, fallback)
    with patch.object(sn, "get_setting", side_effect=setting), \
         patch("app.services.automation_guards.get_setting", side_effect=setting):
        return sn._evaluate_gates(db, _job(), lead)


def test_gate_passes_for_healthy_lead():
    from app.services.silence_nudge import SEND
    assert _gate(_db(lead=_ok_lead()), _ok_lead()) == (SEND, None)


@pytest.mark.parametrize("kw", [{"enabled": "false"}, {"master": "false"}])
def test_gate_holds_on_switches_so_job_stays_pending(kw):
    from app.services.silence_nudge import HOLD
    action, _ = _gate(_db(lead=_ok_lead()), _ok_lead(), **kw)
    assert action == HOLD


@pytest.mark.parametrize("lead,fragment", [
    (_ok_lead(phone=None), "no phone"),
    (_ok_lead(opted_out=True), "opted out"),
    (_ok_lead(whatsapp_undeliverable=True), "undeliverable"),
    (_ok_lead(ai_enabled=False), "ai disabled"),
    (_ok_lead(converted_at="2026-01-01T00:00:00+00:00"), "converted"),
    (_ok_lead(blocked_at="2026-01-01T00:00:00+00:00"), "blocked"),
    (_ok_lead(needs_human_attention=True), "escalated"),
])
def test_gate_skips_blocked_leads(lead, fragment):
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=lead), lead)
    assert action == SKIP and fragment in reason


def test_gate_skips_on_open_handover():
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=_ok_lead(), handover=True), _ok_lead())
    assert action == SKIP and "handover" in reason


def test_gate_skips_during_active_intake():
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=_ok_lead(), intake=True), _ok_lead())
    assert action == SKIP and "intake" in reason


def test_gate_skips_when_daily_cap_reached():
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=_ok_lead(), sent_today=1), _ok_lead(), cap="1")
    assert action == SKIP and "cap" in reason


def test_gate_allows_second_nudge_when_cap_is_two():
    from app.services.silence_nudge import SEND
    action, _ = _gate(_db(lead=_ok_lead(), sent_today=1), _ok_lead(), cap="2")
    assert action == SEND
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: FAIL with `AttributeError: module 'app.services.silence_nudge' has no attribute 'arm'`

- [ ] **Step 3: Implement arm, cancel, and gates**

Append to `backend/app/services/silence_nudge.py`:

```python
from app.services.automation_guards import lead_blocks_automated_outbound, master_switch_on

SEND = "send"
HOLD = "hold"
SKIP = "skip"

# Only these reply sources represent a live AI reply in an open thread.
# generate_reply() emits exactly these two (ai_reply.py L1568, L1620); every
# other source belongs to a different subsystem and must not arm a timer.
_LIVE_AI_SOURCES = ("ai", "knowledge")

_ACTIVE_INTAKE_STATUSES = ("pending", "paid", "in_progress")


def arm(db, tenant_id: str, lead_id: str, anchor_message_id: str, step_index: int = 0) -> bool:
    """Insert one pending timer. Returns False when the ladder has no such rung."""
    delays = _delays_for(tenant_id)
    if step_index >= len(delays):
        return False
    fire_at = _now() + timedelta(minutes=delays[step_index])
    db.table("silence_nudge_jobs").insert({
        "tenant_id": tenant_id,
        "lead_id": str(lead_id),
        "anchor_message_id": str(anchor_message_id),
        "step_index": step_index,
        "fire_at": fire_at.isoformat(),
        "status": "pending",
    }).execute()
    return True


def cancel_pending(db, lead_id: str, reason: str = "thread advanced") -> None:
    """Drop every pending timer for a lead. Called whenever the thread moves.

    This is an optimisation, not the correctness mechanism — _thread_unchanged()
    at fire time is what actually prevents a wrong send.
    """
    db.table("silence_nudge_jobs").update(
        {"status": "cancelled", "skip_reason": reason}
    ).eq("lead_id", str(lead_id)).eq("status", "pending").execute()


def maybe_arm_after_ai_reply(db, *, tenant_id, lead_id, channel, is_ai,
                             sid, reply_source, inserted) -> bool:
    """Called straight after generate_reply() stores its outbound message."""
    if channel != "whatsapp" or not is_ai or sid is None:
        return False
    if reply_source not in _LIVE_AI_SOURCES:
        return False
    if not inserted or not inserted.get("id"):
        return False
    if not _enabled_for(tenant_id):
        return False
    cancel_pending(db, lead_id)
    return arm(db, tenant_id, lead_id, inserted["id"], step_index=0)


def _has_open_handover(db, tenant_id: str, lead_id: str) -> bool:
    rows = (
        db.table("chat_handovers")
        .select("id")
        .eq("lead_id", str(lead_id))
        .eq("status", "open")
        .limit(1)
        .execute()
        .data
    ) or []
    return bool(rows)


def _has_active_intake(db, tenant_id: str, lead_id: str) -> bool:
    rows = (
        db.table("intake_sessions")
        .select("id")
        .eq("lead_id", str(lead_id))
        .in_("status", list(_ACTIVE_INTAKE_STATUSES))
        .limit(1)
        .execute()
        .data
    ) or []
    return bool(rows)


def _sent_in_last_24h(db, lead_id: str) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = (
        db.table("silence_nudge_jobs")
        .select("id")
        .eq("lead_id", str(lead_id))
        .eq("status", "sent")
        .gte("sent_at", since)
        .execute()
        .data
    ) or []
    return len(rows)


def _evaluate_gates(db, job: dict, lead: dict) -> tuple[str, str | None]:
    """Gates 1-7 of the spec. HOLD leaves the job pending; SKIP consumes it."""
    tenant_id = job["tenant_id"]
    lead_id = job["lead_id"]

    # Gates 1-2: master switches leave the job queued, so automation resumes
    # cleanly when the tenant flips them back on rather than losing the work.
    if not _enabled_for(tenant_id):
        return HOLD, "silence nudge disabled"
    if not master_switch_on(tenant_id):
        return HOLD, "ai auto reply disabled"

    # Gate 3-4: shared lead-level gates, plus the three silence-only checks
    # that reengagement deliberately does not perform.
    block = lead_blocks_automated_outbound(lead)
    if block:
        return SKIP, block
    if not lead.get("ai_enabled", True):
        return SKIP, "ai disabled for lead"
    if lead.get("converted_at"):
        return SKIP, "lead converted"
    if lead.get("blocked_at"):
        return SKIP, "lead blocked"

    # Gate 5: a lead waiting on a promised human callback must not get an
    # automated "anything else?" from the same business.
    if lead.get("needs_human_attention"):
        return SKIP, "escalated to human"
    if _has_open_handover(db, tenant_id, lead_id):
        return SKIP, "open handover"

    # Gate 6: intake sends its own holding messages; two uncoordinated
    # automated messages to a paying customer read as broken.
    if _has_active_intake(db, tenant_id, lead_id):
        return SKIP, "active intake session"

    # Gate 7
    cap = _parse_cap(get_setting("silence_nudge_daily_cap", fallback=str(DEFAULT_CAP), tenant_id=tenant_id))
    if _sent_in_last_24h(db, lead_id) >= cap:
        return SKIP, "daily cap reached"

    return SEND, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Confirm the intake status values are right**

The `_ACTIVE_INTAKE_STATUSES` tuple is the one guess in this task. Verify against the live schema before committing:

```sql
SELECT DISTINCT status FROM intake_sessions;
```

Run via Supabase `execute_sql`. Adjust `_ACTIVE_INTAKE_STATUSES` to the non-terminal statuses actually present (exclude anything meaning delivered/refunded/cancelled), and update the test's `intake=True` fixture if the values differ.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/silence_nudge.py backend/tests/test_silence_nudge.py
git commit -m "feat: silence nudge arming, cancellation and gate sequence"
```

---

### Task 5: The nudge copywriter

**Files:**
- Modify: `backend/app/services/ai_reply.py` (add after `generate_reengagement_message`, ~L748)
- Create: `backend/tests/test_silence_nudge_copy.py`

**Interfaces:**
- Consumes: `_recent_thread(db, lead_id, limit)`, `_llm_complete(prompt, max_tokens, tenant_id)`
- Produces: `async generate_silence_nudge(lead_id: str, db=None) -> str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_silence_nudge_copy.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _db():
    db = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"name": "Asha", "tenant_id": "t1"}
    ]
    db.table.return_value = t
    return db


_THREAD = [
    {"direction": "outbound", "content": "The property is 4.7 km from the festival ground."},
    {"direction": "inbound", "content": "How far is the property from the music fest?"},
]


@pytest.mark.asyncio
async def test_returns_trimmed_single_line():
    from app.services import ai_reply as ar
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(return_value="  Happy to help \n with the cycle rental if you need it.  ")):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == "Happy to help with the cycle rental if you need it."


@pytest.mark.asyncio
async def test_truncates_to_160_chars():
    from app.services import ai_reply as ar
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(return_value="x" * 400)):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert len(out) == 160


@pytest.mark.asyncio
async def test_falls_back_when_llm_raises():
    from app.services import ai_reply as ar
    from app.services.silence_nudge import SILENCE_NUDGE_FALLBACK
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(side_effect=RuntimeError("boom"))):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == SILENCE_NUDGE_FALLBACK


@pytest.mark.asyncio
async def test_prompt_bans_links_and_carries_thread():
    from app.services import ai_reply as ar
    spy = AsyncMock(return_value="ok")
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=spy):
        await ar.generate_silence_nudge("lead-1", db=_db())
    prompt = spy.await_args.args[0]
    assert "music fest" in prompt          # thread history reached the model
    assert "NEVER include links" in prompt  # the leak ban is present
    assert spy.await_args.kwargs["max_tokens"] == 60


@pytest.mark.asyncio
async def test_empty_thread_still_produces_a_prompt():
    from app.services import ai_reply as ar
    spy = AsyncMock(return_value="ok")
    with patch.object(ar, "_recent_thread", return_value=[]), \
         patch.object(ar, "_llm_complete", new=spy):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == "ok"
    assert "No prior conversation history available." in spy.await_args.args[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_silence_nudge_copy.py -v`
Expected: FAIL — `AttributeError: module 'app.services.ai_reply' has no attribute 'generate_silence_nudge'`

- [ ] **Step 3: Implement the copywriter**

Add to `backend/app/services/ai_reply.py`, immediately after `generate_reengagement_message`:

```python
async def generate_silence_nudge(lead_id: str, db=None) -> str:
    """One short line for a lead who went quiet minutes after a live AI reply.

    Deliberately does NOT go through _build_base_prompt(): that carries catalog
    context, and commits 24494b3d and 5716c840 both fixed link/catalog leaks
    into outbound copy. Keep this prompt self-contained and link-free.
    """
    from app.services.silence_nudge import SILENCE_NUDGE_FALLBACK

    db = db or get_supabase()
    lead = (
        db.table("leads")
        .select("name,tenant_id")
        .eq("id", str(lead_id))
        .limit(1)
        .execute()
    )
    lead_data = lead.data[0] if lead.data else {}
    tenant_id = lead_data.get("tenant_id")

    history_rows = list(reversed(_recent_thread(db, lead_id, limit=6)))
    history = "\n".join(
        f"{row.get('direction', 'unknown')}: {row.get('content', '').strip()}"
        for row in history_rows
        if (row.get("content") or "").strip()
    ) or "No prior conversation history available."

    prompt = f"""A customer was mid-conversation with a business on WhatsApp and has gone quiet.
Write ONE short line checking in on them.

Customer name: {lead_data.get("name") or "there"}
Recent conversation:
{history}

Rules:
- Under 160 characters. One sentence.
- No greeting — the conversation is already open.
- Refer naturally to whatever was just being discussed.
- Offer to help further. Low pressure, never pushy.
- NEVER include links, URLs, prices, discounts, or new offers.
- No markdown, no quotes, at most one emoji."""

    try:
        text = await _llm_complete(prompt, max_tokens=60, tenant_id=tenant_id)
        text = " ".join((text or "").split())
        if not text:
            return SILENCE_NUDGE_FALLBACK
        return text[:160]
    except Exception as e:
        logger.error(f"Silence nudge copy failed for lead {lead_id}: {e}")
        return SILENCE_NUDGE_FALLBACK
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_silence_nudge_copy.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_silence_nudge_copy.py
git commit -m "feat: silence nudge copywriter with explicit link ban"
```

---

### Task 6: Drain the due timers

**Files:**
- Modify: `backend/app/services/silence_nudge.py`
- Modify: `backend/tests/test_silence_nudge.py`

**Interfaces:**
- Consumes: `ai_reply.generate_silence_nudge`, `ai_reply.send_whatsapp`, `entitlements.check_quota`, `entitlements.meter`
- Produces: `async drain_due_nudges(limit: int = 100) -> int`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_silence_nudge.py`:

```python
# ---------- drain ----------

def _drain_db(job, lead, **kw):
    db = _db(lead=lead, **kw)
    orig = db.table.side_effect
    def selector(name):
        t = orig(name)
        if name == "silence_nudge_jobs":
            t.select.return_value.eq.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = [job]
        return t
    db.table.side_effect = selector
    return db


def _statuses(db):
    return [u.get("status") for u in db._state["updated"] if "status" in u]


async def _run_drain(db, *, enabled="true", master="true", cap="1", nudge="Still there?"):
    """Helper, not a test — awaited by the drain tests below."""
    from app.services import silence_nudge as sn
    def setting(key, fallback=None, tenant_id=None):
        return {"silence_nudge_enabled": enabled, "ai_auto_reply_enabled": master,
                "silence_nudge_daily_cap": cap, "silence_nudge_delays": "5,60",
                "silence_nudge_quiet_start": "21:00",
                "silence_nudge_quiet_end": "09:00"}.get(key, fallback)
    with patch.object(sn, "get_setting", side_effect=setting), \
         patch("app.services.automation_guards.get_setting", side_effect=setting), \
         patch.object(sn, "get_supabase", return_value=db), \
         patch.object(sn, "check_quota", return_value=True), \
         patch.object(sn, "meter"), \
         patch.object(sn, "generate_silence_nudge", new=AsyncMock(return_value=nudge)), \
         patch.object(sn, "send_whatsapp", new=AsyncMock(return_value="sid-1")) as wa:
        count = await sn.drain_due_nudges()
    return count, wa


@pytest.mark.asyncio
async def test_drain_sends_and_marks_sent():
    db = _drain_db(_job(), _ok_lead())
    count, wa = await _run_drain(db)
    assert count == 1
    wa.assert_awaited_once()
    assert "sent" in _statuses(db)
    msg = [r for r in db._state["inserted"] if r.get("direction") == "outbound"][0]
    assert msg["reply_source"] == "silence_nudge"
    assert msg["is_ai_generated"] is True


@pytest.mark.asyncio
async def test_drain_cancels_when_lead_replied_after_fire_time():
    """The race that matters: newest message is no longer our anchor."""
    db = _drain_db(_job(anchor="msg-anchor"), _ok_lead(), newest_id="msg-their-reply")
    count, wa = await _run_drain(db)
    assert count == 0
    wa.assert_not_awaited()
    assert "cancelled" in _statuses(db)


@pytest.mark.asyncio
async def test_drain_skips_when_handover_open():
    db = _drain_db(_job(), _ok_lead(), handover=True)
    count, wa = await _run_drain(db)
    assert count == 0
    wa.assert_not_awaited()
    assert "skipped" in _statuses(db)


@pytest.mark.asyncio
async def test_drain_holds_job_pending_when_master_switch_off():
    db = _drain_db(_job(), _ok_lead())
    count, wa = await _run_drain(db, master="false")
    assert count == 0
    wa.assert_not_awaited()
    assert _statuses(db) == []  # untouched, still pending


@pytest.mark.asyncio
async def test_drain_skips_when_24h_window_closed():
    stale = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    db = _drain_db(_job(), _ok_lead(last_inbound_at=stale))
    count, wa = await _run_drain(db)
    assert count == 0
    wa.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_arms_next_rung_anchored_to_the_nudge_it_just_sent():
    db = _drain_db(_job(step_index=0), _ok_lead(), inserted_id="msg-nudge")
    await _run_drain(db)
    armed = [r for r in db._state["inserted"] if r.get("step_index") == 1]
    assert len(armed) == 1
    # Critical: the next rung's race check must compare against the nudge we
    # just sent, not the original AI reply — otherwise it cancels immediately.
    assert armed[0]["anchor_message_id"] == "msg-nudge"


@pytest.mark.asyncio
async def test_drain_does_not_arm_past_the_last_rung():
    db = _drain_db(_job(step_index=1), _ok_lead())
    await _run_drain(db)
    assert [r for r in db._state["inserted"] if r.get("step_index") == 2] == []


@pytest.mark.asyncio
async def test_drain_marks_failed_when_send_returns_no_id():
    from app.services import silence_nudge as sn
    db = _drain_db(_job(), _ok_lead())
    def setting(key, fallback=None, tenant_id=None):
        return {"silence_nudge_enabled": "true", "ai_auto_reply_enabled": "true",
                "silence_nudge_daily_cap": "1", "silence_nudge_delays": "5"}.get(key, fallback)
    with patch.object(sn, "get_setting", side_effect=setting), \
         patch("app.services.automation_guards.get_setting", side_effect=setting), \
         patch.object(sn, "get_supabase", return_value=db), \
         patch.object(sn, "check_quota", return_value=True), \
         patch.object(sn, "meter"), \
         patch.object(sn, "generate_silence_nudge", new=AsyncMock(return_value="hi")), \
         patch.object(sn, "send_whatsapp", new=AsyncMock(return_value=None)):
        count = await sn.drain_due_nudges()
    assert count == 0
    assert "failed" in _statuses(db)
```

Add these two quiet-hours drain tests as well:

```python
@pytest.mark.asyncio
async def test_first_rung_ignores_quiet_hours():
    from app.services import silence_nudge as sn
    db = _drain_db(_job(step_index=0), _ok_lead())
    # 02:00 IST — deep inside the default 21:00-09:00 quiet window
    with patch.object(sn, "_now", return_value=datetime(2026, 8, 10, 20, 30, tzinfo=timezone.utc)):
        count, wa = await _run_drain(db)
    assert count == 1
    wa.assert_awaited_once()


@pytest.mark.asyncio
async def test_later_rung_defers_out_of_quiet_hours_and_stays_pending():
    from app.services import silence_nudge as sn
    db = _drain_db(_job(step_index=1), _ok_lead())
    with patch.object(sn, "_now", return_value=datetime(2026, 8, 10, 20, 30, tzinfo=timezone.utc)):
        count, wa = await _run_drain(db)
    assert count == 0
    wa.assert_not_awaited()
    deferred = [u for u in db._state["updated"] if "fire_at" in u]
    assert len(deferred) == 1
    assert "status" not in deferred[0]  # still pending
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: FAIL — `AttributeError: module 'app.services.silence_nudge' has no attribute 'drain_due_nudges'`

- [ ] **Step 3: Implement the drain loop**

Append to `backend/app/services/silence_nudge.py`:

```python
from app.db.supabase import get_supabase
from app.services.ai_reply import generate_silence_nudge, send_whatsapp
from app.services.entitlements import check_quota, meter

_LEAD_COLUMNS = (
    "id,name,phone,ai_enabled,converted_at,blocked_at,opted_out,"
    "whatsapp_undeliverable,needs_human_attention,last_inbound_at"
)


def _mark(db, job: dict, status: str, reason: str | None, preview: str | None = None) -> None:
    patch_row: dict = {"status": status, "skip_reason": reason}
    if status == "sent":
        patch_row["sent_at"] = _now().isoformat()
        patch_row["message_preview"] = preview
    db.table("silence_nudge_jobs").update(patch_row).eq("id", job["id"]).execute()


def _fetch_lead(db, job: dict) -> dict | None:
    rows = (
        db.table("leads").select(_LEAD_COLUMNS)
        .eq("id", job["lead_id"]).limit(1).execute().data
    ) or []
    return rows[0] if rows else None


def _thread_unchanged(db, job: dict) -> bool:
    """True only if our anchor is still the newest message in the thread."""
    rows = (
        db.table("messages").select("id")
        .eq("lead_id", job["lead_id"])
        .order("created_at", desc=True).limit(1).execute().data
    ) or []
    return bool(rows) and rows[0]["id"] == job["anchor_message_id"]


def _window_open(lead: dict) -> bool:
    raw = lead.get("last_inbound_at")
    if not raw:
        return False
    try:
        last_inbound = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (_now() - last_inbound) <= timedelta(hours=24)


async def _process_job(db, job: dict) -> bool:
    tenant_id = job["tenant_id"]
    lead = _fetch_lead(db, job)
    if not lead:
        _mark(db, job, "skipped", "lead missing")
        return False

    action, reason = _evaluate_gates(db, job, lead)
    if action == HOLD:
        return False  # stays pending; resumes when the switch flips back
    if action == SKIP:
        _mark(db, job, "skipped", reason)
        return False

    # Gate 8: the first rung always fires — the lead messaged minutes ago and
    # is demonstrably awake. Later rungs defer out of the quiet window.
    now = _now()
    if job["step_index"] > 0:
        quiet_start, quiet_end = _quiet_window(tenant_id)
        if _in_quiet_window((now + IST_OFFSET).time(), quiet_start, quiet_end):
            db.table("silence_nudge_jobs").update(
                {"fire_at": _next_window_end(now, quiet_end).isoformat()}
            ).eq("id", job["id"]).execute()
            return False

    # Gate 9: the race. Second line of defence behind cancel_pending().
    if not _thread_unchanged(db, job):
        _mark(db, job, "cancelled", "lead replied")
        return False

    # Gate 10
    if not _window_open(lead):
        _mark(db, job, "skipped", "24h window closed")
        return False

    if not check_quota(db, tenant_id, "ai_reply"):
        _mark(db, job, "skipped", "ai_reply quota exhausted")
        return False

    text = await generate_silence_nudge(job["lead_id"], db=db)
    sid = await send_whatsapp(lead["phone"], text, tenant_id=tenant_id)
    if not sid:
        _mark(db, job, "failed", "channel send returned no id")
        return False

    res = db.table("messages").insert({
        "lead_id": job["lead_id"],
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": text,
        "is_ai_generated": True,
        "meta_message_id": sid,
        "reply_source": "silence_nudge",
    }).execute()
    meter(db, tenant_id, "ai_reply")
    _mark(db, job, "sent", None, preview=text)

    # The next rung anchors on the nudge we just sent — it is now the newest
    # message, so anchoring on the original reply would self-cancel instantly.
    new_anchor = ((res.data or [{}])[0] or {}).get("id") or job["anchor_message_id"]
    arm(db, tenant_id, job["lead_id"], new_anchor, step_index=job["step_index"] + 1)
    return True


async def drain_due_nudges(limit: int = 100) -> int:
    """Send every due silence nudge. Returns the number actually sent."""
    db = get_supabase()
    jobs = (
        db.table("silence_nudge_jobs").select("*")
        .eq("status", "pending")
        .lte("fire_at", _now().isoformat())
        .order("fire_at").limit(limit).execute().data
    ) or []

    sent = 0
    for job in jobs:
        try:
            if await _process_job(db, job):
                sent += 1
        except Exception:
            logger.exception("Silence nudge job %s failed", job.get("id"))
            try:
                _mark(db, job, "failed", "unhandled error")
            except Exception:
                logger.exception("Could not mark silence nudge job %s failed", job.get("id"))
    return sent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_silence_nudge.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Check for a circular import**

`silence_nudge` imports from `ai_reply`, and Task 7 makes `ai_reply` import from `silence_nudge`. Verify the module still loads standalone:

Run: `cd backend && python -c "import app.services.silence_nudge; print('ok')"`
Expected: prints `ok`. If it raises `ImportError`, move the `ai_reply` imports inside `_process_job` as function-local imports (the codebase already does this in several places, e.g. `main.py::_process_reengagement_rules`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/silence_nudge.py backend/tests/test_silence_nudge.py
git commit -m "feat: drain due silence nudges with race re-check and ladder"
```

---

### Task 7: Wire into the message pipeline

**Files:**
- Modify: `backend/app/services/ai_reply.py:1717` (arm after the outbound insert)
- Modify: `backend/app/routes/webhook.py:268-280` (audio inbound) and `backend/app/routes/webhook.py:771-785` (text inbound)
- Create: `backend/tests/test_silence_nudge_wiring.py`

**Interfaces:**
- Consumes: `silence_nudge.maybe_arm_after_ai_reply`, `silence_nudge.cancel_pending`
- Produces: no new symbols — this task connects existing ones

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_silence_nudge_wiring.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def test_arm_failure_never_breaks_the_reply():
    """The single most important property: a broken nudge must not stop a
    customer receiving their answer."""
    from app.services import silence_nudge as sn
    db = MagicMock()
    db.table.side_effect = RuntimeError("supabase down")
    with pytest.raises(RuntimeError):
        sn.cancel_pending(db, "lead-1")
    # ai_reply must therefore wrap the call — asserted in the source check below


def test_ai_reply_wraps_the_arm_call_in_try_except():
    """Source-level guard: the arm hook sits inside a try/except that logs."""
    from pathlib import Path
    import app.services.ai_reply as ar
    src = Path(ar.__file__).read_text(encoding="utf-8")
    idx = src.index("maybe_arm_after_ai_reply")
    window = src[idx - 400:idx + 400]
    assert "try:" in window
    assert "except Exception" in window
    assert "logger.exception" in window


def test_outbound_insert_result_is_captured():
    """maybe_arm_after_ai_reply needs the inserted row id as its anchor, so the
    Step 4 insert must no longer discard its result."""
    from pathlib import Path
    import app.services.ai_reply as ar
    src = Path(ar.__file__).read_text(encoding="utf-8")
    assert "_outbound_res = db.table(\"messages\").insert(outbound_row).execute()" in src


@pytest.mark.parametrize("site", ["audio", "text"])
def test_webhook_cancels_pending_nudges_on_inbound(site):
    from pathlib import Path
    import app.routes.webhook as wh
    src = Path(wh.__file__).read_text(encoding="utf-8")
    assert src.count("cancel_pending") >= 2, "both inbound insert sites must cancel"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_silence_nudge_wiring.py -v`
Expected: FAIL on `test_ai_reply_wraps_the_arm_call_in_try_except` (substring not found) and the webhook test.

- [ ] **Step 3: Add the arm hook**

In `backend/app/services/ai_reply.py`, change the Step 4 outbound insert (~L1717) from:

```python
    db.table("messages").insert(outbound_row).execute()
```

to:

```python
    _outbound_res = db.table("messages").insert(outbound_row).execute()

    # Arm the silence nudge. Best-effort by design: the customer has already
    # received their reply, and a failure here must never turn a delivered
    # answer into an exception. Same pattern as the intake/escalation blocks.
    try:
        from app.services.silence_nudge import maybe_arm_after_ai_reply
        maybe_arm_after_ai_reply(
            db,
            tenant_id=tenant_id,
            lead_id=str(lead_id),
            channel=channel,
            is_ai=is_ai,
            sid=sid,
            reply_source=reply_source,
            inserted=((_outbound_res.data or [None])[0]),
        )
    except Exception:
        logger.exception("Silence nudge arm failed for lead %s — reply already sent", lead_id)
```

- [ ] **Step 4: Add the cancel hooks**

In `backend/app/routes/webhook.py`, after **each** of the two inbound `messages` inserts (the audio site at ~L268-278 and the text site at ~L771-781), add:

```python
                    try:
                        from app.services.silence_nudge import cancel_pending
                        cancel_pending(db, lead_id)
                    except Exception:
                        logger.exception("Silence nudge cancel failed for lead %s", lead_id)
```

Match the surrounding indentation at each site — the audio site is inside a shallower block than the text site.

> Correctness does not depend on these hooks. `_thread_unchanged()` at fire time already prevents a wrong send; cancelling just keeps the queue clean and avoids a pointless LLM call.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_silence_nudge_wiring.py -v`
Expected: PASS, all tests.

- [ ] **Step 6: Run the whole backend suite**

Run: `cd backend && pytest`
Expected: PASS. Pay particular attention to `test_astro_reply_hardening.py`, `test_expert_handoff.py`, and `test_reengagement_service.py` — they exercise the same webhook and reply paths.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_reply.py backend/app/routes/webhook.py backend/tests/test_silence_nudge_wiring.py
git commit -m "feat: arm silence nudges on AI reply, cancel them on inbound"
```

---

### Task 8: Register the scheduler job

**Files:**
- Modify: `backend/app/main.py` (job function near `_process_reengagement_rules` ~L174, registration ~L358, log line ~L435)

**Interfaces:**
- Consumes: `silence_nudge.drain_due_nudges`
- Produces: APScheduler job id `silence-nudge`, 1-minute interval

- [ ] **Step 1: Add the job function**

In `backend/app/main.py`, directly after `_process_reengagement_rules`:

```python
async def _process_silence_nudges() -> None:
    """APScheduler job: send due silence nudges."""
    try:
        from app.services.silence_nudge import drain_due_nudges
        count = await drain_due_nudges()
        if count:
            logger.info(f"Silence nudge scheduler: sent {count} nudge(s)")
    except Exception as e:
        logger.error(f"Silence nudge scheduler error: {e}")
```

- [ ] **Step 2: Register it**

After the `reengagement-rules` registration (~L358-364):

```python
    _scheduler.add_job(
        _process_silence_nudges,
        trigger="interval",
        minutes=1,
        id="silence-nudge",
        replace_existing=True,
    )
```

- [ ] **Step 3: Update the startup log line**

Change the log at ~L435 to append `+ silence-nudge(1m)`:

```python
    logger.info("Schedulers started: broadcasts(1m) + token-health(24h) + reengagement(1m) + assignment-sweep(2m) + recycle-contacts(30m) + callback-notify(1m) + quality-sync(24h) + daily-digest(cron 13:00 UTC) + pending-whatsapp-alerts(1m) + astro-push-reconcile(5m) + intake-staleness-sweep(5m) + silence-nudge(1m)")
```

- [ ] **Step 4: Verify the app boots and the job is registered**

Run: `cd backend && python -c "import app.main; print('ok')"`
Expected: prints `ok` with no import error.

Then start the server and confirm the startup log lists `silence-nudge(1m)`:

Run: `cd backend && uvicorn app.main:app --port 8899` — check the log line, then stop it.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register the silence-nudge scheduler job"
```

---

### Task 9: Automations settings panel

**Files:**
- Modify: `frontend/app/dashboard/settings/page.tsx` (constants near `AI_AUTO_REPLY_TOGGLE` ~L67; panel inside the `activeTab === "automations"` block ~L662)

**Interfaces:**
- Consumes: existing `drafts` / `setDrafts` / `saveStates` / `handleSave(section, keys)` / `settingFor(key)?.display_value` / `canManageSettings`
- Produces: no new exports — a new card in the Automations tab writing five `app_settings` keys

- [ ] **Step 1: Add the key constants**

Near `AI_AUTO_REPLY_TOGGLE` (~L67) in `frontend/app/dashboard/settings/page.tsx`:

```tsx
const SILENCE_NUDGE_KEYS = {
  enabled: "silence_nudge_enabled",
  delays: "silence_nudge_delays",
  cap: "silence_nudge_daily_cap",
  quietStart: "silence_nudge_quiet_start",
  quietEnd: "silence_nudge_quiet_end",
} as const;

const SILENCE_NUDGE_DEFAULTS: Record<string, string> = {
  [SILENCE_NUDGE_KEYS.enabled]: "false",
  [SILENCE_NUDGE_KEYS.delays]: "5",
  [SILENCE_NUDGE_KEYS.cap]: "1",
  [SILENCE_NUDGE_KEYS.quietStart]: "21:00",
  [SILENCE_NUDGE_KEYS.quietEnd]: "09:00",
};
```

- [ ] **Step 2: Add the derived state**

Beside `aiAutomationDirty` (~L336):

```tsx
  const silenceValue = (key: string) =>
    drafts[key] ?? settingFor(key)?.display_value ?? SILENCE_NUDGE_DEFAULTS[key];
  const silenceEnabled = silenceValue(SILENCE_NUDGE_KEYS.enabled) === "true";
  const silenceDirty = Object.values(SILENCE_NUDGE_KEYS).some((key) => {
    const draft = drafts[key];
    if (draft === undefined) return false;
    return draft !== (settingFor(key)?.display_value ?? SILENCE_NUDGE_DEFAULTS[key]);
  });
  const silenceDelaysValid = /^\s*\d+\s*(,\s*\d+\s*){0,2}$/.test(
    silenceValue(SILENCE_NUDGE_KEYS.delays) ?? ""
  ) && silenceValue(SILENCE_NUDGE_KEYS.delays)!
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .every((n, i, arr) => n >= 1 && n <= 1440 && (i === 0 || n > arr[i - 1]));
```

- [ ] **Step 3: Add the panel**

Inside the `activeTab === "automations"` block, after the existing AI Auto-Reply card's closing `</div>`:

```tsx
              <div className="card rounded-3xl animate-slide-up">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#ede9fe]">
                      <Sparkles size={18} className="text-primary" />
                    </div>
                    <div className="min-w-0">
                      <h2 className="font-display text-base font-bold text-ink">
                        Auto follow-up when a lead goes quiet
                      </h2>
                      <p className="mt-1 max-w-2xl font-body text-sm leading-relaxed text-ink-muted">
                        After the AI answers, if the lead stays silent, send one short message about
                        what they were discussing. Never sent while your team has taken over the
                        chat, or during a paid consultation.
                      </p>
                    </div>
                  </div>
                  <div className="relative inline-flex p-0.5 rounded-full bg-border-subtle/80 border border-border/40 select-none shrink-0">
                    {(["Off", "On"] as const).map((label) => {
                      const value = label === "On" ? "true" : "false";
                      const active = silenceEnabled === (value === "true");
                      return (
                        <button
                          key={label}
                          type="button"
                          disabled={!canManageSettings}
                          onClick={() =>
                            setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.enabled]: value }))
                          }
                          className={`relative z-10 px-3 py-0.5 text-xs font-label font-bold rounded-full transition-all duration-300 ${
                            active
                              ? label === "On"
                                ? "bg-gradient-to-r from-primary to-violet-500 text-white shadow-[0_2px_8px_rgba(91,33,182,0.2)]"
                                : "bg-white text-ink shadow-[0_2px_8px_rgba(28,25,23,0.06)]"
                              : "text-ink-muted hover:text-ink"
                          } disabled:cursor-not-allowed disabled:opacity-60`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {silenceEnabled && (
                  <div className="mt-6 grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="font-label text-xs uppercase tracking-widest text-ink-muted">
                        Wait time (minutes)
                      </span>
                      <input
                        type="text"
                        inputMode="numeric"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.delays) ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: e.target.value }))
                        }
                        className="mt-1.5 w-full rounded-xl border border-border-subtle bg-white px-3 py-2 font-body text-sm text-ink disabled:opacity-60"
                      />
                      <span className="mt-1 block font-body text-[11px] text-ink-muted">
                        {silenceDelaysValid
                          ? "5 sends one message after 5 minutes. 5,60 adds a second an hour later."
                          : "Up to 3 whole numbers, 1–1440, increasing. e.g. 5 or 5,60"}
                      </span>
                    </label>

                    <label className="block">
                      <span className="font-label text-xs uppercase tracking-widest text-ink-muted">
                        Daily limit per lead
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.cap) ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.cap]: e.target.value }))
                        }
                        className="mt-1.5 w-full rounded-xl border border-border-subtle bg-white px-3 py-2 font-body text-sm text-ink disabled:opacity-60"
                      />
                      <span className="mt-1 block font-body text-[11px] text-ink-muted">
                        Most follow-ups one lead can get in 24 hours.
                      </span>
                    </label>

                    <label className="block">
                      <span className="font-label text-xs uppercase tracking-widest text-ink-muted">
                        Quiet hours start (IST)
                      </span>
                      <input
                        type="time"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.quietStart) ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.quietStart]: e.target.value }))
                        }
                        className="mt-1.5 w-full rounded-xl border border-border-subtle bg-white px-3 py-2 font-body text-sm text-ink disabled:opacity-60"
                      />
                    </label>

                    <label className="block">
                      <span className="font-label text-xs uppercase tracking-widest text-ink-muted">
                        Quiet hours end (IST)
                      </span>
                      <input
                        type="time"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.quietEnd) ?? ""}
                        onChange={(e) =>
                          setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.quietEnd]: e.target.value }))
                        }
                        className="mt-1.5 w-full rounded-xl border border-border-subtle bg-white px-3 py-2 font-body text-sm text-ink disabled:opacity-60"
                      />
                      <span className="mt-1 block font-body text-[11px] text-ink-muted">
                        The first follow-up always sends — quiet hours only delay later ones.
                      </span>
                    </label>
                  </div>
                )}

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-5">
                  <div className="min-h-[20px]">
                    {(saveStates.automations_silence ?? "idle") === "saved" && (
                      <span className="inline-flex items-center gap-1.5 font-body text-sm font-medium text-emerald-600">
                        <CheckCircle2 size={15} /> Saved successfully
                      </span>
                    )}
                    {silenceDirty && (saveStates.automations_silence ?? "idle") !== "saved" && (
                      <span className="font-body text-[11px] font-medium text-amber-600">
                        Unsaved changes
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() =>
                      handleSave("automations_silence", Object.values(SILENCE_NUDGE_KEYS))
                    }
                    disabled={
                      !canManageSettings ||
                      !silenceDirty ||
                      !silenceDelaysValid ||
                      (saveStates.automations_silence ?? "idle") === "saving" ||
                      (saveStates.automations_silence ?? "idle") === "saved"
                    }
                    className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 font-label text-sm font-semibold transition-all ${
                      canManageSettings && silenceDirty && silenceDelaysValid
                        ? "bg-primary text-white hover:bg-primary/90"
                        : "bg-surface-subtle text-ink-muted cursor-default"
                    }`}
                  >
                    {(saveStates.automations_silence ?? "idle") === "saving" ? (
                      <><Loader2 size={14} className="animate-spin" />Saving...</>
                    ) : (
                      <>Save</>
                    )}
                  </button>
                </div>
              </div>
```

- [ ] **Step 4: Verify — BOTH commands, lint is what CI runs**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

Run: `cd frontend && npm run lint`
Expected: no errors. `tsc` alone passes code that fails CI on unused imports and `any`.

- [ ] **Step 5: Verify in the browser**

Start the frontend, open `/dashboard/settings?tab=automations`, and confirm:
- The new card renders below AI Auto-Reply, defaulting to **Off**
- The four inputs appear only when toggled On
- Entering `60,5` disables the Save button and shows the format hint
- Entering `5,60` re-enables Save
- Saving, reloading, and re-opening the tab shows the persisted values

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/settings/page.tsx
git commit -m "feat(ui): silence nudge controls in the Automations tab"
```

---

## Post-implementation

- [ ] Run the full backend suite one final time: `cd backend && pytest`
- [ ] Run `cd frontend && npm run lint && npm run typecheck`
- [ ] Leave `silence_nudge_enabled` unset (defaults `"false"`) for every tenant. Enable for one pilot tenant only, with `delays="5"` and `daily_cap="1"`.
- [ ] After a week, review the pilot:

```sql
SELECT status, skip_reason, count(*)
FROM silence_nudge_jobs
WHERE created_at > now() - interval '7 days'
GROUP BY status, skip_reason ORDER BY count(*) DESC;

SELECT message_preview, sent_at FROM silence_nudge_jobs
WHERE status = 'sent' ORDER BY sent_at DESC LIMIT 20;
```

A high `cancelled` count is **healthy** — it means leads are replying inside the window and timers are dying as intended. Read the `message_preview` values before widening: they are what your customers actually received.

- [ ] Route the outcome into the second brain via the `second-brain-close` skill — in particular the `_ACTIVE_INTAKE_STATUSES` values confirmed in Task 4 Step 5, and whether the guard extraction in Task 2 held or fell back to duplication.
