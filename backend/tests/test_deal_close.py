"""R3 / D6: closing a deal on an explicit decline (close_deal) and starting a separate booking
(select_offering new_booking). Runs the real intake helpers against the in-memory FakeSupabase;
only the Razorpay cancel call is replaced."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services import deal_actions, intake
from tests.fake_supabase import FakeSupabase
from tests.test_deal_actions import CONFIG

TENANT, OTHER, LEAD, PHONE = "tenant-1", "tenant-2", "lead-1", "+910000000000"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open_deal(db, tenant=TENANT, status="awaiting_payment", **extra) -> dict:
    session = db.add("intake_sessions", **{
        "tenant_id": tenant, "lead_id": LEAD, "status": status, "package_key": "one_question",
        "package_name": "One Question", "collected_data": {"name": "Vivek"}, "skipped_fields": [],
        "payment_link": "https://rzp.io/x", "razorpay_payment_link_id": "plink_old",
        "payment_link_expires_at": _future(), **extra,
    })
    db.add("deals", tenant_id=tenant, lead_id=LEAD, stage="awaiting_payment", intake_session_id=session["id"])
    return session


def _run(db, *calls, tenant=TENANT):
    ctx = deal_actions.DealContext(config=CONFIG, db=db, lead_id=LEAD, tenant_id=tenant, phone=PHONE)
    payload = [{"function": {"name": n, "arguments": json.dumps(a)}} for n, a in calls]
    return asyncio.run(deal_actions.apply_tool_calls(payload, ctx))


def _status(db, session) -> str:
    return next(r["status"] for r in db.rows("intake_sessions") if r["id"] == session["id"])


@pytest.fixture
def plink():
    with patch.object(intake, "cancel_payment_link", new=AsyncMock(return_value=True)) as cancel:
        yield cancel


class TestCloseDeal:
    def test_an_explicit_decline_cancels_the_session_and_its_live_link(self, plink):
        db = FakeSupabase()
        session = _open_deal(db)
        out = _run(db, ("close_deal", {"reason": "venam"}))
        assert not out.refusals
        assert _status(db, session) == "cancelled"
        plink.assert_awaited_once_with("plink_old", TENANT)

    def test_the_deals_board_card_becomes_lost(self, plink):
        db = FakeSupabase()
        _open_deal(db)
        _run(db, ("close_deal", {}))
        assert db.rows("deals")[0]["stage"] == "lost"

    def test_the_lost_reason_says_the_customer_declined_not_link_expired(self, plink):
        db = FakeSupabase()
        _open_deal(db)
        _run(db, ("close_deal", {}))
        assert db.rows("deals")[0]["lost_reason"] == "Customer declined"

    def test_a_session_with_no_link_is_closed_without_a_razorpay_call(self, plink):
        db = FakeSupabase()
        session = _open_deal(db, status="collecting", payment_link=None, razorpay_payment_link_id=None)
        _run(db, ("close_deal", {}))
        assert _status(db, session) == "cancelled"
        plink.assert_not_awaited()

    def test_is_scoped_to_the_tenant(self, plink):
        db = FakeSupabase()
        theirs = _open_deal(db, tenant=OTHER)
        out = _run(db, ("close_deal", {}), tenant=TENANT)
        assert out.refusals
        assert _status(db, theirs) == "awaiting_payment"
        plink.assert_not_awaited()

    def test_an_already_closed_deal_is_a_no_op(self, plink):
        db = FakeSupabase()
        session = _open_deal(db, status="cancelled")
        out = _run(db, ("close_deal", {}))
        assert out.refusals and "no open booking" in out.refusals[0]
        assert _status(db, session) == "cancelled"
        plink.assert_not_awaited()

    def test_a_paid_deal_is_never_closed(self, plink):
        db = FakeSupabase()
        session = _open_deal(db, status="paid")
        out = _run(db, ("close_deal", {}))
        assert out.refusals and "already paid" in out.refusals[0]
        assert _status(db, session) == "paid"
        plink.assert_not_awaited()

    def test_a_payment_that_lands_during_the_turn_wins(self, plink):
        db = FakeSupabase()
        session = _open_deal(db)
        stale = dict(session)

        def paid_meanwhile(lead_id, tenant_id, db_):
            next(r for r in db.rows("intake_sessions") if r["id"] == session["id"])["status"] = "paid"
            return stale

        with patch.object(intake, "_get_active_session", side_effect=paid_meanwhile):
            out = _run(db, ("close_deal", {}))
        assert out.refusals and "Do not say it was closed" in out.refusals[0]
        assert _status(db, session) == "paid"
        plink.assert_not_awaited()


class TestNewBooking:
    def test_the_old_open_deal_and_its_link_close_before_the_new_session_opens(self, plink):
        db = FakeSupabase()
        old = _open_deal(db)
        seen_at_create: list[str] = []
        real_create = intake._create_session

        def create(lead_id, tenant_id, db_):
            seen_at_create.append(_status(db, old))
            return real_create(lead_id, tenant_id, db_)

        with patch.object(intake, "_create_session", side_effect=create):
            out = _run(db, ("select_offering", {"key": "marriage", "new_booking": True}))
        assert not out.refusals
        assert seen_at_create == ["cancelled"]
        plink.assert_awaited_once_with("plink_old", TENANT)
        opened = [r for r in db.rows("intake_sessions") if r["id"] != old["id"]]
        assert len(opened) == 1 and opened[0]["package_key"] == "marriage"
        assert opened[0]["collected_data"] == {}  # earlier details are never carried over silently

    def test_only_one_deal_is_left_open(self, plink):
        db = FakeSupabase()
        _open_deal(db)
        _run(db, ("select_offering", {"key": "marriage", "new_booking": True}))
        open_rows = [r for r in db.rows("intake_sessions") if r["status"] in intake._UNFINISHED_STATUSES]
        assert len(open_rows) == 1

    def test_without_the_flag_the_same_booking_is_re_pointed(self, plink):
        db = FakeSupabase()
        old = _open_deal(db, status="collecting", payment_link=None, razorpay_payment_link_id=None)
        _run(db, ("select_offering", {"key": "marriage"}))
        assert len(db.rows("intake_sessions")) == 1
        assert db.rows("intake_sessions")[0]["package_key"] == "marriage"
        assert _status(db, old) != "cancelled"

    def test_a_paid_customer_can_book_again_at_once(self, plink):
        """A paid booking is finished: a repeat customer gets a new booking right away, not
        after the 48h paid -> resolved auto-resolve. The paid one is left exactly as it is."""
        db = FakeSupabase()
        old = _open_deal(db, status="paid")
        out = _run(db, ("select_offering", {"key": "marriage", "new_booking": True}))
        assert not out.refusals
        assert _status(db, old) == "paid"
        plink.assert_not_awaited()
        opened = [r for r in db.rows("intake_sessions") if r["id"] != old["id"]]
        assert len(opened) == 1 and opened[0]["package_key"] == "marriage"
        assert opened[0]["collected_data"] == {}  # D6: earlier details are confirmed, never copied

    def test_a_paid_booking_without_the_flag_is_never_re_pointed(self, plink):
        db = FakeSupabase()
        old = _open_deal(db, status="paid")
        out = _run(db, ("select_offering", {"key": "marriage"}))
        assert out.refusals and "new_booking" in out.refusals[0]
        assert _status(db, old) == "paid" and len(db.rows("intake_sessions")) == 1
        assert db.rows("intake_sessions")[0]["package_key"] == "one_question"

    def test_a_deal_that_was_paid_meanwhile_blocks_the_new_booking(self, plink):
        db = FakeSupabase()
        session = _open_deal(db)
        stale = dict(session)

        def paid_meanwhile(lead_id, tenant_id, db_):
            next(r for r in db.rows("intake_sessions") if r["id"] == session["id"])["status"] = "paid"
            return stale

        with patch.object(intake, "_get_active_session", side_effect=paid_meanwhile):
            out = _run(db, ("select_offering", {"key": "marriage", "new_booking": True}))
        assert out.refusals
        assert len(db.rows("intake_sessions")) == 1 and _status(db, session) == "paid"

    def test_the_new_flag_does_not_touch_another_tenants_deal(self, plink):
        db = FakeSupabase()
        theirs = _open_deal(db, tenant=OTHER)
        _run(db, ("select_offering", {"key": "marriage", "new_booking": True}), tenant=TENANT)
        assert _status(db, theirs) == "awaiting_payment"
        plink.assert_not_awaited()
