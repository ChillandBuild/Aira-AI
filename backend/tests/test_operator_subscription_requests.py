"""Tests for the operator subscription-requests approval queue routes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin
from app.services.subscription_requests import approve_request


class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Mimics supabase-py's builder: maybe_single().execute() yields ``None``
    on zero rows, plain execute() yields a response whose ``.data`` is a list."""

    def __init__(self, rows):
        self._rows = rows
        self._maybe_single = False
        self._patch = None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def upsert(self, *a, **k):
        return self

    def update(self, patch, *a, **k):
        # Supabase returns the mutated rows; mirror the patch onto them.
        self._patch = patch
        return self

    def insert(self, *a, **k):
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def execute(self):
        rows = [{**r, **self._patch} for r in self._rows] if self._patch else list(self._rows)
        if self._maybe_single:
            return _FakeResp(rows[0]) if rows else None
        return _FakeResp(rows)


class _FakeDB:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


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


class ApproveRequestServiceTests(unittest.TestCase):
    def test_approve_initial_subscription_with_no_existing_items(self):
        """Initial subscription: tenant has zero tenant_subscription_items, so the
        existing-item lookup returns None (supabase maybe_single on zero rows).
        Regression for the AttributeError that surfaced as a 500 on approve."""
        req = {
            "id": "req-1",
            "tenant_id": "tenant-1",
            "package_id": None,
            "total_amount": 1500,
            "requested_items": [
                {"feature_key": "inbound_messaging", "quantity": 1, "line_total": 1500},
            ],
        }
        db = _FakeDB({
            "subscription_requests": [req],
            "tenant_subscription_items": [],  # no items yet -> maybe_single -> None
            "feature_catalog": [],
            "tenants": [],
            "tenant_usage_counters": [],
            "tenant_subscriptions": [],
        })

        result = approve_request(db, "req-1", reviewer_user_id="admin-1")

        self.assertEqual(result["status"], "approved")


if __name__ == "__main__":
    unittest.main()
