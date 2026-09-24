"""The 7 (AI) + 3 (outcome) call score, the no-answer safety gate and flag raising."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_scorer as sc

EIGHT = ["greeting_quality", "communication_clarity", "product_knowledge", "requirement_understanding",
         "conversation_engagement", "objection_handling", "professionalism", "tone"]


def _evaluation(average=7.6, closing=10, acceptable=("interested", "callback"), real=True):
    return {
        "evaluation_version": 3,
        "criteria": EIGHT,
        "ai_average": average,
        "closing_move": closing,
        "acceptable_outcomes": list(acceptable),
        "real_conversation": real,
    }


def _score(**kw):
    args = {"status": "completed", "duration": 240, "outcome": "interested", "evaluation": _evaluation(),
            "ai_status": "done", "flag_status": None}
    args.update(kw)
    return sc.compute_call_score(**args)


class ScoreMathTests(unittest.TestCase):
    def test_worked_example_from_the_plan(self):
        """AI average 7.6 -> 5.32, correct outcome 1 + full closing 2 -> 8.3."""
        result = _score()
        self.assertEqual(result["score_status"], "scored")
        self.assertEqual(result["score"], 8.3)
        breakdown = result["score_breakdown"]
        self.assertEqual(breakdown["ai_points"], 5.32)
        self.assertEqual(breakdown["accuracy_point"], 1.0)
        self.assertEqual(breakdown["closing_points"], 2.0)

    def test_a_well_handled_not_interested_call_can_score_ten(self):
        result = _score(outcome="not_interested", evaluation=_evaluation(average=10, acceptable=("not_interested",)))
        self.assertEqual(result["score"], 10.0)

    def test_wrong_outcome_loses_only_the_accuracy_point_and_is_not_flagged(self):
        result = _score(outcome="converted")
        self.assertEqual(result["score"], 7.3)
        self.assertFalse(result["raise_flag"])

    def test_closing_move_scales_to_two_points(self):
        self.assertEqual(_score(evaluation=_evaluation(average=0, closing=5))["score"], 2.0)


class NotScoredTests(unittest.TestCase):
    def test_before_the_cdr_arrives_the_call_is_pending(self):
        self.assertEqual(_score(status="initiated", duration=None)["score_status"], "pending")

    def test_under_thirty_seconds_is_a_short_call(self):
        result = _score(duration=29)
        self.assertEqual((result["score_status"], result["score"]), ("short_call", None))

    def test_short_call_marked_no_answer_is_labelled_no_answer(self):
        self.assertEqual(_score(duration=12, outcome="no_answer")["score_status"], "no_answer")

    def test_zero_talk_time_is_no_answer(self):
        self.assertEqual(_score(status="no_answer", duration=0, outcome="no_answer", ai_status=None)["score_status"], "no_answer")

    def test_waiting_on_ai_or_outcome(self):
        self.assertEqual(_score(ai_status="transcribing", evaluation=None)["score_status"], "pending")
        self.assertEqual(_score(outcome=None)["score_status"], "awaiting_outcome")

    def test_failed_processing_and_missing_recording(self):
        self.assertEqual(_score(ai_status="failed", evaluation=None)["score_status"], "failed")
        self.assertEqual(_score(ai_status=None, evaluation=None)["score_status"], "no_recording")

    def test_an_old_v2_evaluation_is_never_scored(self):
        self.assertEqual(_score(evaluation={"overall_score": 8, "evaluation_version": 2})["score_status"], "pending")


class SafetyGateTests(unittest.TestCase):
    def test_no_answer_on_a_real_conversation_is_scored_zero_outcome_and_flagged(self):
        result = _score(outcome="no_answer")
        self.assertEqual(result["score_status"], "scored")
        self.assertEqual(result["score_breakdown"]["outcome_points"], 0.0)
        self.assertEqual(result["score"], 5.3)
        self.assertTrue(result["raise_flag"])

    def test_no_answer_on_voicemail_is_just_no_answer(self):
        result = _score(outcome="no_answer", evaluation=_evaluation(real=False))
        self.assertEqual(result["score_status"], "no_answer")
        self.assertFalse(result["raise_flag"])

    def test_confirmed_flag_stays_scored_without_reflagging(self):
        result = _score(outcome="no_answer", flag_status="confirmed")
        self.assertEqual(result["score_status"], "scored")
        self.assertFalse(result["raise_flag"])

    def test_dismissed_flag_returns_the_call_to_no_answer(self):
        result = _score(outcome="no_answer", flag_status="dismissed")
        self.assertEqual((result["score_status"], result["score"]), ("no_answer", None))


def _db_with_row(row):
    db = MagicMock()
    select_chain = db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value
    select_chain.execute.return_value = MagicMock(data=row)
    return db


class FinalizeTests(unittest.TestCase):
    ROW = {"id": "c1", "tenant_id": "t1", "caller_id": "k1", "lead_id": "l1", "provider": "telecmi",
           "status": "completed", "duration_seconds": 252, "outcome": "no_answer",
           "evaluation": _evaluation(), "ai_status": "done", "flag_status": None, "score_status": None}

    def test_sim_calls_are_never_scored(self):
        db = _db_with_row({**self.ROW, "provider": "sim_basic"})
        self.assertIsNone(sc.finalize_call_score(db, "c1"))
        db.table.return_value.update.assert_not_called()

    def test_flag_is_opened_and_both_sides_notified(self):
        db = _db_with_row(dict(self.ROW))
        with patch.object(sc, "_notify_flag") as notify:
            sc.finalize_call_score(db, "c1")
        update = db.table.return_value.update.call_args.args[0]
        self.assertEqual(update["flag_status"], "open")
        self.assertEqual(update["flag_reason"], "Marked No answer, but the customer spoke for 4m 12s.")
        self.assertEqual(update["score_status"], "scored")
        notify.assert_called_once()

    def test_plain_scoring_writes_no_flag(self):
        db = _db_with_row({**self.ROW, "outcome": "interested"})
        with patch.object(sc, "_notify_flag") as notify:
            sc.finalize_call_score(db, "c1")
        update = db.table.return_value.update.call_args.args[0]
        self.assertNotIn("flag_status", update)
        self.assertEqual(update["score"], 8.3)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
