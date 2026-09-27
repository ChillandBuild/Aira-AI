"""Wrap-up v2 writes: call row, lead status, reminders, the sale, DNC and the reassign alert."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import wrapup_apply as wa
from app.services.deals import DealError
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # 14:00 IST
TOMORROW_10_IST = "2026-09-28T04:30:00+00:00"


class ApplyWrapupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.db.add("leads", id="lead-1", tenant_id="t1", segment="B", phone="+919800000001", ai_enabled=True,
                    converted_at=None, assigned_to="caller-1", call_status="trying", do_not_call=False, opted_out=False)
        self.db.add("call_logs", id="call-1", tenant_id="t1", lead_id="lead-1", provider="telecmi", status="completed",
                    duration_seconds=120, caller_id="caller-1", follow_up_job_id=None, outcome=None, manual_status=None,
                    created_at="2026-09-27T08:00:00+00:00")
        self.mocks = {}
        for name, mock in {
            "sync_follow_up_jobs": MagicMock(), "cancel_pending_follow_ups": MagicMock(),
            "record_stage_event": MagicMock(), "maybe_assign_lead": MagicMock(),
            "get_telecalling_config": MagicMock(return_value={"max_call_attempts": 4}),
            "create_deal": AsyncMock(return_value={"deal": {"id": "deal-1"}}),
            "raise_reassign_alert": MagicMock(),
        }.items():
            patcher = patch.object(wa, name, mock)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    async def run_wrapup(self, log_patch=None, log_extra=None, **wrapup):
        body = {"manual_status": "connected", "outcome": None, "notes": None, "next_action_at": None, "reason": None,
                "preferred_language": None, "stop_messages": False, "products": [], "amount_paise": None}
        body.update(wrapup)
        log = {**self.call(), **(log_patch or {})}
        return await wa.apply_wrapup(self.db, tenant_id="t1", user_id="user-1", caller_id="caller-1",
                                     call_log_id="call-1", log=log, wrapup=body, log_extra=log_extra or {}, now=NOW)

    def call(self):
        return next(r for r in self.db.rows("call_logs") if r["id"] == "call-1")

    def lead(self):
        return self.db.rows("leads")[0]

    def reminders(self):
        return [r for r in self.db.rows("follow_up_jobs") if r.get("channel") == "phone" and r.get("status") == "pending"]

    def earlier_call(self, created_at, **kw):
        self.db.add("call_logs", tenant_id="t1", lead_id="lead-1", created_at=created_at, **{"status": "completed", **kw})

    # ── didn't connect ─────────────────────────────────────────────
    async def test_not_picked_sets_trying_and_a_two_hour_retry(self):
        out = await self.run_wrapup(manual_status="not_picked")
        self.assertEqual(self.lead()["call_status"], "trying")
        self.assertEqual((self.call()["manual_status"], self.call()["outcome"]), ("not_picked", None))
        self.assertEqual(self.call()["next_action_at"], "2026-09-27T10:30:00+00:00")
        [reminder] = self.reminders()
        self.assertEqual(reminder["scheduled_for"], "2026-09-27T10:30:00+00:00")
        self.assertEqual((reminder["cadence"], reminder["message_preview"]), ("callback", "Retry: Not picked"))
        self.assertEqual(reminder["scheduled_by_caller_id"], "caller-1")
        self.assertEqual(out["next_action_at"], "2026-09-27T10:30:00+00:00")
        self.mocks["sync_follow_up_jobs"].assert_called_once()

    async def test_third_failure_in_a_row_retries_tomorrow_10am(self):
        self.earlier_call("2026-09-27T06:00:00+00:00", manual_status="busy")
        self.earlier_call("2026-09-27T05:00:00+00:00", manual_status="not_picked")
        await self.run_wrapup(manual_status="not_picked")
        self.assertEqual(self.reminders()[0]["scheduled_for"], TOMORROW_10_IST)

    async def test_telecallers_time_wins_over_the_suggestion(self):
        chosen = datetime(2026, 9, 27, 12, 30, tzinfo=UTC)
        await self.run_wrapup(manual_status="busy", next_action_at=chosen)
        self.assertEqual(self.reminders()[0]["scheduled_for"], chosen.isoformat())

    async def test_reaching_max_attempts_makes_the_lead_unreachable(self):
        self.mocks["get_telecalling_config"].return_value = {"max_call_attempts": 2}
        self.lead()["assigned_to"] = None
        self.earlier_call("2026-09-26T05:00:00+00:00", manual_status="not_picked")
        out = await self.run_wrapup(manual_status="switched_off")
        self.assertEqual(out["call_status"], "unreachable")
        self.assertIsNone(out["next_action_at"])
        self.assertIsNone(self.call()["next_action_at"])
        self.assertEqual(self.reminders(), [])
        self.mocks["maybe_assign_lead"].assert_not_called()

    # ── connected ──────────────────────────────────────────────────
    async def test_interested_booked_is_hot_with_a_reminder_and_stage_event(self):
        at = datetime(2026, 10, 2, 5, 30, tzinfo=UTC)
        await self.run_wrapup(outcome="interested_booked", next_action_at=at, notes="Demo booked")
        self.assertEqual(self.lead()["call_status"], "hot")
        [reminder] = self.reminders()
        self.assertEqual(reminder["scheduled_for"], at.isoformat())
        self.assertEqual(reminder["message_preview"], "Interested, next step booked — Demo booked")
        self.assertEqual(self.call()["notes"], "Demo booked")
        event = self.mocks["record_stage_event"].call_args
        self.assertEqual(event.kwargs["event_type"], "call_outcome")
        self.assertEqual(event.kwargs["metadata"]["outcome"], "interested_booked")

    async def test_needs_time_is_warm(self):
        await self.run_wrapup(outcome="interested_needs_time", next_action_at=datetime(2026, 9, 29, 5, 0, tzinfo=UTC), notes="x")
        self.assertEqual(self.lead()["call_status"], "warm")

    async def test_maybe_later_without_a_date_is_cold_with_no_reminder(self):
        await self.run_wrapup(outcome="maybe_later")
        self.assertEqual(self.lead()["call_status"], "cold")
        self.assertEqual(self.reminders(), [])
        self.assertIsNone(self.call()["next_action_at"])

    async def test_call_later_is_callback(self):
        await self.run_wrapup(outcome="call_later", next_action_at=datetime(2026, 9, 27, 12, 30, tzinfo=UTC))
        self.assertEqual(self.lead()["call_status"], "callback")
        self.assertEqual(len(self.reminders()), 1)

    async def test_converted_creates_a_won_call_deal_from_products(self):
        self.lead()["assigned_to"] = None
        out = await self.run_wrapup(outcome="converted", notes="Paid by UPI", products=[{"catalog_item_id": "item-1", "qty": 2}])
        self.mocks["create_deal"].assert_awaited_once_with(
            "t1", "lead-1", [{"catalog_item_id": "item-1", "qty": 2}], "call", "won",
            payment_method="other", notes="Paid by UPI", created_by="user-1", db=self.db,
        )
        self.assertEqual(out["deal_id"], "deal-1")
        self.assertEqual((self.lead()["call_status"], self.lead()["converted_at"]), ("converted", NOW.isoformat()))
        self.assertEqual(self.lead()["conversion_notes"], "Paid by UPI")
        self.assertEqual(self.mocks["record_stage_event"].call_args.kwargs["event_type"], "converted")
        self.mocks["maybe_assign_lead"].assert_not_called()

    async def test_converted_with_an_amount(self):
        await self.run_wrapup(outcome="converted", notes="cash", amount_paise=150000)
        self.assertEqual(self.mocks["create_deal"].await_args.args[2],
                         [{"name": "Sale on call", "qty": 1, "unit_price_paise": 150000}])

    async def test_resubmitted_conversion_does_not_create_a_second_deal(self):
        await self.run_wrapup(outcome="converted", notes="cash", amount_paise=150000)
        self.mocks["create_deal"].reset_mock()
        await self.run_wrapup(outcome="converted", notes="cash", amount_paise=150000)
        self.mocks["create_deal"].assert_not_awaited()

    async def test_two_back_to_back_conversions_from_the_same_stale_snapshot_create_one_deal(self):
        # Simulates a genuine double-tap / retry race: both requests read the call_logs row
        # while its outcome is still None, before either one's write lands. The conditional
        # update -- not the caller's stale snapshot -- has to be what stops the second deal.
        stale_log = dict(self.call())  # a true snapshot -- not a live reference into the fake table
        body = {"manual_status": "connected", "outcome": "converted", "notes": "cash", "next_action_at": None,
                "reason": None, "preferred_language": None, "stop_messages": False, "products": [],
                "amount_paise": 150000}
        for _ in range(2):
            await wa.apply_wrapup(self.db, tenant_id="t1", user_id="user-1", caller_id="caller-1",
                                   call_log_id="call-1", log=stale_log, wrapup=body, log_extra={}, now=NOW)
        self.mocks["create_deal"].assert_awaited_once()
        self.assertEqual(self.call()["outcome"], "converted")

    async def test_a_failed_deal_writes_nothing(self):
        self.mocks["create_deal"].side_effect = DealError("No price for Pen")
        with self.assertRaises(DealError):
            await self.run_wrapup(outcome="converted", notes="x", products=[{"catalog_item_id": "pen", "qty": 1}])
        self.assertIsNone(self.call()["manual_status"])
        self.assertIsNone(self.call()["outcome"])
        self.assertEqual(self.lead()["call_status"], "trying")

    async def test_a_failed_deal_after_the_claim_reverts_the_outcome_and_still_writes_nothing_else(self):
        # The claim succeeds (outcome flips to 'converted'), then create_deal blows up. The
        # revert has to put outcome back exactly as the caller's snapshot had it, so a retry
        # of the same wrap-up can claim it again instead of being permanently locked out.
        self.db.add("call_logs", id="call-2", tenant_id="t1", lead_id="lead-1", provider="telecmi",
                     status="completed", duration_seconds=60, caller_id="caller-1", follow_up_job_id=None,
                     outcome="not_interested", manual_status="connected", created_at="2026-09-27T07:00:00+00:00")
        self.mocks["create_deal"].side_effect = DealError("No price for Pen")
        log = dict(next(r for r in self.db.rows("call_logs") if r["id"] == "call-2"))  # a snapshot, not a live reference
        body = {"manual_status": "connected", "outcome": "converted", "notes": "x", "next_action_at": None,
                "reason": None, "preferred_language": None, "stop_messages": False,
                "products": [{"catalog_item_id": "pen", "qty": 1}], "amount_paise": None}
        with self.assertRaises(DealError):
            await wa.apply_wrapup(self.db, tenant_id="t1", user_id="user-1", caller_id="caller-1",
                                   call_log_id="call-2", log=log, wrapup=body, log_extra={}, now=NOW)
        reverted = next(r for r in self.db.rows("call_logs") if r["id"] == "call-2")
        self.assertEqual(reverted["outcome"], "not_interested")
        self.assertEqual(reverted["manual_status"], "connected")
        self.assertIsNone(reverted.get("feedback_at"))
        self.assertEqual(self.lead()["call_status"], "trying")

    async def test_not_interested_and_disqualified_save_the_reason(self):
        await self.run_wrapup(outcome="not_interested", reason="price")
        self.assertEqual((self.lead()["call_status"], self.call()["outcome_reason"]), ("not_interested", "price"))
        self.mocks["sync_follow_up_jobs"].assert_called_once()
        await self.run_wrapup(outcome="disqualified", reason="never_enquired")
        self.assertEqual((self.lead()["call_status"], self.call()["outcome_reason"]), ("disqualified", "never_enquired"))

    async def test_reason_and_language_are_only_kept_for_their_options(self):
        await self.run_wrapup(outcome="maybe_later", reason="price", preferred_language="tamil")
        self.assertEqual((self.call()["outcome_reason"], self.call()["preferred_language"]), (None, None))

    async def test_wrong_number_blocks_calls_and_cancels_every_follow_up(self):
        await self.run_wrapup(outcome="wrong_number")
        self.assertEqual((self.lead()["call_status"], self.lead()["do_not_call"]), ("wrong_number", True))
        self.mocks["cancel_pending_follow_ups"].assert_called_once_with("lead-1", reason="dnc_wrong_number", db=self.db)
        self.mocks["sync_follow_up_jobs"].assert_not_called()

    async def test_do_not_call_optionally_stops_messages(self):
        await self.run_wrapup(outcome="do_not_call")
        self.assertEqual((self.lead()["call_status"], self.lead()["do_not_call"], self.lead()["opted_out"]), ("dnc", True, False))
        await self.run_wrapup(outcome="do_not_call", stop_messages=True)
        self.assertTrue(self.lead()["opted_out"])

    async def test_language_barrier_saves_the_language_and_alerts(self):
        await self.run_wrapup(outcome="language_barrier", preferred_language="tamil")
        self.assertEqual((self.lead()["call_status"], self.call()["preferred_language"]), ("language_barrier", "tamil"))
        self.mocks["raise_reassign_alert"].assert_called_once_with(
            self.db, tenant_id="t1", call_log_id="call-1", caller_id="caller-1", language="tamil",
        )

    async def test_a_failing_alert_never_fails_the_wrapup(self):
        self.mocks["raise_reassign_alert"].side_effect = RuntimeError("insert failed")
        out = await self.run_wrapup(outcome="language_barrier", preferred_language="hindi")
        self.assertEqual(out["call_status"], "language_barrier")

    async def test_the_linked_scheduled_call_is_closed(self):
        self.db.add("follow_up_jobs", id="job-1", tenant_id="t1", lead_id="lead-1", channel="phone", cadence="callback", status="pending")
        await self.run_wrapup(log_patch={"follow_up_job_id": "job-1"}, outcome="maybe_later")
        job = next(r for r in self.db.rows("follow_up_jobs") if r["id"] == "job-1")
        self.assertEqual(job["status"], "sent")

    async def test_the_linked_scheduled_call_is_canceled_on_dnc(self):
        self.db.add("follow_up_jobs", id="job-1", tenant_id="t1", lead_id="lead-1", channel="phone", cadence="callback", status="pending")
        await self.run_wrapup(log_patch={"follow_up_job_id": "job-1"}, outcome="do_not_call")
        job = next(r for r in self.db.rows("follow_up_jobs") if r["id"] == "job-1")
        self.assertEqual((job["status"], job["skip_reason"]), ("canceled", "dnc_do_not_call"))

    async def test_an_unassigned_open_lead_is_offered_for_assignment(self):
        self.lead()["assigned_to"] = None
        await self.run_wrapup(outcome="interested_needs_time", next_action_at=datetime(2026, 9, 29, 5, 0, tzinfo=UTC), notes="x")
        self.mocks["maybe_assign_lead"].assert_called_once_with("lead-1", "t1", "B", None, reason="call_interested_needs_time")

    async def test_segment_is_never_in_the_lead_update(self):
        captured = []
        real_table = self.db.table

        def spying_table(name):
            query = real_table(name)
            if name == "leads":
                original_update = query.update

                def update(payload, original_update=original_update):
                    captured.append(payload)
                    return original_update(payload)

                query.update = update
            return query

        with patch.object(self.db, "table", side_effect=spying_table):
            for outcome, extra in [
                ("interested_booked", {"next_action_at": datetime(2026, 10, 2, 5, 30, tzinfo=UTC), "notes": "x"}),
                ("maybe_later", {}),
                ("wrong_number", {}),
                ("do_not_call", {}),
                ("language_barrier", {"preferred_language": "tamil"}),
                ("converted", {"notes": "cash", "amount_paise": 100}),
            ]:
                await self.run_wrapup(outcome=outcome, **extra)

        self.assertTrue(captured)
        for payload in captured:
            self.assertNotIn("segment", payload)

    async def test_sim_rows_are_completed_manually_with_typed_timing(self):
        await self.run_wrapup(log_patch={"provider": "sim_basic"}, log_extra={"duration_seconds": 95}, outcome="maybe_later")
        self.assertEqual((self.call()["status"], self.call()["feedback_source"], self.call()["duration_seconds"]),
                         ("completed", "manual", 95))
        self.assertEqual(self.call()["feedback_at"], NOW.isoformat())

    async def test_a_call_without_a_lead_still_saves(self):
        out = await self.run_wrapup(log_patch={"lead_id": None}, manual_status="busy")
        self.assertIsNone(out["call_status"])
        self.assertEqual(self.call()["manual_status"], "busy")
        self.assertEqual(self.reminders(), [])


if __name__ == "__main__":
    unittest.main()
