"""Group + score status for every TeleCMI call; the score is only ever the sum of the checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_marking import CHECKS, check_marks
from app.services.call_scorer import compute_call_score


def _eval(group="real_conversation", crm="excellent"):
    if group == "early_exit":
        return {"evaluation_version": 4, "group": "early_exit", "early_exit_check": {}}
    levels = {"opening": "excellent", "courtesy": "good", "questions": "good", "listening": "partial",
              "product_info": "good", "doubts": "excellent", "clarity": "good", "next_step": "excellent",
              "decision": "partial", "crm_update": crm}
    return {"evaluation_version": 4, "group": group,
            "checks": [{"key": c["key"], "level": levels[c["key"]], "marks": check_marks(c["key"], levels[c["key"]])} for c in CHECKS]}


def _score(**kw):
    args = {"status": "completed", "duration": 480, "ai_status": "done", "evaluation": _eval()}
    args.update(kw)
    return compute_call_score(**args)


class ComputeTests(unittest.TestCase):
    def test_not_connected(self):
        for status, duration in (("no_answer", 0), ("missed", 0), ("failed", 0), ("completed", 0)):
            r = _score(status=status, duration=duration, ai_status=None, evaluation=None)
            self.assertEqual((r["call_group"], r["score_status"], r["score"]), ("not_connected", "not_connected", None))

    def test_very_short_under_30s(self):
        r = _score(duration=29, ai_status=None, evaluation=None)
        self.assertEqual((r["call_group"], r["score_status"], r["score_final"]), ("very_short", "very_short", True))

    def test_in_progress_call(self):
        self.assertEqual(_score(status="initiated")["score_status"], "processing")

    def test_processing_and_failed(self):
        self.assertEqual(_score(ai_status="transcribing", evaluation=None)["score_status"], "processing")
        self.assertEqual(_score(ai_status="failed", evaluation=None)["score_status"], "failed")

    def test_old_v3_evaluation_is_processing_not_scored(self):
        self.assertEqual(_score(evaluation={"evaluation_version": 3})["score_status"], "processing")

    def test_early_exit_has_no_score(self):
        r = _score(evaluation=_eval("early_exit"))
        self.assertEqual((r["call_group"], r["score_status"], r["score"], r["score_final"]), ("early_exit", "early_exit", None, True))

    def test_real_conversation_full_score(self):
        r = _score()
        self.assertEqual((r["call_group"], r["score_status"], r["score"], r["score_final"]), ("real_conversation", "scored", 78.5, True))

    def test_pending_crm_is_provisional(self):
        r = _score(evaluation=_eval(crm=None))
        self.assertEqual((r["score_status"], r["score"], r["score_final"]), ("provisional", 71.5, False))


if __name__ == "__main__":
    unittest.main()
