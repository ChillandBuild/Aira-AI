"""Wrap-up v2 rules: retry times, streaks, lead status, validation, phrases, context, connect rate."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_wrapup as cw

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # Sunday 14:00 IST
TOMORROW_10 = datetime(2026, 9, 28, 4, 30, tzinfo=UTC)  # Monday 10:00 IST


def _v(**kw):
    args = dict(
        never_connected=False, manual_status="connected", outcome="maybe_later", notes=None,
        next_action_at=None, reason=None, preferred_language=None, has_products=False,
        amount_paise=None, now=NOW,
    )
    args.update(kw)
    cw.validate_wrapup(**args)


class RetryTests(unittest.TestCase):
    def test_not_picked_is_two_hours_later(self):
        self.assertEqual(cw.suggest_retry_at("not_picked", 0, NOW), NOW + timedelta(hours=2))

    def test_busy_is_thirty_minutes_later(self):
        self.assertEqual(cw.suggest_retry_at("busy", 1, NOW), NOW + timedelta(minutes=30))

    def test_switched_off_is_tomorrow_10am_ist(self):
        self.assertEqual(cw.suggest_retry_at("switched_off", 0, NOW), TOMORROW_10)

    def test_third_failure_in_a_row_is_tomorrow_10am(self):
        self.assertEqual(cw.suggest_retry_at("not_picked", 2, NOW), TOMORROW_10)

    def test_tomorrow_follows_the_ist_calendar_after_midnight_ist(self):
        late = datetime(2026, 9, 27, 19, 0, tzinfo=UTC)  # 00:30 IST on the 28th
        self.assertEqual(cw.tomorrow_at_10(late), datetime(2026, 9, 29, 4, 30, tzinfo=UTC))

    def test_suggestions_are_utc(self):
        self.assertEqual(cw.suggest_retry_at("busy", 0, NOW.astimezone(cw.IST)).utcoffset(), timedelta(0))

    def test_connected_has_no_retry(self):
        with self.assertRaises(cw.WrapupError):
            cw.suggest_retry_at("connected", 0, NOW)


class StreakTests(unittest.TestCase):
    def test_counts_until_the_first_connected_call(self):
        logs = [
            {"manual_status": "busy"}, {"manual_status": None, "status": "no_answer"},
            {"manual_status": "connected"}, {"manual_status": "busy"},
        ]
        self.assertEqual(cw.consecutive_no_connects(logs), 2)

    def test_a_call_still_in_progress_breaks_the_streak(self):
        self.assertEqual(cw.consecutive_no_connects([{"manual_status": None, "status": "initiated"}, {"manual_status": "busy"}]), 0)

    def test_empty_history(self):
        self.assertEqual(cw.consecutive_no_connects([]), 0)


class LeadStatusTests(unittest.TestCase):
    def test_no_connect_is_trying_until_max_attempts(self):
        self.assertEqual(cw.lead_status_after("not_picked", None, 3, 4), "trying")
        self.assertEqual(cw.lead_status_after("busy", None, 4, 4), "unreachable")

    def test_each_outcome_maps_to_the_approved_status(self):
        expected = {
            "interested_booked": "hot", "interested_needs_time": "warm", "maybe_later": "cold",
            "call_later": "callback", "converted": "converted", "not_interested": "not_interested",
            "disqualified": "disqualified", "wrong_number": "wrong_number",
            "language_barrier": "language_barrier", "do_not_call": "dnc",
        }
        for outcome, status in expected.items():
            self.assertEqual(cw.lead_status_after("connected", outcome, 0, 4), status)

    def test_every_status_is_allowed(self):
        self.assertTrue(set(cw.LEAD_STATUS_FOR_OUTCOME.values()) <= set(cw.LEAD_CALL_STATUSES))


class ValidateTests(unittest.TestCase):
    def assertRejects(self, message, **kw):
        with self.assertRaises(cw.WrapupError) as err:
            _v(**kw)
        self.assertEqual(str(err.exception), message)

    def test_a_valid_wrapup_passes(self):
        _v()
        _v(manual_status="busy", outcome=None)

    def test_cloud_call_that_never_connected_cannot_be_connected(self):
        self.assertRejects("This call never connected, so pick Not picked, Busy or Switched off.", never_connected=True)

    def test_no_connect_cannot_have_a_result(self):
        self.assertRejects("Only a connected call can have a result.", manual_status="not_picked", outcome="maybe_later")

    def test_connected_needs_a_result(self):
        self.assertRejects("Pick what happened on the call.", outcome=None)

    def test_notes_required(self):
        for outcome in ("interested_booked", "interested_needs_time"):
            self.assertRejects("Add a short note for this result.", outcome=outcome, next_action_at=NOW + timedelta(days=1))
        self.assertRejects("Add a short note for this result.", outcome="converted", amount_paise=50000, notes="  ")

    def test_time_required(self):
        for outcome in ("interested_booked", "interested_needs_time", "call_later"):
            self.assertRejects("Pick a date and time.", outcome=outcome, notes="x")

    def test_maybe_later_time_is_optional(self):
        _v(outcome="maybe_later", next_action_at=None)

    def test_past_time_is_rejected(self):
        self.assertRejects("Pick a time in the future.", outcome="call_later", next_action_at=NOW - timedelta(minutes=6))
        _v(outcome="call_later", next_action_at=NOW - timedelta(minutes=4))

    def test_reasons(self):
        self.assertRejects("Pick why they're not interested.", outcome="not_interested", reason=None)
        self.assertRejects("Pick why the lead is disqualified.", outcome="disqualified", reason="price")
        _v(outcome="disqualified", reason="never_enquired")

    def test_language(self):
        self.assertRejects("Pick the language the customer speaks.", outcome="language_barrier")
        _v(outcome="language_barrier", preferred_language="tamil")

    def test_sale_needs_products_or_amount_not_both(self):
        self.assertRejects("Add the products sold or the amount.", outcome="converted", notes="paid")
        self.assertRejects("Add the products sold or the amount, not both.", outcome="converted", notes="paid", has_products=True, amount_paise=100)
        _v(outcome="converted", notes="paid", has_products=True)


class ContextTests(unittest.TestCase):
    def test_no_call_row(self):
        ctx = cw.wrapup_context(None, 0, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"], ctx["failed_before"]), (None, False, 0))
        self.assertEqual(ctx["retry_suggestions"]["not_picked"], (NOW + timedelta(hours=2)).isoformat())

    def test_cloud_answered_prefills_connected(self):
        ctx = cw.wrapup_context({"provider": "telecmi", "status": "completed", "duration_seconds": 80}, 0, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"]), ("connected", False))

    def test_cloud_missed_prefills_not_picked(self):
        ctx = cw.wrapup_context({"provider": "telecmi", "status": "no_answer", "duration_seconds": 0}, 2, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"]), ("not_picked", True))
        self.assertEqual(set(ctx["retry_suggestions"].values()), {TOMORROW_10.isoformat()})

    def test_sim_is_never_prefilled(self):
        self.assertIsNone(cw.wrapup_context({"provider": "sim_basic", "status": "sim_started"}, 0, NOW)["connect_prefill"])


class PhraseTests(unittest.TestCase):
    def test_within_a_week_uses_the_weekday(self):
        at = datetime(2026, 10, 2, 5, 30, tzinfo=UTC)
        self.assertEqual(cw.next_step_phrase("interested_booked", at, NOW), "Next step on Friday at 11 AM")

    def test_today_and_tomorrow(self):
        self.assertEqual(cw.next_step_phrase("call_later", datetime(2026, 9, 27, 12, 30, tzinfo=UTC), NOW), "Call back today at 6 PM")
        self.assertEqual(
            cw.next_step_phrase("interested_needs_time", datetime(2026, 9, 28, 5, 0, tzinfo=UTC), NOW),
            "Follow-up call tomorrow at 10:30 AM",
        )

    def test_far_dates_use_day_and_month(self):
        self.assertEqual(cw.next_step_phrase("interested_booked", datetime(2026, 10, 10, 5, 30, tzinfo=UTC), NOW), "Next step on 10 Oct at 11 AM")


class SmallHelperTests(unittest.TestCase):
    def test_reminder_note(self):
        self.assertEqual(cw.reminder_note("busy", None, None), "Retry: Busy")
        self.assertEqual(cw.reminder_note("connected", "call_later", "after salary"), "Call later (customer asked) — after salary")

    def test_sale_lines(self):
        self.assertEqual(cw.sale_lines([{"catalog_item_id": "i1", "qty": 2}], None), [{"catalog_item_id": "i1", "qty": 2}])
        self.assertEqual(cw.sale_lines([], 150000), [{"name": "Sale on call", "qty": 1, "unit_price_paise": 150000}])

    def test_connect_rate_counts_wrapups_only(self):
        logs = [{"manual_status": "connected"}, {"manual_status": "not_picked"}, {"manual_status": None}, {"manual_status": "busy"}]
        self.assertEqual(cw.connect_rate(logs), 0.3333)
        self.assertEqual(cw.connect_rate([]), 0.0)

    def test_as_aware_reads_naive_times_as_ist(self):
        self.assertEqual(cw.as_aware(datetime(2026, 9, 28, 10, 0)), TOMORROW_10)

    def test_call_result_label(self):
        self.assertEqual(cw.call_result_label({"outcome": "maybe_later", "manual_status": "connected"}), "Maybe later")
        self.assertEqual(cw.call_result_label({"outcome": None, "manual_status": "busy"}), "Busy")
        self.assertIsNone(cw.call_result_label({}))


if __name__ == "__main__":
    unittest.main()
