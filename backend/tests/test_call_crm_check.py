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
    async def _run(self, row, ai=None):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", side_effect=lambda db, r: None if not r.get("feedback_at") else {"outcome": r.get("outcome"), "manual_status": r.get("manual_status"), "notes": r.get("notes"), "callback_at": r.get("wrapup_callback_at"), "do_not_call": False}), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(return_value=ai or {"level": "excellent", "reason": "matches"})) as gem, \
             patch.object(cm, "raise_alert") as alert, \
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
        changed, _, gem, _, _ = await self._run(row)
        self.assertFalse(changed)
        gem.assert_not_called()

    async def test_early_exit_mismatch_raises_alert_without_ai(self):
        row = _row(call_group="early_exit", feedback_at=NOW.isoformat(), outcome="interested",
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, _ = await self._run(row)
        gem.assert_not_called()
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        self.assertEqual(alert.call_args.kwargs["type"], "crm_mismatch")
        self.assertEqual(alert.call_args.kwargs["quote"], "The call sounded like: Wrong number. Wrap-up saved: Interested.")

    async def test_ai_not_done_yet_waits(self):
        changed, writes, _, _, _ = await self._run(_row(ai_status="scoring", feedback_at=NOW.isoformat(), evaluation=None))
        self.assertFalse(changed)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
