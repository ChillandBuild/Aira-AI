"""Tests for optional start/end custom ranges on /messaging and /inbound.
/overview is deliberately excluded -- see the plan's Global Constraints."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes.analytics import _resolve_window


class ResolveWindowTests(unittest.TestCase):
    def test_custom_start_end_builds_a_half_open_utc_window(self):
        start_dt, end_dt, days = _resolve_window("7d", "2026-07-10", "2026-07-12")
        self.assertEqual(start_dt.isoformat(), "2026-07-10T00:00:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-07-13T00:00:00+00:00")
        self.assertEqual(days, ["2026-07-10", "2026-07-11", "2026-07-12"])

    def test_end_before_start_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "2026-07-12", "2026-07-10")

    def test_malformed_date_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "not-a-date", "2026-07-12")

    def test_missing_start_end_falls_back_to_the_preset(self):
        start_dt, end_dt, days = _resolve_window("today", None, None)
        self.assertEqual(len(days), 1)
        self.assertIsNotNone(end_dt)


class MessagingCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_passes_exact_bounds_to_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        first_call_params = db.rpc.call_args_list[0].args[1]
        self.assertEqual(first_call_params["p_start"], "2026-07-10T00:00:00+00:00")
        self.assertEqual(first_call_params["p_end"], "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)


class InboundCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_bounds_the_leads_query_on_both_ends(self, mock_get_db):
        db = MagicMock()
        gte_mock = db.table.return_value.select.return_value.eq.return_value.in_.return_value.is_.return_value.gte
        gte_mock.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        gte_mock.assert_called_with("created_at", "2026-07-10T00:00:00+00:00")
        gte_mock.return_value.lt.assert_called_with("created_at", "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
