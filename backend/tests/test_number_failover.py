"""Number health + failover (2026-10-16).

Rules agreed with the user:
- Everything comes from Meta: a number may only send or take over when Meta
  reports status CONNECTED; an Unverified (PENDING) number never does.
- New numbers warm up for 14 days from the day Meta connects them; a
  warming standby may still take over, with its broadcasts capped.
- A Red number rests: no broadcasts, still answers chats. It recovers after
  7 days once Meta reports it Green, as a standby (it doesn't retake primary).
- No usable standby -> broadcasts pause; the rest of a broadcast waits for
  tomorrow instead of going out from a Red number.
- The sync, not only Meta's webhook, starts the switch.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import number_health as nh

NOW = datetime.now(timezone.utc)


def _ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def _num(id_, **kw):
    row = {
        "id": id_, "tenant_id": "t1", "number": f"+91{id_}", "role": "standby",
        "status": "active", "quality_rating": "green", "messaging_tier": 2000,
        "daily_send_count": 0, "paused_outbound": False, "meta_status": "CONNECTED",
        "meta_code_verification": "VERIFIED", "warm_up_started_at": _ago(30),
        "warm_up_day": 14, "rested_since": None, "meta_phone_number_id": f"meta-{id_}",
    }
    row.update(kw)
    return row


# ── Meta is the only source ──────────────────────────────────────────────

def test_unknown_quality_and_missing_limit_are_not_guessed():
    snap = nh.meta_snapshot({"quality_rating": "UNKNOWN", "status": "PENDING", "code_verification_status": "NOT_VERIFIED"})
    assert snap["quality_rating"] is None
    assert "messaging_tier" not in snap
    assert snap["meta_status"] == "PENDING"
    assert snap["meta_code_verification"] == "NOT_VERIFIED"


def test_number_without_a_meta_limit_cannot_broadcast():
    row = _num("a", messaging_tier=None)
    assert nh.broadcast_cap(row, NOW) is None
    assert not nh.can_broadcast(row, NOW, {"a"})


# ── Badges ───────────────────────────────────────────────────────────────

def test_unverified_number_shows_meta_pending_not_active():
    row = _num("a", meta_status="PENDING", meta_code_verification="NOT_VERIFIED", warm_up_started_at=None, status="warming")
    assert nh.health(row, NOW)["state"] == "meta_pending"


def test_connected_number_mid_warm_up_shows_its_day():
    h = nh.health(_num("a", status="warming", warm_up_started_at=_ago(3)), NOW)
    assert h["state"] == "warming" and h["warm_up_day"] == 3 and h["broadcast_cap"] == 75


def test_red_number_shows_resting_with_rest_day():
    h = nh.health(_num("a", status="restricted", quality_rating="red", rested_since=_ago(2)), NOW)
    assert h["state"] == "resting" and h["rest_day"] == 2


# ── Warm-up ──────────────────────────────────────────────────────────────

def test_warm_up_starts_the_day_meta_connects_the_number():
    pending = _num("a", meta_status="PENDING", warm_up_started_at=None, status="warming", warm_up_day=0)
    assert "warm_up_started_at" not in nh.lifecycle_updates(pending, NOW, unlocked=True)

    connected = {**pending, "meta_status": "CONNECTED"}
    updates = nh.lifecycle_updates(connected, NOW, unlocked=True)
    assert updates["warm_up_started_at"] == NOW.isoformat()
    assert updates.get("status", "warming") == "warming"


def test_warm_up_completes_after_14_days_when_unlocked():
    row = _num("a", status="warming", warm_up_started_at=_ago(14), warm_up_day=13)
    assert nh.lifecycle_updates(row, NOW, unlocked=True)["status"] == "active"
    assert "status" not in nh.lifecycle_updates(row, NOW, unlocked=False)


def test_warming_number_broadcasts_within_the_warm_up_cap():
    row = _num("a", status="warming", warm_up_started_at=_ago(1), daily_send_count=0)
    assert nh.can_broadcast(row, NOW, {"a"})
    assert nh.broadcast_cap(row, NOW) == 50


# ── Who may take over ────────────────────────────────────────────────────

def test_unverified_standby_is_never_a_candidate():
    rows = [_num("p", role="primary", status="restricted", quality_rating="red"),
            _num("s", meta_status="PENDING", status="warming", warm_up_started_at=None)]
    assert nh.standby_candidates(rows, "p", {"p", "s"}) == []


def test_warming_connected_standby_is_a_candidate_and_furthest_warmed_wins():
    rows = [_num("p", role="primary", status="restricted", quality_rating="red"),
            _num("s1", status="warming", warm_up_started_at=_ago(2)),
            _num("s2", status="warming", warm_up_started_at=_ago(9))]
    assert [r["id"] for r in nh.standby_candidates(rows, "p", {"p", "s1", "s2"})] == ["s2", "s1"]


def test_paused_red_or_locked_standbys_are_skipped():
    rows = [_num("paused", paused_outbound=True), _num("red", quality_rating="red"), _num("locked")]
    assert nh.standby_candidates(rows, None, {"paused", "red"}) == []


# ── Recovery ─────────────────────────────────────────────────────────────

def test_recovery_needs_seven_days_and_green():
    assert not nh.recovered(_num("a", status="restricted", quality_rating="green", rested_since=_ago(6)), NOW)
    assert not nh.recovered(_num("a", status="restricted", quality_rating="yellow", rested_since=_ago(8)), NOW)
    ok = _num("a", status="restricted", quality_rating="green", rested_since=_ago(7))
    assert nh.recovered(ok, NOW)
    assert nh.lifecycle_updates(ok, NOW, unlocked=True) == {"rested_since": None, "status": "active"}


# ── Failover against a fake DB ───────────────────────────────────────────

class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.f, self.nf = db, table, "select", None, {}, {}

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload, **_k):
        self.op, self.payload = "upsert", payload
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def neq(self, col, val):
        self.nf[col] = val
        return self

    def limit(self, _n):
        return self

    def _match(self, r):
        return all(r.get(k) == v for k, v in self.f.items()) and all(r.get(k) != v for k, v in self.nf.items())

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "select":
            return _Res([dict(r) for r in rows if self._match(r)])
        if self.op == "update":
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(self.payload)
            return _Res(hit)
        rows.append(dict(self.payload))
        return _Res([self.payload])


class _DB:
    def __init__(self, numbers):
        self.tables = {"phone_numbers": [dict(n) for n in numbers], "incidents": [], "app_settings": []}

    def table(self, name):
        return _Q(self, name)

    def row(self, id_):
        return next(r for r in self.tables["phone_numbers"] if r["id"] == id_)

    def incident_types(self):
        return [i["type"] for i in self.tables["incidents"]]


def _patch_db(db, unlocked):
    return [
        patch("app.services.failover.get_supabase", return_value=db),
        patch("app.services.failover.get_unlocked_number_ids", return_value=unlocked),
        patch("app.config_dynamic.invalidate_cache"),
    ]


async def _run_red(db, unlocked, number_id):
    from app.services.failover import handle_quality_red
    ps = _patch_db(db, unlocked)
    for p in ps:
        p.start()
    try:
        await handle_quality_red(number_id, source="test")
    finally:
        for p in ps:
            p.stop()


@pytest.mark.asyncio
async def test_red_primary_hands_over_to_a_warming_connected_standby():
    db = _DB([_num("p", role="primary"), _num("s", status="warming", warm_up_started_at=_ago(1))])
    await _run_red(db, {"p", "s"}, "p")

    assert db.row("s")["role"] == "primary"
    old = db.row("p")
    assert old["role"] == "standby" and old["status"] == "restricted" and old["rested_since"]
    assert db.tables["app_settings"][0]["value"] == "meta-s"
    assert "failover" in db.incident_types() and "standby_promoted" in db.incident_types()


@pytest.mark.asyncio
async def test_red_primary_with_only_an_unverified_standby_stays_primary_and_rests():
    db = _DB([_num("p", role="primary"),
              _num("s", meta_status="PENDING", status="warming", warm_up_started_at=None)])
    await _run_red(db, {"p", "s"}, "p")

    assert db.row("p")["role"] == "primary" and db.row("p")["status"] == "restricted"
    assert db.row("s")["role"] == "standby"
    no_standby = [i for i in db.tables["incidents"] if i["detail"].get("message") == "no_standby_available"]
    assert len(no_standby) == 1


@pytest.mark.asyncio
async def test_a_second_red_report_does_not_restart_the_rest_clock():
    db = _DB([_num("p", role="primary", status="restricted", quality_rating="red", rested_since=_ago(3))])
    await _run_red(db, {"p"}, "p")
    assert db.row("p")["rested_since"] == _ago(3)


@pytest.mark.asyncio
async def test_standby_that_becomes_ready_later_takes_over_on_the_next_sync():
    from app.services.failover import ensure_healthy_primary
    db = _DB([_num("p", role="primary", status="restricted", quality_rating="red", rested_since=_ago(1)),
              _num("s", status="warming", warm_up_started_at=_ago(0))])
    ps = _patch_db(db, {"p", "s"})
    for p in ps:
        p.start()
    try:
        promoted = await ensure_healthy_primary("t1")
    finally:
        for p in ps:
            p.stop()
    assert promoted["id"] == "s" and db.row("s")["role"] == "primary"


# ── Sync starts the switch too ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_seeing_red_starts_the_failover():
    from app.services.number_sync import apply_meta_snapshot
    db = _DB([_num("p", role="primary")])
    red = AsyncMock()
    with patch("app.services.number_sync.handle_quality_red", red):
        await apply_meta_snapshot(db, "t1", db.row("p"), {"quality_rating": "RED", "status": "CONNECTED"}, {"p"}, "test")
    red.assert_awaited_once_with("p", source="test")


@pytest.mark.asyncio
async def test_sync_records_meta_pending_and_no_rating_for_an_unverified_number():
    from app.services.number_sync import apply_meta_snapshot
    db = _DB([_num("s", status="warming", warm_up_started_at=None, warm_up_day=0, meta_status=None)])
    db.tables["phone_number_quality_history"] = []
    await apply_meta_snapshot(db, "t1", db.row("s"), {
        "quality_rating": "UNKNOWN", "status": "PENDING", "code_verification_status": "NOT_VERIFIED",
    }, {"s"}, "test")
    row = db.row("s")
    assert row["quality_rating"] is None
    assert row["meta_status"] == "PENDING"
    assert row["status"] == "warming" and row["warm_up_started_at"] is None


# ── Picking the sender ───────────────────────────────────────────────────

def _count_in(db):
    async def inc(number_id, delta=1):
        db.row(number_id)["daily_send_count"] += delta
    return inc


def _picker(rows, unlocked):
    from app.services.outbound_router import SenderPicker
    db = _DB(rows)
    patches = [
        patch("app.services.outbound_router.get_supabase", return_value=db),
        patch("app.services.outbound_router.get_unlocked_number_ids", return_value=unlocked),
        patch("app.services.outbound_router.increment_send_count", new=AsyncMock(side_effect=_count_in(db))),
    ]
    for p in patches:
        p.start()
    return SenderPicker("t1"), db, patches


def _stop(patches):
    for p in patches:
        p.stop()


def test_resting_primary_is_skipped_for_broadcasts():
    picker, _, ps = _picker([_num("p", role="primary", status="restricted", quality_rating="red"),
                             _num("s")], {"p", "s"})
    try:
        assert picker.next()["id"] == "s"
    finally:
        _stop(ps)


def test_no_sender_when_only_a_red_primary_and_an_unverified_standby():
    picker, _, ps = _picker([_num("p", role="primary", status="restricted", quality_rating="red"),
                             _num("s", meta_status="PENDING", status="warming", warm_up_started_at=None)], {"p", "s"})
    try:
        assert picker.next() is None
    finally:
        _stop(ps)


@pytest.mark.asyncio
async def test_warm_up_cap_stops_a_warming_sender_for_the_day():
    picker, _, ps = _picker([_num("s", role="primary", status="warming", warm_up_started_at=_ago(0), daily_send_count=49)], {"s"})
    try:
        first = picker.next()
        assert first["id"] == "s"
        await picker.record_sent(first)  # 50th send today -- the day-0 cap
        assert picker.next() is None
    finally:
        _stop(ps)


def test_mid_broadcast_failover_moves_the_rest_to_the_new_primary():
    picker, db, ps = _picker([_num("p", role="primary"), _num("s")], {"p", "s"})
    try:
        assert picker.next()["id"] == "p"
        # Meta flags p Red mid-run: failover rests it and promotes s.
        db.row("p").update({"role": "standby", "status": "restricted", "quality_rating": "red"})
        db.row("s").update({"role": "primary"})
        picks = [picker.next()["id"] for _ in range(6)]
        assert picks[-1] == "s" and "p" not in picks[4:]
    finally:
        _stop(ps)


# ── Deferral to tomorrow ─────────────────────────────────────────────────

def test_next_ist_morning_is_just_after_midnight_ist():
    from app.services.broadcast_executor import next_ist_morning
    # 23:00 IST on 16 Oct -> 00:05 IST on 17 Oct (= 18:35 UTC on 16 Oct)
    assert next_ist_morning(datetime(2026, 10, 16, 17, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 16, 18, 35, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_scheduled_broadcast_with_no_sender_waits_for_tomorrow_instead_of_failing():
    from app.services import broadcast_executor

    class _NoSender:
        def __init__(self, _t):
            pass

        def next(self):
            return None

    db = _DB([])
    db.tables["scheduled_broadcasts"] = [{"id": "b1", "status": "pending"}]
    row = {"id": "b1", "tenant_id": "t1", "template_name": "promo", "leads_json": [{"phone": "+911111111111"}]}
    with patch("app.services.broadcast_executor.get_supabase", return_value=db), \
         patch("app.services.broadcast_executor.SenderPicker", _NoSender):
        result = await broadcast_executor.execute_broadcast(row)

    assert result["deferred"] is True
    saved = db.tables["scheduled_broadcasts"][0]
    assert saved["status"] == "pending"
    assert datetime.fromisoformat(saved["fire_at"]) > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_two_numbers_share_metas_one_daily_limit():
    """Meta's 2,000 is per business, not per number: a 3,000-person broadcast
    sends 2,000 and stops, instead of overflowing 1,000 onto the standby that
    Meta would refuse."""
    picker, db, ps = _picker([_num("p", role="primary"), _num("s")], {"p", "s"})
    try:
        sent = 0
        for _ in range(3000):
            sender = picker.next()
            if sender is None:
                break
            await picker.record_sent(sender)
            sent += 1
        assert sent == 2000
        assert db.row("p")["daily_send_count"] + db.row("s")["daily_send_count"] == 2000
    finally:
        _stop(ps)


def test_no_broadcasts_when_meta_has_reported_no_limit_on_any_number():
    picker, _, ps = _picker([_num("p", role="primary", messaging_tier=None)], {"p"})
    try:
        assert picker.next() is None
    finally:
        _stop(ps)
