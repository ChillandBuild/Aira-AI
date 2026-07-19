"""Tests for the admin-set cost-rate endpoints (migration 143's provider_model_rates
+ migration 144's distinct-pairs RPC), which back the "which models need a rate"
todo list on the AI Spend rate-management screen."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class ProviderRatesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_list_returns_configured_and_missing_pairs(self, mock_get_db):
        db = MagicMock()
        configured_tbl = MagicMock()
        configured_tbl.select.return_value.execute.return_value.data = [
            {"provider": "groq", "model": "llama-3.3-70b-versatile", "input_rate_per_1k_inr": 2.0, "output_rate_per_1k_inr": 4.0, "updated_at": "2026-07-19T00:00:00Z"},
        ]
        db.table.return_value = configured_tbl
        db.rpc.return_value.execute.return_value.data = [
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
            {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        ]
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/provider-rates")
        self.assertEqual(res.status_code, 200)
        body = res.json()["data"]
        self.assertEqual(len(body["configured"]), 1)
        self.assertEqual(body["missing"], [{"provider": "gemini", "model": "gemini-3.1-flash-lite"}])
        db.rpc.assert_called_once_with("distinct_token_usage_pairs", {})

    @patch("app.routes.operator.get_supabase")
    def test_put_upserts_a_rate(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        res = self.client.put("/api/v1/operator/provider-rates", json={
            "provider": "gemini", "model": "gemini-3.1-flash-lite",
            "input_rate_per_1k_inr": 1.5, "output_rate_per_1k_inr": 3.0,
        })
        self.assertEqual(res.status_code, 200)
        db.table.assert_called_with("provider_model_rates")
        upsert_call = db.table.return_value.upsert.call_args
        self.assertEqual(upsert_call.kwargs["on_conflict"], "provider,model")
        self.assertEqual(upsert_call.args[0]["provider"], "gemini")
        self.assertEqual(upsert_call.args[0]["input_rate_per_1k_inr"], 1.5)


if __name__ == "__main__":
    unittest.main()
