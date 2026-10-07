"""Tests for client-facing subscription routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class SubscriptionRoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.subscriptions.get_supabase")
    def test_submit_requires_owner_role(self, mock_db):
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "caller"}
        res = self.client.post("/api/v1/subscriptions/requests", json={"items": [{"feature_key": "inbound_messaging", "quantity": 1}]})
        self.assertEqual(res.status_code, 403)

    @patch("app.routes.subscriptions.submit_request")
    @patch("app.routes.subscriptions.get_supabase")
    def test_submit_as_owner_calls_service(self, mock_db, mock_submit):
        mock_submit.return_value = {"id": "req-1", "total_amount": 1500}
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}
        res = self.client.post("/api/v1/subscriptions/requests", json={"items": [{"feature_key": "inbound_messaging", "quantity": 1}]})
        self.assertEqual(res.status_code, 200)
        mock_submit.assert_called_once()

    @patch("app.routes.subscriptions.get_supabase")
    def test_catalog_hides_operator_only_features(self, mock_db):
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}
        rows = [{"feature_key": "inbound_messaging"}, {"feature_key": "private_send"}]
        mock_db.return_value.table.return_value.select.return_value.order.return_value.execute.return_value.data = rows
        res = self.client.get("/api/v1/subscriptions/catalog")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([r["feature_key"] for r in res.json()["catalog"]], ["inbound_messaging"])

    @patch("app.routes.subscriptions.submit_request")
    def test_submit_rejects_operator_only_feature(self, mock_submit):
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}
        res = self.client.post("/api/v1/subscriptions/requests", json={"items": [{"feature_key": "private_send", "quantity": 1}]})
        self.assertEqual(res.status_code, 400)
        mock_submit.assert_not_called()

    def test_submit_rejects_empty_cart(self):
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}
        res = self.client.post("/api/v1/subscriptions/requests", json={"items": []})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
