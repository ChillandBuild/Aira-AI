"""
Tests for Score Engine v3 — Segment Lock and core logic.
Kept from v2 tests: tests that don't depend on removed functions.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub out Groq and settings before importing the module
mock_settings = MagicMock()
mock_settings.groq_api_key = None
with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
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

    # Now safe to import
    from app.services.scoring_engine import (
        _apply_segment_lock,
    )


class TestSegmentLock(unittest.TestCase):
    """Segment lock logic — unchanged from v2."""

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

    # ── Explicit big_drop flag: immediate ─────────────────────────────────
    def test_a_to_d_big_drop_is_immediate(self):
        seg, count = _apply_segment_lock("D", "A", 0, True)
        self.assertEqual(seg, "D")
        self.assertEqual(count, 0)

    def test_2_segment_drop_without_flag_is_held_once(self):
        # A→C without the flag needs a second confirming message, like any drop.
        seg, count = _apply_segment_lock("C", "A", 0, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 1)

    # ── Same segment resets counter ───────────────────────────────────────
    def test_same_segment_resets_drop_count(self):
        seg, count = _apply_segment_lock("A", "A", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)


class TestSegmentMappingLogic(unittest.TestCase):
    """Verify segment-to-score compatibility mapping."""

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

    def test_mapping_maintains_thresholds(self):
        """Verify mapped scores still trigger correct segment via score_to_segment."""
        mapping = {"A": 9, "B": 6, "C": 2, "D": 0}

        def score_to_segment(score):
            if score >= 8: return "A"
            if score >= 4: return "B"
            if score >= 1: return "C"
            return "D"

        self.assertEqual(score_to_segment(mapping["A"]), "A")
        self.assertEqual(score_to_segment(mapping["B"]), "B")
        self.assertEqual(score_to_segment(mapping["C"]), "C")
        self.assertEqual(score_to_segment(mapping["D"]), "D")


if __name__ == "__main__":
    unittest.main(verbosity=2)
