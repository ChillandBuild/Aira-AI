"""
Tests for call evaluation v2 — derivation helpers and analyze_call wiring.
No real Groq/Supabase calls — groq and app.config are stubbed.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

mock_settings = MagicMock()
mock_settings.groq_api_key = None  # disables module-level _client

with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
    from app.services import call_summarizer


class QualityLabelTests(unittest.TestCase):
    def test_quality_label_thresholds(self):
        self.assertEqual(call_summarizer._quality_label(9.5), "Excellent")
        self.assertEqual(call_summarizer._quality_label(9.0), "Excellent")
        self.assertEqual(call_summarizer._quality_label(8.9), "Good")
        self.assertEqual(call_summarizer._quality_label(7.0), "Good")
        self.assertEqual(call_summarizer._quality_label(6.9), "Average")
        self.assertEqual(call_summarizer._quality_label(5.0), "Average")
        self.assertEqual(call_summarizer._quality_label(4.9), "Bad")
        self.assertEqual(call_summarizer._quality_label(1.0), "Bad")


class FinalizeEvaluationTests(unittest.TestCase):
    def test_finalize_evaluation_computes_overall_and_label(self):
        evaluation = {
            "greeting_quality": 8,
            "communication_clarity": 8,
            "product_knowledge": 8,
            "requirement_understanding": 8,
            "conversation_engagement": 8,
            "objection_handling": 8,
            "professionalism": 8,
            "coaching_tip": "Keep it up",
        }
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertEqual(result["overall_score"], 8.0)
        self.assertEqual(result["quality_label"], "Good")
        self.assertEqual(result["evaluation_version"], 2)

    def test_finalize_evaluation_handles_missing_scores(self):
        evaluation = {"coaching_tip": "no scores returned"}
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertNotIn("overall_score", result)
        self.assertNotIn("quality_label", result)
        self.assertEqual(result["evaluation_version"], 2)

    def test_finalize_evaluation_rounds_to_one_decimal(self):
        evaluation = {
            "greeting_quality": 8,
            "communication_clarity": 7,
            "product_knowledge": 6,
            "requirement_understanding": 8,
            "conversation_engagement": 7,
            "objection_handling": 5,
            "professionalism": 9,
        }
        # mean = 50/7 = 7.142857...
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertEqual(result["overall_score"], 7.1)
        self.assertEqual(result["quality_label"], "Good")


if __name__ == "__main__":
    unittest.main()
