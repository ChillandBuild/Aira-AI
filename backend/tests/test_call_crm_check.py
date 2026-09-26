"""Check 10: marked from the wrap-up, Missing after 2 hours, re-marked when the wrap-up changes."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_marking as cm

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _checks(crm_level=None):
    out = []
    for c in cm.CHECKS:
        level = "good" if c["key"] != "crm_update" else crm_level
        out.append({"key": c["key"], "full": c["full"], "level": level, "marks": cm.check_marks(c["key"], level)})
    return out


def _row(**kw):
    row = {
        "id": "call-1", "tenant_id": "t", "caller_id": "c1", "lead_id": "lead-1", "provider": "telecmi",
        "call_group": "real_conversation", "ai_status": "done",
        "created_at": (NOW - timedelta(minutes=30)).isoformat(), "feedback_at": None,
        "outcome": None, "manual_status": None, "notes": None, "wrapup_callback_at": None,
        "transcript": "[00:01] Telecaller: Hello\n[00:03] Customer: I need a demo",
        "evaluation": {"evaluation_version": 4, "group": "real_conversation", "checks": _checks(), "signs": []},
    }
    row.update(kw)
    return row


class CrmExpectedTests(unittest.TestCase):
    def test_mapping(self):
        self.assertTrue(cm.crm_matches_expected("wrong_number", {"manual_status": "wrong_number"}))
        self.assertFalse(cm.crm_matches_expected("wrong_number", {"outcome": "interested"}))
        self.assertTrue(cm.crm_matches_expected("not_enquired", {"outcome": "not_interested"}))
        self.assertTrue(cm.crm_matches_expected("callback", {"outcome": "callback", "callback_at": "2026-09-26T05:00:00+00:00"}))
        self.assertFalse(cm.crm_matches_expected("callback", {"outcome": "callback", "callback_at": None}))
        self.assertIsNone(cm.crm_matches_expected("language_barrier", {"outcome": "not_interested"}))
        self.assertIsNone(cm.crm_matches_expected("voicemail", {"outcome": None}))
        self.assertIsNone(cm.crm_matches_expected("other", {"outcome": "interested"}))


class MarkCrmUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, row, ai=None, alert_error=None):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", side_effect=lambda db, r: None if not r.get("feedback_at") else {"outcome": r.get("outcome"), "manual_status": r.get("manual_status"), "notes": r.get("notes"), "callback_at": r.get("wrapup_callback_at"), "do_not_call": False}), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(return_value=ai or {"level": "excellent", "reason": "matches"})) as gem, \
             patch.object(cm, "raise_alert", side_effect=alert_error) as alert, \
             patch.object(cm, "finalize_call_score") as fin:
            changed = await cm.mark_crm_update(db, "call-1", now=NOW)
        return changed, writes, gem, alert, fin

    async def test_no_wrapup_before_cutoff_does_nothing(self):
        changed, writes, gem, _, _ = await self._run(_row())
        self.assertFalse(changed)
        self.assertEqual(writes, [])
        gem.assert_not_called()

    async def test_no_wrapup_after_cutoff_is_missing_without_ai(self):
        row = _row(created_at=(NOW - timedelta(hours=2, minutes=1)).isoformat())
        changed, writes, gem, _, fin = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["marks"]), ("missing", 0.0))
        fin.assert_called_once()

    async def test_wrapup_marks_with_ai_and_leaves_other_checks(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested", notes="needs demo friday")
        changed, writes, gem, _, _ = await self._run(row, ai={"level": "good", "reason": "notes thin"})
        checks = writes[0]["evaluation"]["checks"]
        self.assertEqual(checks[-1]["level"], "good")
        self.assertEqual(checks[-1]["marks"], 5.25)
        self.assertEqual([c["level"] for c in checks[:-1]], ["good"] * 9)
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)

    async def test_changed_wrapup_is_remarked(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="callback", wrapup_callback_at=None)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        changed, writes, gem, _, _ = await self._run(row, ai={"level": "poor", "reason": "callback without time"})
        self.assertTrue(changed)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")

    async def test_same_wrapup_not_remarked(self):
        snap = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = snap
        changed, writes, gem, _, fin = await self._run(row)
        self.assertFalse(changed)
        self.assertEqual(writes, [])
        gem.assert_not_called()
        fin.assert_called_once()  # score_final was never set on the row: self-heal

    async def test_same_wrapup_with_score_final_already_true_skips_finalize(self):
        snap = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        row = _row(feedback_at=NOW.isoformat(), outcome="interested", score_final=True)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = snap
        changed, _, gem, _, fin = await self._run(row)
        self.assertFalse(changed)
        gem.assert_not_called()
        fin.assert_not_called()

    async def test_early_exit_mismatch_raises_alert_without_ai(self):
        row = _row(call_group="early_exit", feedback_at=NOW.isoformat(), outcome="interested",
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, fin = await self._run(row)
        gem.assert_not_called()
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        self.assertEqual(alert.call_args.kwargs["type"], "crm_mismatch")
        self.assertEqual(alert.call_args.kwargs["quote"], "The call sounded like: Wrong number. Wrap-up saved: Interested.")
        fin.assert_called_once()

    async def test_early_exit_no_wrapup_after_cutoff_is_mismatch_with_alert(self):
        row = _row(call_group="early_exit", created_at=(NOW - timedelta(hours=2, minutes=1)).isoformat(),
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, fin = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        early = writes[0]["evaluation"]["early_exit_check"]
        self.assertFalse(early["crm_matches"])
        self.assertTrue(early["no_wrapup"])
        self.assertEqual(alert.call_args.kwargs["type"], "crm_mismatch")
        self.assertEqual(alert.call_args.kwargs["quote"], "No wrap-up saved within 2 hours")
        fin.assert_called_once()

    async def test_early_exit_alert_failure_still_saves_and_finalizes(self):
        row = _row(call_group="early_exit", feedback_at=NOW.isoformat(), outcome="interested",
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, fin = await self._run(row, alert_error=RuntimeError("insert failed"))
        self.assertTrue(changed)  # the exception from raise_alert must not propagate
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        fin.assert_called_once()

    async def test_real_conversation_alert_failure_still_saves_and_finalizes(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        changed, writes, gem, alert, fin = await self._run(
            row, ai={"level": "poor", "reason": "status wrong"}, alert_error=RuntimeError("insert failed"),
        )
        self.assertTrue(changed)  # the exception from raise_alert must not propagate
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")
        fin.assert_called_once()

    async def test_ai_failure_increments_crm_attempts_and_reraises(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value={"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=RuntimeError("timeout"))), \
             patch.object(cm, "finalize_call_score") as fin:
            with self.assertRaises(RuntimeError):
                await cm.mark_crm_update(db, "call-1", now=NOW)
        self.assertEqual(writes[-1]["evaluation"]["crm_attempts"], 1)
        fin.assert_not_called()

    async def test_third_ai_failure_marks_missing_and_alerts_no_proof(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        row["evaluation"]["crm_attempts"] = 3
        changed, writes, gem, alert, fin = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["marks"], crm["reason"]),
                         ("missing", 0.0, "The wrap-up couldn't be checked automatically."))
        self.assertEqual(alert.call_args.kwargs["type"], "no_proof")
        self.assertEqual(alert.call_args.kwargs["quote"], "Wrap-up check failed 3 times")
        fin.assert_called_once()

    async def test_ai_not_done_yet_waits(self):
        changed, writes, _, _, _ = await self._run(_row(ai_status="scoring", feedback_at=NOW.isoformat(), evaluation=None))
        self.assertFalse(changed)
        self.assertEqual(writes, [])

    async def test_gemini_called_ai_votes_times(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested", notes="needs demo friday")
        _, _, gem, _, _ = await self._run(row, ai={"level": "good", "reason": "notes thin"})
        self.assertEqual(gem.await_count, cm.AI_VOTES)


class MarkCrmUpdateVotingTests(unittest.IsolatedAsyncioTestCase):
    """Check 10 also asks Gemini AI_VOTES times and decides by majority."""

    async def _run_votes(self, row, votes):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        snap = {"outcome": row.get("outcome"), "manual_status": row.get("manual_status"), "notes": row.get("notes"),
                "callback_at": row.get("wrapup_callback_at"), "do_not_call": False}
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value=snap), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=votes)), \
             patch.object(cm, "raise_alert"), \
             patch.object(cm, "finalize_call_score"):
            changed = await cm.mark_crm_update(db, "call-1", now=NOW)
        return changed, writes

    async def test_majority_level_from_three_runs(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        votes = [{"level": "good", "reason": "r1"}, {"level": "good", "reason": "r2"}, {"level": "poor", "reason": "r3"}]
        changed, writes = await self._run_votes(row, votes)
        self.assertTrue(changed)
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["reason"]), ("good", "r1"))

    async def test_all_differ_takes_median(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        votes = [{"level": "poor", "reason": "r1"}, {"level": "good", "reason": "r2"}, {"level": "excellent", "reason": "r3"}]
        changed, writes = await self._run_votes(row, votes)
        self.assertTrue(changed)
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual(crm["level"], "good")

    async def test_fewer_than_two_valid_votes_raises_and_counts_one_attempt(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        snap = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        votes = [{"level": "good", "reason": "r1"}, {"level": "not_a_real_level"}, {"level": None}]
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value=snap), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=votes)), \
             patch.object(cm, "finalize_call_score"):
            with self.assertRaises(cm.CallMarkingError):
                await cm.mark_crm_update(db, "call-1", now=NOW)
        self.assertEqual(writes[-1]["evaluation"]["crm_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
