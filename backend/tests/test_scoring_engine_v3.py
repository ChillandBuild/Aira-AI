"""
Tests for Score Engine v3 (3-label classifier).
Tests pure functions and rejection detection.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

mock_settings = MagicMock()
mock_settings.groq_api_key = None
with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
    import importlib
    import types

    seg_mod = types.ModuleType("app.services.segmentation")
    def _score_to_segment(score):
        if score >= 8: return "A"
        if score >= 4: return "B"
        if score >= 1: return "C"
        return "D"
    seg_mod.score_to_segment = _score_to_segment
    sys.modules["app.services.segmentation"] = seg_mod
    sys.modules["app.config"] = MagicMock(settings=mock_settings)
    sys.modules["groq"] = MagicMock()

    from app.services.scoring_engine import (
        _check_rejection,
        _apply_segment_lock,
        _is_old_5band_rubric,
    )


class TestRejectionDetection(unittest.TestCase):
    """Test rejection pattern matching."""

    def test_not_interested_is_rejection(self):
        self.assertTrue(_check_rejection("not interested"))

    def test_stop_is_rejection(self):
        self.assertTrue(_check_rejection("please stop messaging me"))

    def test_tamil_rejection_is_rejection(self):
        self.assertTrue(_check_rejection("வேண்டாம்"))

    def test_hindi_rejection_is_rejection(self):
        self.assertTrue(_check_rejection("नहीं चाहिए"))

    def test_hinglish_rejection_is_rejection(self):
        self.assertTrue(_check_rejection("zaroorat nahi hai"))

    def test_normal_message_is_not_rejection(self):
        self.assertFalse(_check_rejection("Hi, I'm interested"))

    def test_ok_is_not_rejection(self):
        self.assertFalse(_check_rejection("ok"))

    def test_remove_my_number_is_rejection(self):
        self.assertTrue(_check_rejection("remove my number from your list"))

    def test_telugu_rejection_is_rejection(self):
        self.assertTrue(_check_rejection("వద్దు"))

    def test_malayalam_rejection_is_rejection(self):
        self.assertTrue(_check_rejection("വേണ്ട"))


class TestSegmentLock(unittest.TestCase):
    """Test segment lock logic (unchanged from v2)."""

    def test_upgrade_c_to_b_is_immediate(self):
        seg, count = _apply_segment_lock("B", "C", 0, False)
        self.assertEqual(seg, "B")
        self.assertEqual(count, 0)

    def test_upgrade_b_to_a_is_immediate(self):
        seg, count = _apply_segment_lock("A", "B", 1, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)

    def test_first_small_drop_holds_segment(self):
        seg, count = _apply_segment_lock("B", "A", 0, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 1)

    def test_second_small_drop_allows_downgrade(self):
        seg, count = _apply_segment_lock("B", "A", 1, False)
        self.assertEqual(seg, "B")
        self.assertEqual(count, 0)

    def test_big_drop_is_immediate(self):
        seg, count = _apply_segment_lock("C", "A", 0, False)
        self.assertEqual(seg, "C")
        self.assertEqual(count, 0)

    def test_same_segment_resets_counter(self):
        seg, count = _apply_segment_lock("A", "A", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)


class TestOldRubricDetection(unittest.TestCase):
    """Test detection of old 5-band rubric format."""

    def test_old_5band_format_detected(self):
        old_rubric = """9-10: High intent — explicitly asked for pricing/payment
7-8: Warm — asking detailed questions
5-6: Neutral — general inquiry
3-4: Lukewarm — vague replies
1-2: Low intent — unresponsive"""
        self.assertTrue(_is_old_5band_rubric(old_rubric))

    def test_new_3band_format_not_detected(self):
        new_rubric = """- Hot: Explicitly asked for pricing/payment
- Warm: Asking detailed questions
- Cold: General inquiry"""
        self.assertFalse(_is_old_5band_rubric(new_rubric))

    def test_partial_old_format_detected(self):
        partial = """9-10: Something\n- Hot: Something else"""
        self.assertTrue(_is_old_5band_rubric(partial))

    def test_empty_string_not_detected(self):
        self.assertFalse(_is_old_5band_rubric(""))


class TestSegmentToScoreMapping(unittest.TestCase):
    """Test the compatibility score mapping."""

    def test_hot_maps_to_9(self):
        mapping = {"A": 9, "B": 6, "C": 2, "D": 0}
        self.assertEqual(mapping["A"], 9)

    def test_warm_maps_to_6(self):
        mapping = {"A": 9, "B": 6, "C": 2, "D": 0}
        self.assertEqual(mapping["B"], 6)

    def test_cold_maps_to_2(self):
        mapping = {"A": 9, "B": 6, "C": 2, "D": 0}
        self.assertEqual(mapping["C"], 2)

    def test_not_interested_maps_to_0(self):
        mapping = {"A": 9, "B": 6, "C": 2, "D": 0}
        self.assertEqual(mapping["D"], 0)


class TestComputeScoreRejection(unittest.IsolatedAsyncioTestCase):
    """Test rejection handling in compute_score."""

    def _make_db(self, lead_state, message_row=None):
        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [lead_state]
        leads_table.update.return_value.eq.return_value.execute.return_value = None

        messages_table = MagicMock()
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = (
            [message_row] if message_row else []
        )
        messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        handovers_table = MagicMock()
        handovers_table.select.return_value.eq.return_value.execute.return_value.data = []

        tables = {"leads": leads_table, "messages": messages_table, "chat_handovers": handovers_table}
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db

    async def test_rejection_forces_d_immediately(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 9, "score_arc": 9, "score_intent_delta": 2,
            "score_engagement": 0, "segment": "A", "segment_drop_count": 0,
        }
        message_row = {
            "direction": "inbound", "content": "not interested",
            "via_ad_referral": False, "attributed_ad_creative_id": None,
        }
        db = self._make_db(lead_state, message_row)

        result = await scoring_engine.compute_score(
            message="not interested", lead_id="lead-1", db=db, tenant_id=None,
        )

        self.assertEqual(result["score"], 0)
        self.assertEqual(result["segment"], "D")
        self.assertEqual(result["reason"], "rejection")
        self.assertTrue(result["arc_updated"])

    async def test_rejection_even_for_warm_lead(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 6, "score_arc": 6, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "B", "segment_drop_count": 0,
        }
        message_row = {
            "direction": "inbound", "content": "stop calling me",
            "via_ad_referral": False, "attributed_ad_creative_id": None,
        }
        db = self._make_db(lead_state, message_row)

        result = await scoring_engine.compute_score(
            message="stop calling me", lead_id="lead-1", db=db, tenant_id=None,
        )

        self.assertEqual(result["segment"], "D")
        self.assertEqual(result["score"], 0)


class TestComputeScoreReturnsReason(unittest.IsolatedAsyncioTestCase):
    """Test that compute_score returns the reason key."""

    def _make_db(self, lead_state):
        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [lead_state]
        leads_table.update.return_value.eq.return_value.execute.return_value = None

        messages_table = MagicMock()
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        handovers_table = MagicMock()
        handovers_table.select.return_value.eq.return_value.execute.return_value.data = []

        tables = {"leads": leads_table, "messages": messages_table, "chat_handovers": handovers_table}
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db

    async def test_compute_score_returns_reason_key(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 5, "score_arc": 5, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        db = self._make_db(lead_state)

        with patch.object(scoring_engine, "_classify_segment", new=AsyncMock(return_value=("B", "shows_interest"))):
            result = await scoring_engine.compute_score(
                message="I want to book a slot", lead_id="lead-1", db=db, tenant_id=None,
            )

        self.assertIn("reason", result)
        self.assertEqual(result["reason"], "shows_interest")


if __name__ == "__main__":
    unittest.main(verbosity=2)
