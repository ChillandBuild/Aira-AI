"""R3 / D3: last_activity_at moves only on a lead message or real deal progress, never on our
own outbound, a nudge, or a link expiring. D2: an expired current link clears the link and
keeps the deal open."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import intake
from tests.fake_supabase import FakeSupabase

TENANT, OTHER_TENANT, LEAD = "tenant-1", "tenant-2", "lead-1"
OLD = "2026-01-01T00:00:00+00:00"


def _db(**session) -> tuple[FakeSupabase, dict]:
    db = FakeSupabase()
    row = db.add("intake_sessions", **{
        "tenant_id": TENANT, "lead_id": LEAD, "status": "awaiting_payment", "last_activity_at": OLD,
        "payment_link": "https://rzp.io/x", "razorpay_payment_link_id": "plink_1",
        "payment_link_expires_at": "2026-01-02T00:00:00+00:00", **session,
    })
    return db, row


def _session(db) -> dict:
    return db.rows("intake_sessions")[0]


def test_touch_sets_last_activity_to_now():
    db, row = _db()
    intake.touch_session_activity(db, TENANT, row["id"])
    assert _session(db)["last_activity_at"] > OLD


def test_touch_is_scoped_to_the_tenant():
    db, row = _db()
    intake.touch_session_activity(db, OTHER_TENANT, row["id"])
    assert _session(db)["last_activity_at"] == OLD


def test_inbound_message_touches_the_open_session_and_returns_the_previous_value():
    db, _ = _db()
    previous = intake.note_lead_message(db, TENANT, LEAD)
    assert previous == OLD
    assert _session(db)["last_activity_at"] > OLD


def test_inbound_message_does_not_touch_a_paid_or_cancelled_session():
    for status in ("paid", "cancelled"):
        db, _ = _db(status=status)
        assert intake.note_lead_message(db, TENANT, LEAD) is None
        assert _session(db)["last_activity_at"] == OLD


def test_inbound_message_for_another_tenants_lead_touches_nothing():
    db, _ = _db()
    assert intake.note_lead_message(db, OTHER_TENANT, LEAD) is None
    assert _session(db)["last_activity_at"] == OLD


def test_inbound_touch_failure_never_raises():
    class Boom:
        def table(self, _):
            raise RuntimeError("db down")
    assert intake.note_lead_message(Boom(), TENANT, LEAD) is None


def test_progress_writes_touch_but_a_plain_patch_does_not():
    db, row = _db()
    with patch.object(intake, "_sync_deal"):
        intake._update_session(row["id"], {"payment_link_expires_at": "2026-01-03T00:00:00+00:00"}, db)
        assert _session(db)["last_activity_at"] == OLD
        for patch_ in (
            {"package_key": "k", "status": "collecting"},
            {"collected_data": {"a": 1}},
            {"skipped_fields": ["a"]},
            {"status": "awaiting_payment", "payment_link": "https://rzp.io/y"},
            {"status": "paid"},
        ):
            db.rows("intake_sessions")[0]["last_activity_at"] = OLD
            intake._update_session(row["id"], patch_, db)
            assert _session(db)["last_activity_at"] > OLD, patch_


def test_cancelling_a_session_is_not_progress():
    db, row = _db()
    with patch.object(intake, "_sync_deal"):
        intake._update_session(row["id"], {"status": "cancelled"}, db)
    assert _session(db)["last_activity_at"] == OLD


def test_a_new_session_starts_its_idle_clock_now():
    db = FakeSupabase()
    created = intake._create_session(LEAD, TENANT, db)
    assert created["last_activity_at"]


def test_expiry_clears_the_link_and_keeps_the_deal_open():
    db, row = _db()
    with patch.object(intake, "_sync_deal") as sync:
        assert intake.expire_intake_session(row["id"], db=db) is True
    saved = _session(db)
    assert saved["status"] == "awaiting_payment"
    assert saved["payment_link"] is None and saved["payment_link_expires_at"] is None
    assert saved["razorpay_payment_link_id"] == "plink_1"  # kept for audit and the next link's key
    assert saved["last_activity_at"] == OLD  # link expiry is not activity
    sync.assert_called_once()


def test_expiry_ignores_a_link_that_is_still_live():
    future = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db, row = _db(payment_link_expires_at=future)
    with patch.object(intake, "_sync_deal"):
        assert intake.expire_intake_session(row["id"], db=db) is False
    assert _session(db)["payment_link"] == "https://rzp.io/x"


def test_expiry_does_not_touch_a_session_that_moved_on():
    db, row = _db(status="paid")
    with patch.object(intake, "_sync_deal"):
        assert intake.expire_intake_session(row["id"], db=db) is False
    assert _session(db)["status"] == "paid"
