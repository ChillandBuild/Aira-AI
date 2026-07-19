"""Tests for the cross-tenant "AI Spend" fleet endpoint -- aggregates
tenant_token_usage across every tenant into fleet totals, a per-provider and
per-feature breakdown, and a per-client leaderboard with period-over-period
trend, since Aira funds every provider account rather than the tenant."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class FleetTokenUsageTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, current_rows, prior_rows=None, tenant_names=None, total_clients=2, rate_rows=None):
        db = MagicMock()

        usage_tbl = MagicMock()
        usage_tbl.select.return_value.execute.return_value.data = current_rows
        usage_tbl.select.return_value.gte.return_value.execute.return_value.data = current_rows
        usage_tbl.select.return_value.gte.return_value.lt.return_value.execute.return_value.data = prior_rows or []

        tenants_tbl = MagicMock()
        tenants_tbl.select.return_value.in_.return_value.execute.return_value.data = [
            {"id": tid, "name": name} for tid, name in (tenant_names or {}).items()
        ]
        tenants_tbl.select.return_value.execute.return_value.count = total_clients

        rates_tbl = MagicMock()
        rates_tbl.select.return_value.execute.return_value.data = rate_rows or []

        def table(name):
            return {"tenant_token_usage": usage_tbl, "tenants": tenants_tbl, "provider_model_rates": rates_tbl}[name]

        db.table.side_effect = table
        mock_get_db.return_value = db
        return db

    @patch("app.routes.operator.get_supabase")
    def test_leaderboard_ranks_clients_by_tokens_with_names_joined(self, mock_get_db):
        rows = [
            {"tenant_id": "t1", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "llama-3.3-70b-versatile", "calls": 5, "input_tokens": 5000, "output_tokens": 1000},
            {"tenant_id": "t2", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "gemini", "model": "gemini-3.1-flash-lite", "calls": 2, "input_tokens": 900, "output_tokens": 100},
        ]
        self._mock_db(mock_get_db, rows, tenant_names={"t1": "Meridian Realty", "t2": "Coastline Wellness"}, total_clients=5)

        res = self.client.get("/api/v1/operator/token-usage/fleet?all_time=true")
        self.assertEqual(res.status_code, 200)
        body = res.json()["data"]

        self.assertEqual(body["active_clients"], 2)
        self.assertEqual(body["total_clients"], 5)
        leaderboard = body["leaderboard"]
        self.assertEqual(leaderboard[0]["tenant_id"], "t1")
        self.assertEqual(leaderboard[0]["tenant_name"], "Meridian Realty")
        self.assertGreater(leaderboard[0]["share_of_fleet"], leaderboard[1]["share_of_fleet"])
        self.assertAlmostEqual(sum(r["share_of_fleet"] for r in leaderboard), 1.0, places=6)

    @patch("app.routes.operator.get_supabase")
    def test_by_provider_and_by_feature_aggregate_across_clients(self, mock_get_db):
        rows = [
            {"tenant_id": "t1", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "m1", "calls": 3, "input_tokens": 300, "output_tokens": 60},
            {"tenant_id": "t2", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "m1", "calls": 2, "input_tokens": 200, "output_tokens": 40},
            {"tenant_id": "t2", "usage_date": "2026-07-19", "purpose": "scoring", "provider": "groq", "model": "m1", "calls": 1, "input_tokens": 100, "output_tokens": 10},
        ]
        self._mock_db(mock_get_db, rows, tenant_names={"t1": "A", "t2": "B"})

        res = self.client.get("/api/v1/operator/token-usage/fleet?all_time=true")
        body = res.json()["data"]

        by_provider = {p["provider"]: p for p in body["by_provider"]}
        self.assertEqual(by_provider["groq"]["calls"], 6)

        by_feature = {f["purpose"]: f for f in body["by_feature"]}
        self.assertEqual(by_feature["ai_reply"]["calls"], 5)
        self.assertEqual(by_feature["scoring"]["calls"], 1)

    @patch("app.routes.operator.get_supabase")
    def test_trend_pct_none_when_all_time_or_no_prior_baseline(self, mock_get_db):
        rows = [{"tenant_id": "t1", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "m1", "calls": 1, "input_tokens": 100, "output_tokens": 10}]
        self._mock_db(mock_get_db, rows, prior_rows=[], tenant_names={"t1": "A"})

        # all_time=true: no trend at all
        res_all_time = self.client.get("/api/v1/operator/token-usage/fleet?all_time=true")
        body = res_all_time.json()["data"]
        self.assertIsNone(body["totals"]["trend_pct"])
        self.assertIsNone(body["leaderboard"][0]["trend_pct"])

        # ranged, but prior window was empty -> no baseline to compare against
        res_ranged = self.client.get("/api/v1/operator/token-usage/fleet?range_days=30")
        body2 = res_ranged.json()["data"]
        self.assertIsNone(body2["totals"]["trend_pct"])
        self.assertIsNone(body2["leaderboard"][0]["trend_pct"])

    @patch("app.routes.operator.get_supabase")
    def test_trend_pct_computed_against_prior_window(self, mock_get_db):
        rows = [{"tenant_id": "t1", "usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "m1", "calls": 1, "input_tokens": 150, "output_tokens": 0}]
        prior_rows = [{"tenant_id": "t1", "usage_date": "2026-06-19", "purpose": "ai_reply", "provider": "groq", "model": "m1", "calls": 1, "input_tokens": 100, "output_tokens": 0}]
        self._mock_db(mock_get_db, rows, prior_rows=prior_rows, tenant_names={"t1": "A"})

        res = self.client.get("/api/v1/operator/token-usage/fleet?range_days=30")
        body = res.json()["data"]
        # 150 vs 100 baseline -> +50%
        self.assertEqual(body["totals"]["trend_pct"], 50)
        self.assertEqual(body["leaderboard"][0]["trend_pct"], 50)


if __name__ == "__main__":
    unittest.main()
