"""Tests for the read-only per-tenant entitlements view (replaces the old Feature Store plan-picker)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClientEntitlementsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_returns_items_and_status(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenant_subscription_items":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"feature_key": "inbound_messaging", "quantity": 1, "unit_price_snapshot": 1500}
                ]
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"status": "active"}
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/entitlements")
        self.assertEqual(res.status_code, 200)
        body = res.json()["data"]
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["items"], [{"feature_key": "inbound_messaging", "quantity": 1, "unit_price_snapshot": 1500}])


if __name__ == "__main__":
    unittest.main()
