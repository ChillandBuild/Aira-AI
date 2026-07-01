"""
Tests for `compute_fleet_health`, the pure scoring function behind the operator
Fleet Cockpit's attention queue (GET /api/v1/operator/fleet).

Contract under test: health is derived purely from the signals passed in —
no DB access — so every tier/branch can be exercised directly.
"""
import sys
import unittest
from pathlib import Path

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes.operator import compute_fleet_health


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


if __name__ == "__main__":
    unittest.main()
