"""Security-review fixes for the payment / deal-lifecycle work (findings 1-3, 5, 6):
a cancel event never un-wins a deal, a second payment is never silently dropped or
overwritten, the extra-payment write is a compare-and-set, the idle sweep skips a tenant whose
setting could not be read, and a racing session insert returns the existing open session."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.routes.intake import _handle_deal_payment_event
from app.services import intake
from tests.fake_supabase import FakeSupabase

T, LEAD = "t1", "lead-1"


def _event(plink_id="plink_1", payment_id=None):
    body = {"payload": {"payment_link": {"entity": {"id": plink_id, "notes": {"deal_id": "d1"}}}}}
    if payment_id:
        body["payload"]["payment"] = {"entity": {"id": payment_id}}
    return body


@pytest.fixture
def alerts():
    with patch.object(intake, "notify_pool") as pool, \
         patch("app.services.ai_reply._trigger_chat_escalation") as handover:
        yield SimpleNamespace(pool=pool, handover=handover)


def _use(db):
    """Point every get_supabase the deal webhook path touches at one fake."""
    return patch("app.services.deals.get_supabase", return_value=db), \
        patch("app.routes.intake.get_supabase", return_value=db), \
        patch("app.routes.intake._current_plink_id", return_value="plink_1")


# ---- 1. a cancel event never moves a won deal to lost ----

class TestCancelledEventOnWonDeal:
    @pytest.mark.asyncio
    async def test_a_won_deal_stays_won_and_its_stock_is_not_restored(self):
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="won", razorpay_payment_link_id="plink_1")
        a, b, c = _use(db)
        with a, b, c, patch("app.services.deals._deduct_for_deal") as stock:
            out = await _handle_deal_payment_event(_event(), "payment_link.cancelled", "d1", T)
        assert db.rows("deals")[0]["stage"] == "won"
        assert out["status"] == "ignored"
        stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_awaiting_payment_deal_is_still_marked_lost(self):
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="awaiting_payment", razorpay_payment_link_id="plink_1")
        a, b, c = _use(db)
        with a, b, c:
            out = await _handle_deal_payment_event(_event(), "payment_link.cancelled", "d1", T)
        assert db.rows("deals")[0]["stage"] == "lost" and out["status"] == "ok"

    def test_mark_lost_only_from_filters_the_claiming_update_too(self):
        from app.services import deals
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="won")
        assert deals.mark_lost(T, "d1", "x", only_from=("quoted", "awaiting_payment"), db=db) is None
        assert db.rows("deals")[0]["stage"] == "won"
        assert deals.mark_lost(T, "d1", "x", db=db) is not None  # default behaviour unchanged


# ---- 2a. a paid event on an already-won deal is not swallowed silently ----

class TestPaidEventOnWonDeal:
    async def _paid(self, db, payment_id):
        a, b, c = _use(db)
        with a, b, c:
            return await _handle_deal_payment_event(_event(payment_id=payment_id), "payment_link.paid", "d1", T)

    @pytest.mark.asyncio
    async def test_a_different_payment_on_a_won_deal_alerts_staff(self, alerts):
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="won", razorpay_payment_id="pay_1", lead_id=LEAD)
        out = await self._paid(db, "pay_2")
        assert out["status"] == "ignored"
        alerts.pool.assert_called_once()
        assert alerts.pool.call_args.args[0] == T and "pay_2" in alerts.pool.call_args.args[3]

    @pytest.mark.asyncio
    async def test_a_link_payment_after_staff_took_cash_is_flagged(self, alerts):
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="won", payment_method="cash", razorpay_payment_id=None, lead_id=LEAD)
        await self._paid(db, "pay_9")
        alerts.pool.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_redelivery_of_the_same_payment_is_a_no_op(self, alerts):
        db = FakeSupabase()
        db.add("deals", id="d1", tenant_id=T, stage="won", razorpay_payment_id="pay_1", lead_id=LEAD)
        await self._paid(db, "pay_1")
        alerts.pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_deal_linked_to_a_session_records_it_on_the_session(self, alerts):
        db = FakeSupabase()
        sess = db.add("intake_sessions", tenant_id=T, lead_id=LEAD, status="awaiting_payment",
                      razorpay_payment_id=None, extra_payment_ids=[], refund_needed=False, collected_data={})
        db.add("deals", id="d1", tenant_id=T, stage="won", razorpay_payment_id="pay_1", lead_id=LEAD,
               intake_session_id=sess["id"])
        await self._paid(db, "pay_2")
        row = db.rows("intake_sessions")[0]
        assert row["extra_payment_ids"] == ["pay_2"] and row["refund_needed"] is True
        alerts.pool.assert_called_once()
        await self._paid(db, "pay_2")  # redelivery
        alerts.pool.assert_called_once()


# ---- 2b. "already paid" is status paid OR a payment id on file ----

def _resolved_session(db, **over):
    return db.add("intake_sessions", **{
        "tenant_id": T, "lead_id": LEAD, "status": "resolved", "razorpay_payment_id": "pay_1",
        "paid_at": "2026-01-01T00:00:00+00:00", "amount_paise": 100, "extra_payment_ids": [],
        "refund_needed": False, "collected_data": {"name": "Vivek"}, **over,
    })


class TestResolvedSessionSecondPayment:
    def test_a_second_payment_on_a_resolved_session_is_extra_not_a_first_payment(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db)
        assert intake.confirm_intake_payment(sess["id"], "pay_2", amount_paid_paise=500, db=db) is None
        row = db.rows("intake_sessions")[0]
        assert row["razorpay_payment_id"] == "pay_1" and row["amount_paise"] == 100
        assert row["paid_at"] == "2026-01-01T00:00:00+00:00" and row["status"] == "resolved"
        assert row["extra_payment_ids"] == ["pay_2"] and row["refund_needed"] is True
        alerts.pool.assert_called_once()

    def test_a_retry_of_the_original_payment_on_a_resolved_session_is_a_no_op(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db)
        assert intake.confirm_intake_payment(sess["id"], "pay_1", db=db) is None
        row = db.rows("intake_sessions")[0]
        assert row["extra_payment_ids"] == [] and row["refund_needed"] is False
        alerts.pool.assert_not_called()

    def test_record_extra_payment_applies_the_same_rule(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db)
        intake._record_extra_payment(db, sess["id"], "pay_2")
        assert db.rows("intake_sessions")[0]["extra_payment_ids"] == ["pay_2"]

    def test_a_session_that_never_paid_is_left_alone_by_record_extra_payment(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db, status="cancelled", razorpay_payment_id=None)
        intake._record_extra_payment(db, sess["id"], "pay_2")
        assert db.rows("intake_sessions")[0]["extra_payment_ids"] == []
        alerts.pool.assert_not_called()


# ---- 3. the extra-payment write is a compare-and-set ----

class _StaleFirstRead:
    """Serves the first intake_sessions SELECT from before a concurrent delivery wrote."""

    def __init__(self, db, stale_row):
        self.db, self.stale = db, stale_row

    def table(self, name):
        query = self.db.table(name)
        if name != "intake_sessions":
            return query
        real_execute = query.execute

        def execute():
            if query.op == "select" and self.stale is not None:
                stale, self.stale = self.stale, None
                return SimpleNamespace(data=dict(stale), count=1)
            return real_execute()

        query.execute = execute
        return query


class _FailingWrite:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        query = self.db.table(name)
        if name == "intake_sessions":
            real_update = query.update

            def update(payload):
                boom = real_update(payload)
                boom.execute = MagicMock(side_effect=RuntimeError("db down"))
                return boom

            query.update = update
        return query


class TestExtraPaymentCompareAndSet:
    def test_a_concurrent_redelivery_that_read_stale_data_does_not_alert_again(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db, status="paid", extra_payment_ids=["pay_2"], refund_needed=True)
        stale = {**sess, "extra_payment_ids": [], "refund_needed": False}
        intake._record_extra_payment(_StaleFirstRead(db, stale), sess["id"], "pay_2")
        assert db.rows("intake_sessions")[0]["extra_payment_ids"] == ["pay_2"]
        alerts.pool.assert_not_called()
        alerts.handover.assert_not_called()

    def test_a_failed_write_still_alerts_staff(self, alerts, caplog):
        db = FakeSupabase()
        sess = _resolved_session(db, status="paid")
        with caplog.at_level("ERROR"):
            intake._record_extra_payment(_FailingWrite(db), sess["id"], "pay_2")
        alerts.pool.assert_called_once()
        assert any("pay_2" in r.getMessage() for r in caplog.records)

    def test_the_write_and_read_are_tenant_scoped(self, alerts):
        db = FakeSupabase()
        sess = _resolved_session(db, status="paid")
        intake._record_extra_payment(db, sess["id"], "pay_2", tenant_id="other-tenant")
        assert db.rows("intake_sessions")[0]["extra_payment_ids"] == []
        alerts.pool.assert_not_called()


# ---- 5. a failed settings read never falls back to 30 days in the idle sweep ----

def _ago(**delta):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


class TestIdleSweepSettingsRead:
    @pytest.fixture(autouse=True)
    def _isolated(self):
        from app import config_dynamic
        config_dynamic.invalidate_cache()
        with patch.object(intake, "_sync_deal"), \
             patch.object(intake, "cancel_session_link", new=AsyncMock(return_value=True)):
            yield
        config_dynamic.invalidate_cache()

    def _idle_db(self):
        db = FakeSupabase()
        row = db.add("intake_sessions", tenant_id=T, lead_id=LEAD, status="collecting", payment_link=None,
                     payment_link_expires_at=None, last_activity_at=_ago(days=40))
        return db, row

    @pytest.mark.asyncio
    async def test_an_unreadable_setting_skips_the_tenant_instead_of_using_30_days(self, caplog):
        db, row = self._idle_db()
        broken = MagicMock()
        broken.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .maybe_single.return_value.execute.side_effect = RuntimeError("settings db down")
        with patch("app.db.supabase.get_supabase", return_value=broken), caplog.at_level("WARNING"):
            await intake.sweep_stale_intake_sessions(db=db)
        assert db.rows("intake_sessions")[0]["status"] == "collecting"
        assert any("idle" in r.getMessage().lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_a_missing_setting_still_means_30_days(self):
        db, row = self._idle_db()
        settings = FakeSupabase()  # readable, but the tenant never set the key
        with patch("app.db.supabase.get_supabase", return_value=settings):
            await intake.sweep_stale_intake_sessions(db=db)
        assert db.rows("intake_sessions")[0]["status"] == "cancelled"

    def test_get_setting_strict_raises_when_the_read_fails_but_not_when_missing(self):
        from app import config_dynamic
        broken = MagicMock()
        broken.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .maybe_single.return_value.execute.side_effect = RuntimeError("down")
        with patch("app.db.supabase.get_supabase", return_value=broken):
            with pytest.raises(config_dynamic.SettingReadError):
                config_dynamic.get_setting_strict("some_key", tenant_id=T)
        with patch("app.db.supabase.get_supabase", return_value=FakeSupabase()):
            assert config_dynamic.get_setting_strict("some_key", tenant_id=T) is None


class TestCancelPaymentLinkNeedsATenant:
    @pytest.mark.asyncio
    async def test_tenant_id_is_a_required_argument(self):
        from app.services import payment_razorpay as pr
        with pytest.raises(TypeError):
            await pr.cancel_payment_link("plink_x")

    @pytest.mark.asyncio
    async def test_a_blank_tenant_never_reads_default_tenant_credentials(self):
        from app.services import payment_razorpay as pr
        with patch.object(pr, "_get_key_id") as key:
            assert await pr.cancel_payment_link("plink_x", "") is False
        key.assert_not_called()


# ---- 6. a racing session insert returns the existing open session ----

class _UniqueViolationDb:
    """Every insert into intake_sessions fails like the 213 unique index does."""

    def __init__(self, db, error):
        self.db, self.error = db, error

    def table(self, name):
        query = self.db.table(name)
        if name == "intake_sessions":
            real_insert = query.insert

            def insert(payload):
                q = real_insert(payload)
                q.execute = MagicMock(side_effect=self.error)
                return q

            query.insert = insert
        return query


def _unique_error():
    from postgrest import APIError
    return APIError({"message": "duplicate key value violates unique constraint \"uq_intake_one_open_per_lead\"",
                     "code": "23505", "details": "", "hint": ""})


class TestCreateSessionRace:
    def test_a_unique_violation_returns_the_existing_open_session(self):
        db = FakeSupabase()
        winner = db.add("intake_sessions", tenant_id=T, lead_id=LEAD, status="collecting")
        db.add("intake_sessions", tenant_id=T, lead_id=LEAD, status="cancelled")
        db.add("intake_sessions", tenant_id="t2", lead_id=LEAD, status="collecting")  # another tenant
        got = intake._create_session(LEAD, T, _UniqueViolationDb(db, _unique_error()))
        assert got["id"] == winner["id"]

    def test_other_database_errors_still_raise(self):
        from postgrest import APIError
        boom = APIError({"message": "boom", "code": "XX000", "details": "", "hint": ""})
        with pytest.raises(APIError):
            intake._create_session(LEAD, T, _UniqueViolationDb(FakeSupabase(), boom))

    def test_a_violation_with_no_open_session_to_return_raises(self):
        with pytest.raises(Exception):
            intake._create_session(LEAD, T, _UniqueViolationDb(FakeSupabase(), _unique_error()))

    def test_no_conflict_still_creates_normally(self):
        db = FakeSupabase()
        got = intake._create_session(LEAD, T, db)
        assert got["status"] == "offer_pending" and len(db.rows("intake_sessions")) == 1
