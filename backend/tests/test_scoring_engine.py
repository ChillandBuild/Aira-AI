"""
Tests for Score Engine v2 pure functions.
No DB, no Groq — only deterministic logic.
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub out Groq and settings before importing the module
mock_settings = MagicMock()
mock_settings.groq_api_key = None  # disables _client so no real calls
with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
    # Also stub segmentation import
    import importlib
    import types

    seg_mod = types.ModuleType("app.services.segmentation")
    def _score_to_segment(score, thresholds=None):
        t = thresholds or {"A": 9, "B": 7, "C": 5}
        if score >= t.get("A", 9): return "A"
        if score >= t.get("B", 7): return "B"
        if score >= t.get("C", 5): return "C"
        return "D"
    seg_mod.score_to_segment = _score_to_segment
    seg_mod.parse_thresholds = lambda raw: None
    sys.modules["app.services.segmentation"] = seg_mod
    sys.modules["app.config"] = MagicMock(settings=mock_settings)
    sys.modules["groq"] = MagicMock()

    # Now safe to import
    from app.services.scoring_engine import (
        _compute_intent_delta,
        _compute_decay,
        _apply_segment_lock,
        _should_score_arc,
        _REJECTION_SENTINEL,
    )


class TestIntentDelta(unittest.TestCase):

    # ── Rejection phrases ─────────────────────────────────────────────────
    def test_english_not_interested_returns_rejection(self):
        delta, reason = _compute_intent_delta("not interested", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)
        self.assertEqual(reason, "rejection")

    def test_english_stop_returns_rejection(self):
        delta, reason = _compute_intent_delta("please stop messaging me", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tamil_rejection_returns_rejection(self):
        delta, reason = _compute_intent_delta("வேண்டாம்", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hindi_rejection_returns_rejection(self):
        delta, reason = _compute_intent_delta("नहीं चाहिए", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    # ── High intent keywords ──────────────────────────────────────────────
    def test_book_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("I want to book the homam", "idle")
        self.assertGreater(delta, 0)
        self.assertIn("high_intent", reason)

    def test_price_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("what is the price?", "idle")
        self.assertGreater(delta, 0)

    def test_tamil_booking_keyword(self):
        delta, reason = _compute_intent_delta("விலை என்ன?", "idle")
        self.assertGreater(delta, 0)

    def test_payment_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("how do I make the payment?", "idle")
        self.assertGreater(delta, 0)

    # ── Detailed message ──────────────────────────────────────────────────
    def test_long_message_adds_delta(self):
        long_msg = "I am very interested in your services and would like to know more about the process and what is involved in the booking"
        delta_long, _ = _compute_intent_delta(long_msg, "idle")
        delta_short, _ = _compute_intent_delta("ok", "idle")
        self.assertGreater(delta_long, delta_short)

    # ── Neutral messages ──────────────────────────────────────────────────
    def test_ok_in_idle_is_neutral(self):
        delta, reason = _compute_intent_delta("ok", "idle")
        self.assertEqual(delta, 0)
        self.assertEqual(reason, "neutral")

    def test_thanks_in_idle_is_neutral(self):
        delta, reason = _compute_intent_delta("thanks", "idle")
        self.assertEqual(delta, 0)

    # ── Delta clamping ────────────────────────────────────────────────────
    def test_delta_never_exceeds_3(self):
        # booking + info + long message all fire at once
        delta, _ = _compute_intent_delta(
            "I want to book homam. My name is Rajan and my gotram is Bharadwaj, please let me know the price and payment details now",
            "idle"
        )
        self.assertLessEqual(delta, 3)

    def test_delta_never_below_minus3_for_non_rejection(self):
        delta, _ = _compute_intent_delta("hi", "idle")
        self.assertGreaterEqual(delta, -3)


class TestDecay(unittest.TestCase):

    def _hours_ago(self, hours: float) -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=hours)

    def test_within_1_hour_is_plus3(self):
        self.assertEqual(_compute_decay(self._hours_ago(0.5)), 3)

    def test_6_hours_ago_is_plus1(self):
        self.assertEqual(_compute_decay(self._hours_ago(6)), 1)

    def test_18_hours_ago_is_zero(self):
        self.assertEqual(_compute_decay(self._hours_ago(18)), 0)

    def test_2_days_silent_is_minus1(self):
        self.assertEqual(_compute_decay(self._hours_ago(48)), -1)

    def test_5_days_silent_is_minus2(self):
        self.assertEqual(_compute_decay(self._hours_ago(120)), -2)

    def test_10_days_silent_is_minus3(self):
        self.assertEqual(_compute_decay(self._hours_ago(240)), -3)

    def test_45_days_silent_is_minus4(self):
        self.assertEqual(_compute_decay(self._hours_ago(1080)), -4)

    def test_none_last_inbound_is_zero(self):
        self.assertEqual(_compute_decay(None), 0)

    def test_naive_datetime_handled(self):
        naive = datetime.now() - timedelta(days=10)
        result = _compute_decay(naive)
        self.assertEqual(result, -3)


class TestSegmentLock(unittest.TestCase):

    # ── Upgrades always immediate ─────────────────────────────────────────
    def test_upgrade_c_to_b_is_immediate(self):
        seg, count = _apply_segment_lock("B", "C", 0, False)
        self.assertEqual(seg, "B")
        self.assertEqual(count, 0)

    def test_upgrade_b_to_a_is_immediate(self):
        seg, count = _apply_segment_lock("A", "B", 1, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)

    def test_upgrade_d_to_a_is_immediate(self):
        seg, count = _apply_segment_lock("A", "D", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)

    # ── Small drop: needs 2 consecutive ──────────────────────────────────
    def test_first_small_drop_holds_segment(self):
        seg, count = _apply_segment_lock("B", "A", 0, False)
        self.assertEqual(seg, "A")   # held
        self.assertEqual(count, 1)

    def test_second_small_drop_allows_downgrade(self):
        seg, count = _apply_segment_lock("B", "A", 1, False)
        self.assertEqual(seg, "B")   # confirmed drop
        self.assertEqual(count, 0)

    def test_first_small_drop_c_to_b(self):
        seg, count = _apply_segment_lock("C", "B", 0, False)
        self.assertEqual(seg, "B")   # held
        self.assertEqual(count, 1)

    # ── Big drop: always immediate ────────────────────────────────────────
    def test_a_to_d_big_drop_is_immediate(self):
        seg, count = _apply_segment_lock("D", "A", 0, True)
        self.assertEqual(seg, "D")
        self.assertEqual(count, 0)

    def test_big_drop_2_segments_immediate(self):
        # A→C is a 2-segment drop (even without big_drop flag, diff >= 2)
        seg, count = _apply_segment_lock("C", "A", 0, False)
        self.assertEqual(seg, "C")
        self.assertEqual(count, 0)

    # ── Same segment resets counter ───────────────────────────────────────
    def test_same_segment_resets_drop_count(self):
        seg, count = _apply_segment_lock("A", "A", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)


class TestShouldScoreArc(unittest.TestCase):

    def test_first_message_always_scores(self):
        self.assertTrue(_should_score_arc(1, "neutral"))

    def test_third_message_scores(self):
        self.assertTrue(_should_score_arc(3, "neutral"))

    def test_sixth_message_scores(self):
        self.assertTrue(_should_score_arc(6, "neutral"))

    def test_second_message_does_not_score(self):
        self.assertFalse(_should_score_arc(2, "neutral"))

    def test_fourth_message_does_not_score(self):
        self.assertFalse(_should_score_arc(4, "neutral"))

    def test_high_intent_on_second_message_scores(self):
        self.assertTrue(_should_score_arc(2, "high_intent"))

    def test_neutral_on_non_multiple_does_not_score(self):
        self.assertFalse(_should_score_arc(5, "neutral"))


class TestCompositeScoreLogic(unittest.TestCase):
    """Verify composite arithmetic stays correct and clamped."""

    def _composite(self, arc, intent, engagement, decay):
        return max(1, min(10, arc + intent + engagement + decay))

    def test_hot_lead_ok_message_stays_high(self):
        # arc=8, intent 0, engagement 0, decay 0
        self.assertEqual(self._composite(8, 0, 0, 0), 8)

    def test_hot_lead_does_not_drop_on_ok(self):
        self.assertGreaterEqual(self._composite(8, 0, 0, 0), 7)

    def test_booking_keyword_pushes_above_threshold(self):
        # arc=6, booking keyword +2, engagement 0, decay 0
        self.assertGreaterEqual(self._composite(6, 2, 0, 0), 7)

    def test_decay_drifts_hot_lead(self):
        # arc=9, silent 10 days → decay -3 → 6 (Segment C)
        self.assertEqual(self._composite(9, 0, 0, -3), 6)

    def test_recency_boosts_score(self):
        # arc=6, intent 0, engagement +1, replied within 1 hour → decay +3
        self.assertEqual(self._composite(6, 0, 1, 3), 10)

    def test_engagement_lifts_warm_to_hot(self):
        # arc=7 (Warm), engagement +2 boosts to 9 (Hot)
        self.assertEqual(self._composite(7, 0, 2, 0), 9)

    def test_score_clamped_at_10(self):
        self.assertEqual(self._composite(9, 2, 2, 3), 10)

    def test_score_clamped_at_1(self):
        self.assertEqual(self._composite(1, -3, 0, -4), 1)

    def test_rejection_overrides_everything(self):
        delta, reason = _compute_intent_delta("not interested at all", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_high_intent_stale_lead(self):
        # arc=9 (high intent), but 30+ days stale → decay -4, engagement 0
        self.assertEqual(self._composite(9, 0, 0, -4), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
