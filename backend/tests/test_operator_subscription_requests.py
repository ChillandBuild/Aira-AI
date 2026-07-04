"""Tests for the operator subscription-requests approval queue routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorSubscriptionRequestsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_list_includes_tenant_name(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "subscription_requests":
                tbl.select.return_value.order.return_value.execute.return_value.data = [
                    {"id": "req-1", "tenant_id": "tenant-1", "status": "submitted", "requested_items": [],
                     "package_id": None, "total_amount": 1500, "is_initial": True,
                     "payment_confirmed": False, "submitted_at": "2026-07-04T00:00:00Z"}
                ]
            elif name == "tenants":
                tbl.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "tenant-1", "name": "ABC Coaching"}
                ]
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/subscription-requests")
        self.assertEqual(res.status_code, 200)
        rows = res.json()["data"]
        self.assertEqual(rows[0]["tenant_name"], "ABC Coaching")

    @patch("app.routes.operator.approve_request")
    @patch("app.routes.operator.get_supabase")
    def test_approve_requires_payment_confirmed(self, mock_db, mock_approve):
        res = self.client.patch(
            "/api/v1/operator/subscription-requests/req-1",
            json={"action": "approve", "payment_confirmed": False},
        )
        self.assertEqual(res.status_code, 400)
        mock_approve.assert_not_called()

    @patch("app.routes.operator.approve_request")
    @patch("app.routes.operator.get_supabase")
    def test_approve_with_payment_confirmed_calls_service(self, mock_db, mock_approve):
        mock_approve.return_value = {"id": "req-1", "status": "approved"}
        res = self.client.patch(
            "/api/v1/operator/subscription-requests/req-1",
            json={"action": "approve", "payment_confirmed": True},
        )
        self.assertEqual(res.status_code, 200)
        mock_approve.assert_called_once()

    @patch("app.routes.operator.reject_request")
    @patch("app.routes.operator.get_supabase")
    def test_reject_requires_reason(self, mock_db, mock_reject):
        res = self.client.patch(
            "/api/v1/operator/subscription-requests/req-1",
            json={"action": "reject"},
        )
        self.assertEqual(res.status_code, 400)
        mock_reject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
