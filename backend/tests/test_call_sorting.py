"""Step 1: the system, not the AI, decides the group by counting quote-backed signs."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_sorting as cs
from app.services.call_lines import Line

# The method document's Example 2 (real conversation, ~95 seconds).
REAL = [
    Line(2, "customer", "I need billing software for two shops."),
    Line(8, "telecaller", "Our plan includes GST billing and stock tracking."),
    Line(15, "customer", "How much?"),
    Line(40, "customer", "A bit costly, I'll think."),
    Line(60, "telecaller", "I'll send a demo link and call Friday at 11."),
]
# Example 1 (early exit, ~2 minutes).
EARLY = [
    Line(1, "telecaller", "Calling about your enquiry."),
    Line(4, "customer", "Who is this? Where did you get my number?"),
    Line(9, "customer", "I never enquired, don't call."),
]


def _ai(signs, **extra):
    base = {
        "summary": {"brief": "b", "next_action": "n"},
        "signs": signs,
        "polite": True, "rude_quote": None,
        "enquiry_confirmed_early": True, "expected_crm": "not_enquired",
        "language_barrier": False, "language_barrier_quote": None,
    }
    base.update(extra)
    return base


class ValidateSignsTests(unittest.TestCase):
    def test_all_six_signs_on_document_example(self):
        raw = [
            {"sign": 1, "quote": "I need billing software for two shops"},
            {"sign": 2, "quote": "Our plan includes GST billing"},
            {"sign": 3, "quote": "How much?"},
            {"sign": 4, "quote": "How much?"},
            {"sign": 5, "quote": "A bit costly, I'll think"},
            {"sign": 6, "quote": "I'll send a demo link and call Friday at 11"},
        ]
        valid = cs.validate_signs(raw, REAL)
        self.assertEqual([s["sign"] for s in valid], [1, 2, 3, 4, 5, 6])
        self.assertEqual(valid[0]["time"], "00:02")
        self.assertEqual(valid[1]["speaker"], "telecaller")

    def test_sign_from_wrong_speaker_is_dropped(self):
        # sign 1 (need) must come from the customer
        self.assertEqual(cs.validate_signs([{"sign": 1, "quote": "Our plan includes GST billing"}], REAL), [])

    def test_made_up_quote_is_dropped(self):
        self.assertEqual(cs.validate_signs([{"sign": 3, "quote": "It costs 999 per month"}], REAL), [])

    def test_duplicate_sign_counted_once(self):
        raw = [{"sign": 3, "quote": "How much?"}, {"sign": 3, "quote": "How much?"}]
        self.assertEqual(len(cs.validate_signs(raw, REAL)), 1)

    def test_garbage_entries_ignored(self):
        self.assertEqual(cs.validate_signs([{"sign": 9, "quote": "How much?"}, "x", {"quote": "How much?"}], REAL), [])

    def test_group_threshold(self):
        self.assertEqual(cs.group_for(0), "early_exit")
        self.assertEqual(cs.group_for(1), "early_exit")
        self.assertEqual(cs.group_for(2), "real_conversation")


class SortCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_claiming_signs_without_proof_is_early_exit(self):
        ai = _ai([{"sign": 1, "quote": "I want your product"}, {"sign": 3, "quote": "What's the price"}])
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertEqual(result.group, "early_exit")
        self.assertEqual(result.early_exit_check["expected_crm"], "not_enquired")
        self.assertIsNone(result.early_exit_check["crm_matches"])

    async def test_real_conversation_has_no_early_exit_check(self):
        ai = _ai([{"sign": 3, "quote": "How much?"}, {"sign": 5, "quote": "A bit costly"}])
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)) as gem:
            result = await cs.sort_call(REAL, tenant_id="t")
        self.assertEqual(result.group, "real_conversation")
        self.assertIsNone(result.early_exit_check)
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)
        self.assertIn("[00:15] Customer: How much?", gem.call_args.kwargs["user_prompt"])

    async def test_rude_quote_must_be_telecallers(self):
        ai = _ai([], polite=False, rude_quote="Who is this?")  # customer's line, not the telecaller's
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertTrue(result.early_exit_check["polite"])
        self.assertIsNone(result.rude_quote)

    async def test_unknown_expected_crm_becomes_other(self):
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=_ai([], expected_crm="banana"))):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertEqual(result.early_exit_check["expected_crm"], "other")

    async def test_malformed_ai_json_degrades(self):
        ai = _ai(
            [{"sign": 1, "quote": 12345}, "junk"],
            summary="not a dict",
            polite=False,
            rude_quote=12345,
            language_barrier=True,
            language_barrier_quote=["x"]
        )
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertEqual(result.group, "early_exit")
        self.assertEqual(result.summary, {})
        self.assertIsNone(result.rude_quote)
        self.assertFalse(result.language_barrier)


if __name__ == "__main__":
    unittest.main()
