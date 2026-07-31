"""Tests for date_from/date_to filtering on GET /api/v1/leads/."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routes import leads as leads_route
from app.dependencies.auth import get_current_user


class LeadsDateFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[leads_route.require_leads_view] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.leads.get_supabase")
    def test_date_from_and_date_to_are_applied_to_the_query(self, mock_get_db):
        db = MagicMock()
        base = (
            db.table.return_value.select.return_value.eq.return_value
            .is_.return_value.neq.return_value.neq.return_value
        )
        base.gte.return_value.lt.return_value.order.return_value.range.return_value.execute.return_value = (
            MagicMock(data=[], count=0)
        )
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?date_from=2026-07-10&date_to=2026-07-11")

        self.assertEqual(res.status_code, 200)
        base.gte.assert_called_with("created_at", "2026-07-10")
        base.gte.return_value.lt.assert_called_with("created_at", "2026-07-12")

    @patch("app.routes.leads.get_supabase")
    def test_malformed_date_from_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?date_from=not-a-date")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.leads.get_supabase")
    def test_malformed_date_to_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?date_to=not-a-date")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.leads.get_supabase")
    def test_no_date_params_leaves_existing_behaviour_unchanged(self, mock_get_db):
        db = MagicMock()
        base = (
            db.table.return_value.select.return_value.eq.return_value
            .is_.return_value.neq.return_value.neq.return_value
        )
        base.order.return_value.range.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/")

        self.assertEqual(res.status_code, 200)
        base.gte.assert_not_called()


if __name__ == "__main__":
    unittest.main()
