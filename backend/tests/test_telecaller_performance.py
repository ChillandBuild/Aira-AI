"""Total calls, average score and the 70/30 daily/monthly winner."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import telecaller_performance as tp


def _rows(scored=(), short=0, no_answer=0, pending=0):
    rows = [{"score_status": "scored", "score": s, "evaluation": {"criteria": ["tone"], "tone": 7}} for s in scored]
    rows += [{"score_status": "short_call", "score": None}] * short
    rows += [{"score_status": "no_answer", "score": None}] * no_answer
    rows += [{"score_status": "awaiting_outcome", "score": None}] * pending
    return rows


class SummaryTests(unittest.TestCase):
    def test_every_call_counts_toward_total_but_only_scored_ones_average(self):
        """The plan's example: 5 scored + 10 no answer + 5 short = 20 total calls."""
        summary = tp.summarize_calls(_rows(scored=[8, 9, 7, 8, 8], no_answer=10, short=5))
        self.assertEqual(summary["total_calls"], 20)
        self.assertEqual(summary["scored_calls"], 5)
        self.assertEqual(summary["avg_score"], 8.0)
        self.assertEqual(summary["breakdown"], {"scored": 5, "short_call": 5, "no_answer": 10, "not_scored": 0})
        self.assertEqual(summary["criteria_avg"], {"tone": 7.0})
        self.assertEqual(summary["weakest_criterion"], "tone")

    def test_no_scored_calls_means_no_average(self):
        self.assertIsNone(tp.summarize_calls(_rows(short=3, pending=2))["avg_score"])


class WinnerTests(unittest.TestCase):
    def _stats(self, spec):
        return {cid: {"total_calls": total, "scored_calls": scored, "avg_score": avg} for cid, (avg, total, scored) in spec.items()}

    def test_plan_example_the_busy_good_telecaller_wins(self):
        winner = tp.rank_winner(self._stats({"A": (8.0, 40, 10), "B": (9.0, 10, 5), "C": (6.5, 35, 9)}), 3)
        self.assertEqual(winner["caller_id"], "A")
        self.assertEqual(winner["points"], 8.6)
        self.assertEqual(winner["volume_points"], 10.0)

    def test_minimum_scored_calls_is_enforced(self):
        self.assertIsNone(tp.rank_winner(self._stats({"A": (9.0, 30, 2)}), 3))

    def test_volume_is_relative_to_the_busiest_telecaller_even_if_they_dont_qualify(self):
        winner = tp.rank_winner(self._stats({"A": (8.0, 20, 5), "busy": (5.0, 40, 1)}), 3)
        self.assertEqual(winner["points"], round(0.7 * 8.0 + 0.3 * 5.0, 2))

    def test_ties_go_to_more_calls(self):
        """A: 0.7*8.3 + 0.3*(10/12*10) = 8.31; B: 0.7*7.8 + 0.3*10 = 8.46 -> B. Equal points -> more calls."""
        tied = tp.rank_winner({"A": {"total_calls": 10, "scored_calls": 5, "avg_score": 8.3},
                               "B": {"total_calls": 12, "scored_calls": 5, "avg_score": 7.8}}, 3)
        self.assertEqual(tied["caller_id"], "B")
        equal = tp.rank_winner({"A": {"total_calls": 12, "scored_calls": 5, "avg_score": 8.0},
                                "B": {"total_calls": 12, "scored_calls": 5, "avg_score": 8.0},
                                "C": {"total_calls": 6, "scored_calls": 5, "avg_score": 10.0}}, 3)
        self.assertEqual(equal["points"], 8.6)
        self.assertIn(equal["caller_id"], {"A", "B"})

    def test_nobody_scored(self):
        self.assertIsNone(tp.rank_winner({}, 3))


class IstBoundsTests(unittest.TestCase):
    def test_day_starts_at_ist_midnight(self):
        start, end = tp.ist_day_bounds(datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(start, "2026-09-24T18:30:00+00:00")
        self.assertEqual(end, "2026-09-25T18:30:00+00:00")

    def test_2am_ist_belongs_to_the_new_day(self):
        start, _ = tp.ist_day_bounds(datetime(2026, 9, 24, 20, 30, tzinfo=timezone.utc))
        self.assertEqual(start, "2026-09-24T18:30:00+00:00")

    def test_month_bounds_including_december(self):
        self.assertEqual(tp.ist_month_bounds(datetime(2026, 9, 10, tzinfo=timezone.utc)),
                         ("2026-08-31T18:30:00+00:00", "2026-09-30T18:30:00+00:00"))
        self.assertEqual(tp.ist_month_bounds(datetime(2026, 12, 15, tzinfo=timezone.utc))[1], "2026-12-31T18:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
