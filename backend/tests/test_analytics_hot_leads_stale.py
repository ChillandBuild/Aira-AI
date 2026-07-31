"""Tests for GET /api/v1/analytics/hot-leads-stale."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class HotLeadsStaleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_returns_the_rpc_rows_under_a_leads_key(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[
            {"id": "lead-1", "name": "Asha", "phone": "+91900000001", "score": 8,
             "created_at": "2026-07-20T10:00:00+00:00", "last_outbound_at": None},
        ])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/hot-leads-stale")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["leads"]), 1)
        self.assertEqual(body["leads"][0]["name"], "Asha")

    @patch("app.routes.analytics.get_supabase")
    def test_passes_min_hours_and_limit_to_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/hot-leads-stale?min_hours=48&limit=5")

        self.assertEqual(res.status_code, 200)
        db.rpc.assert_called_with("analytics_stale_hot_leads", {
            "p_tenant_id": "tenant-1", "p_min_hours": 48, "p_limit": 5,
        })

    @patch("app.routes.analytics.get_supabase")
    def test_limit_over_50_is_rejected(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/hot-leads-stale?limit=999")
        self.assertEqual(res.status_code, 422)

    @patch("app.routes.analytics.get_supabase")
    def test_min_hours_under_1_is_rejected(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/hot-leads-stale?min_hours=0")
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
