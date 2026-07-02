"""
Tests for `compute_alerts`, the pure aggregation function behind the operator
Alert Center (GET /api/v1/operator/alerts).

Contract under test: alerts are derived purely from already-fetched signal
inputs (fleet rows, scheduler jobs, incidents) — no DB access — so severity
ordering, dedup, and per-signal emission can all be exercised directly.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes.operator import compute_alerts

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def fleet_row(**overrides) -> dict:
    row = {
        "id": "tenant-1",
        "name": "Acme Corp",
        "ai_usage": 10,
        "near_cap": False,
        "no_activity_14d": False,
        "token_expired": False,
        "channel_unhealthy": False,
        "last_activity": None,
    }
    row.update(overrides)
    return row


def job(**overrides) -> dict:
    j = {
        "id": "scheduled-broadcasts",
        "last_status": "success",
        "last_run": "2026-07-01T11:00:00+00:00",
        "last_error": None,
        "errors_24h": 0,
        "paused": False,
    }
    j.update(overrides)
    return j


class ComputeAlertsTests(unittest.TestCase):
    def test_no_signals_no_alerts(self):
        alerts = compute_alerts(
            fleet_rows=[fleet_row()],
            scheduler_jobs=[job()],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(alerts, [])

    def test_token_expired_emits_critical_fleet_alert(self):
        alerts = compute_alerts(
            fleet_rows=[fleet_row(token_expired=True)],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertEqual(alerts[0]["source"], "fleet")
        self.assertEqual(alerts[0]["tenant_id"], "tenant-1")
        self.assertEqual(alerts[0]["href"], "/operator/client/tenant-1")

    def test_ai_usage_at_or_over_100_emits_critical(self):
        alerts = compute_alerts(
            fleet_rows=[fleet_row(ai_usage=100, near_cap=True)],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertIn("cap", alerts[0]["title"].lower())

    def test_near_cap_emits_warning_not_critical(self):
        alerts = compute_alerts(
            fleet_rows=[fleet_row(ai_usage=85, near_cap=True)],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "warning")

    def test_ai_cap_and_near_cap_are_mutually_exclusive_for_same_tenant(self):
        # ai_usage >= 100 already implies near_cap upstream; only the critical
        # alert should be emitted, not both.
        alerts = compute_alerts(
            fleet_rows=[fleet_row(ai_usage=120, near_cap=True)],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")

    def test_failing_job_emits_critical_scheduler_alert(self):
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[job(errors_24h=3, last_status="error", last_error="boom")],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertEqual(alerts[0]["source"], "scheduler")
        self.assertEqual(alerts[0]["href"], "/operator/scheduler")
        self.assertEqual(alerts[0]["detail"], "boom")

    def test_paused_job_emits_warning_not_critical(self):
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[job(paused=True, last_status=None)],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "warning")

    def test_healthy_job_emits_no_alert(self):
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[job()],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(alerts, [])

    def test_token_invalid_incident_emits_critical(self):
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[],
            incidents=[{
                "id": "inc-1",
                "tenant_id": "tenant-2",
                "tenant_name": "Beta LLC",
                "type": "token_invalid",
                "detail": {"message": "Token invalid for WABA"},
                "created_at": "2026-07-01T10:00:00+00:00",
            }],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertEqual(alerts[0]["source"], "incident")
        self.assertEqual(alerts[0]["detail"], "Token invalid for WABA")

    def test_unknown_incident_type_defaults_to_warning(self):
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[],
            incidents=[{
                "id": "inc-2",
                "tenant_id": "tenant-3",
                "type": "delivery_degraded",
                "detail": None,
                "created_at": "2026-07-01T10:00:00+00:00",
            }],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "warning")

    def test_severity_ordering_critical_before_warning_before_info(self):
        alerts = compute_alerts(
            fleet_rows=[
                fleet_row(id="t-warn", name="Warn Co", ai_usage=85, near_cap=True),
                fleet_row(id="t-crit", name="Crit Co", token_expired=True),
            ],
            scheduler_jobs=[job(id="paused-job", paused=True, last_status=None)],
            incidents=[{
                "id": "inc-3",
                "tenant_id": "t-info",
                "type": "note",
                "detail": {"severity": "info"},
                "created_at": "2026-07-01T09:00:00+00:00",
            }],
            now=NOW,
        )
        severities = [a["severity"] for a in alerts]
        # critical alerts must all precede warning alerts
        first_warning_idx = severities.index("warning")
        self.assertTrue(all(s == "critical" for s in severities[:first_warning_idx]))
        self.assertTrue(all(s in ("warning", "info") for s in severities[first_warning_idx:]))
        self.assertEqual(severities[0], "critical")

    def test_dedup_same_alert_id_collapses_to_one(self):
        # Two fleet rows for the "same" tenant id (e.g. re-fetched) should not
        # produce duplicate alerts.
        alerts = compute_alerts(
            fleet_rows=[
                fleet_row(token_expired=True),
                fleet_row(token_expired=True),
            ],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)

    def test_distinct_problems_same_tenant_both_emitted(self):
        # A tenant that is both token_expired and near_cap gets two distinct
        # alerts (different underlying problems), not deduped into one.
        alerts = compute_alerts(
            fleet_rows=[fleet_row(token_expired=True, ai_usage=85, near_cap=True)],
            scheduler_jobs=[],
            incidents=[],
            now=NOW,
        )
        ids = {a["id"] for a in alerts}
        self.assertEqual(len(alerts), 2)
        self.assertIn("fleet:token_expired:tenant-1", ids)
        self.assertIn("fleet:near_cap:tenant-1", ids)

    def test_token_invalid_incidents_different_channels_both_emitted(self):
        # create_token_incident dedups token_invalid incidents per (tenant,
        # channel), so a tenant can have two simultaneous open token_invalid
        # incidents (e.g. Telegram AND WhatsApp both broken). Both are
        # distinct DB rows with distinct ids and must surface as two alerts,
        # not collapse into one (which would silently drop the second).
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[],
            incidents=[
                {
                    "id": "inc-telegram",
                    "tenant_id": "tenant-5",
                    "tenant_name": "Gamma Inc",
                    "type": "token_invalid",
                    "detail": {"channel": "telegram", "message": "Telegram token invalid"},
                    "created_at": "2026-07-01T10:00:00+00:00",
                },
                {
                    "id": "inc-whatsapp",
                    "tenant_id": "tenant-5",
                    "tenant_name": "Gamma Inc",
                    "type": "token_invalid",
                    "detail": {"channel": "whatsapp", "message": "WhatsApp token invalid"},
                    "created_at": "2026-07-01T10:05:00+00:00",
                },
            ],
            now=NOW,
        )
        self.assertEqual(len(alerts), 2)
        ids = {a["id"] for a in alerts}
        self.assertEqual(len(ids), 2)
        details = {a["detail"] for a in alerts}
        self.assertIn("Telegram token invalid", details)
        self.assertIn("WhatsApp token invalid", details)

    def test_same_incident_refetched_collapses_to_one(self):
        # The same incident row (same id) appearing twice in the input -- as
        # would happen if a poll re-fetches an already-seen incident -- must
        # still collapse to a single alert.
        incident = {
            "id": "inc-telegram",
            "tenant_id": "tenant-5",
            "tenant_name": "Gamma Inc",
            "type": "token_invalid",
            "detail": {"channel": "telegram", "message": "Telegram token invalid"},
            "created_at": "2026-07-01T10:00:00+00:00",
        }
        alerts = compute_alerts(
            fleet_rows=[],
            scheduler_jobs=[],
            incidents=[incident, dict(incident)],
            now=NOW,
        )
        self.assertEqual(len(alerts), 1)

    def test_each_alert_has_required_shape(self):
        alerts = compute_alerts(
            fleet_rows=[fleet_row(token_expired=True)],
            scheduler_jobs=[job(errors_24h=1, last_status="error")],
            incidents=[{
                "id": "inc-4",
                "tenant_id": "tenant-9",
                "type": "token_invalid",
                "detail": None,
                "created_at": "2026-07-01T08:00:00+00:00",
            }],
            now=NOW,
        )
        required_keys = {
            "id", "severity", "title", "detail", "tenant_id", "tenant_name",
            "source", "created_at", "href",
        }
        for alert in alerts:
            self.assertTrue(required_keys.issubset(alert.keys()))
            self.assertIn(alert["severity"], {"critical", "warning", "info"})


if __name__ == "__main__":
    unittest.main()
