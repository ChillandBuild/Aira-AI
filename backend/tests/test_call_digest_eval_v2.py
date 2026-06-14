"""
Tests for call_digest evaluation v2 aggregation.
No real Groq/Supabase calls — groq, app.config, app.db.supabase are stubbed.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

mock_settings = MagicMock()
mock_settings.groq_api_key = None  # disables module-level _client

with patch.dict("sys.modules", {
    "groq": MagicMock(),
    "app.config": MagicMock(settings=mock_settings),
    "app.db.supabase": MagicMock(get_supabase=MagicMock()),
}):
    from app.services import call_digest


class AggregateEvaluationsTests(unittest.TestCase):
    def test_aggregates_criteria_and_flags_mismatches(self):
        rows = [
            {"evaluation": {"greeting_quality": 8, "objection_handling": 4, "outcome_match": True}},
            {"evaluation": {"greeting_quality": 6, "objection_handling": 2, "outcome_match": False}},
            {"evaluation": None},
            {},
        ]
        result = call_digest._aggregate_evaluations(rows)
        self.assertEqual(result["criteria_avg"]["greeting_quality"], 7.0)
        self.assertEqual(result["criteria_avg"]["objection_handling"], 3.0)
        self.assertEqual(result["weakest_criterion"], "objection_handling")
        self.assertEqual(result["outcome_mismatches"], 1)

    def test_no_evaluations_returns_empty_aggregate(self):
        result = call_digest._aggregate_evaluations([{}, {"evaluation": None}])
        self.assertEqual(result["criteria_avg"], {})
        self.assertIsNone(result["weakest_criterion"])
        self.assertEqual(result["outcome_mismatches"], 0)

    def test_v1_shaped_rows_do_not_crash_and_contribute_nothing(self):
        rows = [
            {"evaluation": {"objection_handling": "good", "outcome_clarity": "yes", "overall_score": 8}},
            {"evaluation": {"greeting_quality": 7}},
        ]
        result = call_digest._aggregate_evaluations(rows)
        self.assertEqual(result["criteria_avg"], {"greeting_quality": 7.0})
        self.assertEqual(result["weakest_criterion"], "greeting_quality")
        self.assertEqual(result["outcome_mismatches"], 0)


class BuildStatsTextTests(unittest.TestCase):
    def test_build_stats_text_includes_weakest_criterion(self):
        stats = {
            "total_calls": 5, "converted": 1, "callbacks": 1, "not_interested": 2, "no_answer": 1,
            "avg_duration_seconds": 120, "avg_score": 6.5,
            "criteria_avg": {"objection_handling": 4.2, "greeting_quality": 8.0},
            "weakest_criterion": "objection_handling",
            "outcome_mismatches": 1,
        }
        text = call_digest._build_stats_text(stats)
        self.assertIn("Weakest area today: objection_handling (avg 4.2/10)", text)

    def test_build_stats_text_without_weakest_criterion(self):
        stats = {
            "total_calls": 0, "converted": 0, "callbacks": 0, "not_interested": 0, "no_answer": 0,
            "avg_duration_seconds": 0, "avg_score": None,
            "criteria_avg": {}, "weakest_criterion": None, "outcome_mismatches": 0,
        }
        text = call_digest._build_stats_text(stats)
        self.assertNotIn("Weakest area", text)


if __name__ == "__main__":
    unittest.main()
