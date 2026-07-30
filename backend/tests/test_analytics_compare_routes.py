"""Tests for GET /api/v1/analytics/compare -- period comparison endpoint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class AnalyticsCompareTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, summaries, daily_leads, daily_messages):
        """summaries/daily_* are lists: index 0 = current period, 1 = previous."""
        db = MagicMock()

        def rpc(name, params):
            result = MagicMock()
            if name == "analytics_period_summary":
                result.execute.return_value = MagicMock(data=summaries.pop(0))
            elif name == "analytics_daily_leads":
                result.execute.return_value = MagicMock(data=daily_leads.pop(0))
            elif name == "analytics_daily_messages":
                result.execute.return_value = MagicMock(data=daily_messages.pop(0))
            else:
                raise AssertionError(f"unexpected rpc {name}")
            return result

        db.rpc.side_effect = rpc
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_compare_returns_both_periods_with_deltas(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[
                [{"new_leads": 20, "inbound_leads": 20, "outbound_leads": 0, "hot": 4,
                  "warm": 6, "cold": 9, "disqualified": 1, "avg_score": 6.0,
                  "messages_in": 100, "messages_out": 120, "ai_replies": 118,
                  "human_replies": 2, "converted": 0}],
                [{"new_leads": 10, "inbound_leads": 10, "outbound_leads": 0, "hot": 2,
                  "warm": 3, "cold": 5, "disqualified": 0, "avg_score": 5.0,
                  "messages_in": 50, "messages_out": 60, "ai_replies": 60,
                  "human_replies": 0, "converted": 0}],
            ],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["current"]["start"], "2026-07-15")
        self.assertEqual(body["previous"]["start"], "2026-07-13")
        self.assertEqual(body["metrics"]["new_leads"]["current"], 20)
        self.assertEqual(body["metrics"]["new_leads"]["previous"], 10)
        self.assertEqual(body["metrics"]["new_leads"]["delta_pct"], 100)

    @patch("app.routes.analytics.get_supabase")
    def test_series_is_zero_filled_for_every_day_in_range(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[
                [{"day": "2026-07-16", "inbound": 5, "outbound": 0,
                  "hot": 1, "warm": 2, "cold": 2, "disqualified": 0}],
                [],
            ],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        series = res.json()["series"]["leads_inbound"]
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["current"], 0)
        self.assertEqual(series[1]["current"], 5)

    @patch("app.routes.analytics.get_supabase")
    def test_export_returns_csv_with_a_header_row(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare/export?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        body = res.content.decode()
        self.assertIn("day_index,current_date,current_leads_inbound", body)
        self.assertEqual(len(body.strip().splitlines()), 3)  # header + 2 days

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_unknown_preset_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=forever")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
