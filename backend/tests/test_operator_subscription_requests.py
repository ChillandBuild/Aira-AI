"""Tests for the operator subscription-requests approval queue routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
