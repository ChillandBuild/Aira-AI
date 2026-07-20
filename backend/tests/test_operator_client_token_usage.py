"""Tests for the per-tenant token-consumption view (migration 142's tenant_token_usage,
aggregated in Python by get_client_token_usage into totals/by_feature/by_model/daily),
including cost estimation against migration 143's admin-set rate card."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClientTokenUsageTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, usage_rows, rate_rows=None):
        db = MagicMock()
        tables: dict = {}

        def table(name):
            if name not in tables:
                tbl = MagicMock()
                if name == "tenant_token_usage":
                    tbl.select.return_value.eq.return_value.execute.return_value.data = usage_rows
                    tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = usage_rows
                elif name == "provider_model_rates":
                    tbl.select.return_value.execute.return_value.data = rate_rows or []
                tables[name] = tbl
            return tables[name]

        db.table.side_effect = table
        mock_get_db.return_value = db
        return db, tables

    @patch("app.routes.operator.get_supabase")
    def test_aggregates_totals_by_feature_by_model_and_daily(self, mock_get_db):
        rows = [
            {"usage_date": "2026-07-18", "purpose": "ai_reply", "provider": "groq", "model": "llama-3.3-70b-versatile", "calls": 10, "input_tokens": 1000, "output_tokens": 200},
            {"usage_date": "2026-07-18", "purpose": "scoring", "provider": "groq", "model": "llama-3.3-70b-versatile", "calls": 5, "input_tokens": 300, "output_tokens": 50},
            {"usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "gemini", "model": "gemini-3.1-flash-lite", "calls": 8, "input_tokens": 900, "output_tokens": 150},
        ]
        self._mock_db(mock_get_db, rows)

        res = self.client.get("/api/v1/operator/clients/tenant-1/token-usage")
        self.assertEqual(res.status_code, 200)
        body = res.json()

        self.assertEqual(body["range_days"], 30)
        totals = body["data"]["totals"]
        self.assertEqual(totals["calls"], 23)
        self.assertEqual(totals["input_tokens"], 2200)
        self.assertEqual(totals["output_tokens"], 400)

        by_feature = {f["purpose"]: f for f in body["data"]["by_feature"]}
        self.assertEqual(by_feature["ai_reply"]["calls"], 18)
        self.assertEqual(by_feature["ai_reply"]["input_tokens"], 1900)
        self.assertEqual(by_feature["scoring"]["calls"], 5)

        by_model = {(m["provider"], m["model"]): m for m in body["data"]["by_model"]}
        self.assertEqual(by_model[("groq", "llama-3.3-70b-versatile")]["calls"], 15)
        self.assertEqual(by_model[("gemini", "gemini-3.1-flash-lite")]["calls"], 8)

        daily = {d["date"]: d for d in body["data"]["daily"]}
        self.assertEqual(daily["2026-07-18"]["input_tokens"], 1300)
        self.assertEqual(daily["2026-07-19"]["input_tokens"], 900)
        # daily series must be date-ordered
        self.assertEqual([d["date"] for d in body["data"]["daily"]], ["2026-07-18", "2026-07-19"])

    @patch("app.routes.operator.get_supabase")
    def test_empty_usage_returns_zeroed_totals_not_an_error(self, mock_get_db):
        self._mock_db(mock_get_db, [])

        res = self.client.get("/api/v1/operator/clients/tenant-1/token-usage")
        self.assertEqual(res.status_code, 200)
        body = res.json()["data"]
        self.assertEqual(body["totals"], {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0, "has_unrated": False})
        self.assertEqual(body["by_feature"], [])
        self.assertEqual(body["by_model"], [])
        self.assertEqual(body["daily"], [])
        self.assertEqual(body["unrated_models"], [])

    @patch("app.routes.operator.get_supabase")
    def test_all_time_flag_skips_date_filter_and_nulls_range_days(self, mock_get_db):
        db, tables = self._mock_db(mock_get_db, [])
        res = self.client.get("/api/v1/operator/clients/tenant-1/token-usage?all_time=true")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["range_days"])
        # no .gte() call should have been made on the usage query chain
        tables["tenant_token_usage"].select.return_value.eq.return_value.gte.assert_not_called()

    @patch("app.routes.operator.get_supabase")
    def test_default_range_days_is_30(self, mock_get_db):
        self._mock_db(mock_get_db, [])
        res = self.client.get("/api/v1/operator/clients/tenant-1/token-usage")
        self.assertEqual(res.json()["range_days"], 30)

    @patch("app.routes.operator.get_supabase")
    def test_estimated_cost_computed_only_when_a_rate_is_configured(self, mock_get_db):
        rows = [
            {"usage_date": "2026-07-19", "purpose": "ai_reply", "provider": "groq", "model": "llama-3.3-70b-versatile", "calls": 1, "input_tokens": 1000, "output_tokens": 1000},
            {"usage_date": "2026-07-19", "purpose": "call_analysis", "provider": "gemini", "model": "gemini-3.1-flash-lite", "calls": 1, "input_tokens": 1000, "output_tokens": 1000},
        ]
        rates = [
            {"provider": "groq", "model": "llama-3.3-70b-versatile", "input_rate_per_1k_inr": 2.0, "output_rate_per_1k_inr": 4.0},
        ]
        self._mock_db(mock_get_db, rows, rates)

        res = self.client.get("/api/v1/operator/clients/tenant-1/token-usage?all_time=true")
        body = res.json()["data"]

        # groq: 1000/1000*2.0 + 1000/1000*4.0 = 6.0; gemini has no rate -> excluded from the sum, flagged instead
        self.assertAlmostEqual(body["totals"]["estimated_cost"], 6.0)
        self.assertTrue(body["totals"]["has_unrated"])
        self.assertEqual(body["unrated_models"], [{"provider": "gemini", "model": "gemini-3.1-flash-lite"}])

        by_model = {(m["provider"], m["model"]): m for m in body["by_model"]}
        self.assertAlmostEqual(by_model[("groq", "llama-3.3-70b-versatile")]["estimated_cost"], 6.0)
        self.assertFalse(by_model[("groq", "llama-3.3-70b-versatile")]["has_unrated"])
        self.assertAlmostEqual(by_model[("gemini", "gemini-3.1-flash-lite")]["estimated_cost"], 0.0)
        self.assertTrue(by_model[("gemini", "gemini-3.1-flash-lite")]["has_unrated"])


if __name__ == "__main__":
    unittest.main()
