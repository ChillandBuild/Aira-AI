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


# Drain tests pin the clock so quiet-hours behaviour can never depend on when
# the suite happens to run. 06:30 UTC == 12:00 IST — squarely outside the
# default 21:00-09:00 quiet window.
_PINNED_NOW = datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc)
# 20:30 UTC == 02:00 IST — deep inside the quiet window.
_PINNED_QUIET_NOW = datetime(2026, 8, 10, 20, 30, tzinfo=timezone.utc)


def _ok_lead(**over):
    base = {"id": "lead-1", "name": "Asha", "phone": "919999999999",
            "ai_enabled": True, "converted_at": None, "blocked_at": None,
            "opted_out": False, "whatsapp_undeliverable": False,
            "needs_human_attention": False,
            "last_inbound_at": _PINNED_NOW.isoformat()}
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
    from app.services import automation_guards as guards

    def setting(key, fallback=None, tenant_id=None):
        return {"silence_nudge_enabled": enabled,
                "ai_auto_reply_enabled": master,
                "silence_nudge_daily_cap": cap}.get(key, fallback)

    with patch.object(sn, "get_setting", side_effect=setting), \
         patch.object(guards, "get_setting", side_effect=setting):
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


def test_open_handover_query_uses_pending_status():
    """An open handover carries status='pending', not 'open' — chat_handovers
    defaults to 'pending' (migration 043) and resolve flips it to 'resolved'.
    Querying 'open' would match nothing and silently disable this gate."""
    from app.services import silence_nudge as sn
    calls = []
    t = MagicMock()
    t.select.return_value = t

    def _eq(field, value):
        calls.append((field, value))
        return t

    t.eq.side_effect = _eq
    t.limit.return_value.execute.return_value.data = []
    db = MagicMock()
    db.table.return_value = t

    sn._has_open_handover(db, "t1", "lead-1")
    assert ("status", "pending") in calls


def test_gate_skips_during_active_intake():
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=_ok_lead(), intake=True), _ok_lead())
    assert action == SKIP and "intake" in reason


def test_active_intake_statuses_exclude_only_terminal_ones():
    """Guards against drift from the intake_sessions_status_check constraint
    set in migration 176. Terminal = resolved/cancelled; everything else is live."""
    from app.services.silence_nudge import _ACTIVE_INTAKE_STATUSES
    assert set(_ACTIVE_INTAKE_STATUSES) == {
        "offer_pending", "awaiting_package_choice", "collecting",
        "awaiting_confirmation", "awaiting_payment", "paid",
    }


def test_gate_skips_when_daily_cap_reached():
    from app.services.silence_nudge import SKIP
    action, reason = _gate(_db(lead=_ok_lead(), sent_today=1), _ok_lead(), cap="1")
    assert action == SKIP and "cap" in reason


def test_gate_allows_second_nudge_when_cap_is_two():
    from app.services.silence_nudge import SEND
    action, _ = _gate(_db(lead=_ok_lead(), sent_today=1), _ok_lead(), cap="2")
    assert action == SEND


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


async def _run_drain(db, *, enabled="true", master="true", cap="1",
                     nudge="Still there?", now=_PINNED_NOW, send_sid="sid-1"):
    """Helper, not a test — awaited by the drain tests below."""
    from app.services import silence_nudge as sn
    from app.services import automation_guards as guards

    def setting(key, fallback=None, tenant_id=None):
        return {"silence_nudge_enabled": enabled, "ai_auto_reply_enabled": master,
                "silence_nudge_daily_cap": cap, "silence_nudge_delays": "5,60",
                "silence_nudge_quiet_start": "21:00",
                "silence_nudge_quiet_end": "09:00"}.get(key, fallback)

    with patch.object(sn, "get_setting", side_effect=setting), \
         patch.object(guards, "get_setting", side_effect=setting), \
         patch.object(sn, "_now", return_value=now), \
         patch.object(sn, "get_supabase", return_value=db), \
         patch.object(sn, "check_quota", return_value=True), \
         patch.object(sn, "meter"), \
         patch.object(sn, "generate_silence_nudge", new=AsyncMock(return_value=nudge)), \
         patch.object(sn, "send_whatsapp", new=AsyncMock(return_value=send_sid)) as wa:
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
async def test_drain_skips_during_active_intake():
    db = _drain_db(_job(), _ok_lead(), intake=True)
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
    stale = (_PINNED_NOW - timedelta(hours=30)).isoformat()
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
    db = _drain_db(_job(), _ok_lead())
    count, wa = await _run_drain(db, send_sid=None)
    assert count == 0
    assert "failed" in _statuses(db)


@pytest.mark.asyncio
async def test_first_rung_ignores_quiet_hours():
    db = _drain_db(_job(step_index=0), _ok_lead())
    count, wa = await _run_drain(db, now=_PINNED_QUIET_NOW)
    assert count == 1
    wa.assert_awaited_once()


@pytest.mark.asyncio
async def test_later_rung_defers_out_of_quiet_hours_and_stays_pending():
    db = _drain_db(_job(step_index=1), _ok_lead())
    count, wa = await _run_drain(db, now=_PINNED_QUIET_NOW)
    assert count == 0
    wa.assert_not_awaited()
    deferred = [u for u in db._state["updated"] if "fire_at" in u]
    assert len(deferred) == 1
    assert "status" not in deferred[0]  # still pending
