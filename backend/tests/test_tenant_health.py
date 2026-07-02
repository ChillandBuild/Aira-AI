"""
Tests for `compute_fleet_health` and `has_required_tokens`, the pure scoring
functions behind `_build_fleet_rows` — the shared per-tenant health signal
builder used by `GET /api/v1/operator/alerts` (the Fleet page that used to
also consume this was removed; the scoring logic it shared with Alerts stays).

Contract under test: health is derived purely from the signals passed in --
no DB access -- so every tier/branch can be exercised directly.
"""
import sys
import unittest
from pathlib import Path

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes.operator import compute_fleet_health, has_required_tokens


class ComputeFleetHealthTests(unittest.TestCase):
    def test_healthy_when_no_signals_fire(self):
        health = compute_fleet_health(
            ai_usage=10, near_cap=False, no_activity_14d=False
        )
        self.assertEqual(health, "healthy")

    def test_warning_when_near_cap(self):
        health = compute_fleet_health(
            ai_usage=85, near_cap=True, no_activity_14d=False
        )
        self.assertEqual(health, "warning")

    def test_warning_when_no_activity_14d(self):
        health = compute_fleet_health(
            ai_usage=5, near_cap=False, no_activity_14d=True
        )
        self.assertEqual(health, "warning")

    def test_critical_when_ai_usage_at_or_over_100(self):
        self.assertEqual(
            compute_fleet_health(ai_usage=100, near_cap=True, no_activity_14d=False),
            "critical",
        )
        self.assertEqual(
            compute_fleet_health(ai_usage=140, near_cap=True, no_activity_14d=False),
            "critical",
        )

    def test_critical_when_token_expired_even_with_low_usage(self):
        health = compute_fleet_health(
            ai_usage=0,
            near_cap=False,
            no_activity_14d=False,
            token_expired=True,
        )
        self.assertEqual(health, "critical")

    def test_critical_when_channel_unhealthy_even_with_low_usage(self):
        health = compute_fleet_health(
            ai_usage=0,
            near_cap=False,
            no_activity_14d=False,
            channel_unhealthy=True,
        )
        self.assertEqual(health, "critical")

    def test_critical_takes_priority_over_warning_signals(self):
        health = compute_fleet_health(
            ai_usage=100,
            near_cap=True,
            no_activity_14d=True,
            token_expired=True,
            channel_unhealthy=True,
        )
        self.assertEqual(health, "critical")

    def test_defaults_for_token_expired_and_channel_unhealthy_are_false(self):
        # Omitting the keyword-only deferred signals must not force critical.
        health = compute_fleet_health(ai_usage=50, near_cap=False, no_activity_14d=False)
        self.assertEqual(health, "healthy")


class HasRequiredTokensTests(unittest.TestCase):
    """Per-channel token presence, pure and DB-free. B3: telegram-only tenants
    must be checked against telegram_bot_token, not meta_access_token."""

    def test_telegram_only_tenant_with_telegram_token_is_satisfied(self):
        # This is the false-critical regression: a telegram-only tenant with a
        # valid bot token must NOT be flagged as missing tokens.
        self.assertTrue(
            has_required_tokens({"telegram"}, {"telegram_bot_token": True})
        )

    def test_telegram_only_tenant_without_telegram_token_is_missing(self):
        self.assertFalse(
            has_required_tokens({"telegram"}, {"meta_access_token": True})
        )

    def test_telegram_only_tenant_with_no_settings_is_missing(self):
        self.assertFalse(has_required_tokens({"telegram"}, {}))

    def test_whatsapp_tenant_with_meta_token_is_satisfied(self):
        self.assertTrue(
            has_required_tokens({"whatsapp"}, {"meta_access_token": True})
        )

    def test_whatsapp_tenant_without_meta_token_is_missing(self):
        self.assertFalse(has_required_tokens({"whatsapp"}, {}))

    def test_instagram_and_facebook_also_satisfied_by_meta_token(self):
        self.assertTrue(
            has_required_tokens({"instagram"}, {"meta_access_token": True})
        )
        self.assertTrue(
            has_required_tokens({"facebook"}, {"meta_access_token": True})
        )

    def test_multi_channel_tenant_needs_both_tokens(self):
        # whatsapp + telegram enabled: meta token alone is not enough.
        self.assertFalse(
            has_required_tokens(
                {"whatsapp", "telegram"}, {"meta_access_token": True}
            )
        )
        self.assertTrue(
            has_required_tokens(
                {"whatsapp", "telegram"},
                {"meta_access_token": True, "telegram_bot_token": True},
            )
        )

    def test_non_messaging_channel_ignored(self):
        # telecalling doesn't require either token.
        self.assertTrue(has_required_tokens({"telecalling"}, {}))

    def test_no_enabled_channels_is_satisfied(self):
        self.assertTrue(has_required_tokens(set(), {}))


if __name__ == "__main__":
    unittest.main()
