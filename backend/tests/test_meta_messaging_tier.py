"""Meta's messaging-limit enums map to real daily limits.

Regression: the old map keyed TIER_1000/TIER_10000/TIER_100000 -- values Meta
never sends -- so every sync left the tier at the 1,000 DB default even when
Meta's portfolio limit was TIER_2K. Quality had the same shape of bug on the
single-number sync (HIGH/MEDIUM/LOW keys vs Meta's GREEN/YELLOW/RED)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.number_health import map_quality
from app.services.meta_cloud import UNLIMITED_MESSAGING_TIER, parse_messaging_tier, tier_from_meta


class TierFromMetaTests(unittest.TestCase):
    def test_every_meta_enum_maps(self):
        self.assertEqual(tier_from_meta("TIER_50"), 50)
        self.assertEqual(tier_from_meta("TIER_250"), 250)
        self.assertEqual(tier_from_meta("TIER_1K"), 1000)
        self.assertEqual(tier_from_meta("TIER_2K"), 2000)
        self.assertEqual(tier_from_meta("TIER_10K"), 10000)
        self.assertEqual(tier_from_meta("TIER_100K"), 100000)
        self.assertEqual(tier_from_meta("TIER_UNLIMITED"), UNLIMITED_MESSAGING_TIER)

    def test_unknown_or_missing_is_none_not_zero(self):
        self.assertIsNone(tier_from_meta("TIER_1000"))
        self.assertIsNone(tier_from_meta(""))
        self.assertIsNone(tier_from_meta(None))

    def test_portfolio_limit_wins_over_deprecated_field(self):
        # Live shape from Meta on 2026-10-15 for a verified portfolio.
        meta = {"whatsapp_business_manager_messaging_limit": "TIER_2K", "messaging_limit_tier": "TIER_250"}
        self.assertEqual(parse_messaging_tier(meta), 2000)

    def test_never_falls_back_to_the_deprecated_field(self):
        """Meta deprecated messaging_limit_tier; it can be stale (90427 81088
        reported TIER_250 beside a TIER_2K portfolio), so it's not read."""
        self.assertIsNone(parse_messaging_tier({"messaging_limit_tier": "TIER_10K"}))
        self.assertIsNone(parse_messaging_tier({}))


class CapabilityUpdateTests(unittest.TestCase):
    """Meta's webhook docs show max_daily_conversations_per_business both as
    TIER_* and as a plain number."""

    def test_tier_string_and_plain_number_both_parse(self):
        from app.services.meta_cloud import tier_from_capability_update as t
        self.assertEqual(t({"max_daily_conversations_per_business": "TIER_10K"}), 10000)
        self.assertEqual(t({"max_daily_conversations_per_business": 2000}), 2000)
        self.assertEqual(t({"max_daily_conversations_per_business": "TIER_UNLIMITED"}), UNLIMITED_MESSAGING_TIER)
        self.assertEqual(t({"max_daily_conversations_per_business": -1}), UNLIMITED_MESSAGING_TIER)

    def test_deprecated_keys_are_ignored(self):
        from app.services.meta_cloud import tier_from_capability_update as t
        self.assertIsNone(t({"max_daily_conversation_per_phone": 2000}))
        self.assertIsNone(t({"current_limit": "TIER_10K"}))
        self.assertIsNone(t({"max_daily_conversations_per_business": 1234}))


class QualityMapTests(unittest.TestCase):
    def test_graph_api_colours_map(self):
        self.assertEqual(map_quality("RED"), "red")
        self.assertEqual(map_quality("YELLOW"), "yellow")
        self.assertEqual(map_quality("GREEN"), "green")
        # No rating yet is stored as None, never guessed.
        self.assertIsNone(map_quality("UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
