"""Tests for reply_window, assigned_to="unassigned", and sort query parameters on GET /api/v1/leads/."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routes import leads as leads_route
from app.dependencies.auth import get_current_user


class LeadsListFiltersTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[leads_route.require_leads_view] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _wire(self, db):
        """Return the query object the route holds after its base filters."""
        base = (
            db.table.return_value.select.return_value.eq.return_value
            .is_.return_value.or_.return_value.or_.return_value
        )
        # Set up a return chain that supports all the methods we use
        base.gte.return_value = base
        base.or_.return_value = base
        base.order.return_value = base
        base.range.return_value.execute.return_value = MagicMock(data=[], count=0)
        return base

    # Tests for reply_window=open
    @patch("app.routes.leads.get_supabase")
    def test_reply_window_open_filters_by_gte_last_inbound_at(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?reply_window=open")

        self.assertEqual(res.status_code, 200)
        # Check that gte was called with "last_inbound_at" and a string ending in "Z"
        base.gte.assert_called()
        call_args = base.gte.call_args
        self.assertEqual(call_args[0][0], "last_inbound_at")
        # Verify the cutoff string ends with Z (ISO format without +00:00)
        self.assertTrue(call_args[0][1].endswith("Z"))

    # Tests for reply_window=closed
    @patch("app.routes.leads.get_supabase")
    def test_reply_window_closed_filters_by_or_null_and_lt(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?reply_window=closed")

        self.assertEqual(res.status_code, 200)
        # Check that or_ was called with a string starting with "last_inbound_at.is.null,last_inbound_at.lt."
        or_calls = base.or_.call_args_list
        # We expect one or_ call for opted_out, one for whatsapp_undeliverable, and one for reply_window closed
        # Find the last or_ call (for reply_window closed)
        last_or_call = or_calls[-1]
        or_string = last_or_call[0][0]
        self.assertTrue(or_string.startswith("last_inbound_at.is.null,last_inbound_at.lt."))
        # Verify it ends with Z
        self.assertTrue(or_string.endswith("Z"))

    # Tests for reply_window validation
    @patch("app.routes.leads.get_supabase")
    def test_reply_window_invalid_value_returns_422(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?reply_window=bogus")
        self.assertEqual(res.status_code, 422)

    # Tests for assigned_to=unassigned
    @patch("app.routes.leads.get_supabase")
    def test_assigned_to_unassigned_uses_is_null(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?assigned_to=unassigned")

        self.assertEqual(res.status_code, 200)
        # Check that is_ was called with ("assigned_to", "null")
        is_calls = base.is_.call_args_list
        # First is_ call is for deleted_at, second is for assigned_to unassigned
        found_assigned_to_call = False
        for call in is_calls:
            if call[0][0] == "assigned_to" and call[0][1] == "null":
                found_assigned_to_call = True
                break
        self.assertTrue(found_assigned_to_call, "is_('assigned_to', 'null') was not called")

    # Tests for assigned_to with a normal value
    @patch("app.routes.leads.get_supabase")
    def test_assigned_to_normal_value_uses_eq(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        # Need to track eq calls
        base.eq.return_value = base
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?assigned_to=caller-123")

        self.assertEqual(res.status_code, 200)
        # Check that eq was called with ("assigned_to", "caller-123")
        eq_calls = base.eq.call_args_list
        found_assigned_to_eq = False
        for call in eq_calls:
            if len(call[0]) >= 2 and call[0][0] == "assigned_to" and call[0][1] == "caller-123":
                found_assigned_to_eq = True
                break
        self.assertTrue(found_assigned_to_eq, "eq('assigned_to', 'caller-123') was not called")

    # Tests for sort=newest
    @patch("app.routes.leads.get_supabase")
    def test_sort_newest_orders_by_created_at_desc(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?sort=newest")

        self.assertEqual(res.status_code, 200)
        # Check that order was called with ("created_at", desc=True)
        order_calls = base.order.call_args_list
        found_created_at_desc = False
        for call in order_calls:
            if call[0][0] == "created_at" and call[1].get("desc") == True:
                found_created_at_desc = True
                break
        self.assertTrue(found_created_at_desc, "order('created_at', desc=True) was not called for sort=newest")

    # Tests for sort=oldest
    @patch("app.routes.leads.get_supabase")
    def test_sort_oldest_orders_by_created_at_asc(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?sort=oldest")

        self.assertEqual(res.status_code, 200)
        # Check that order was called with ("created_at", desc=False)
        order_calls = base.order.call_args_list
        found_created_at_asc = False
        for call in order_calls:
            if call[0][0] == "created_at" and call[1].get("desc") == False:
                found_created_at_asc = True
                break
        self.assertTrue(found_created_at_asc, "order('created_at', desc=False) was not called for sort=oldest")

    # Tests for sort=urgent
    @patch("app.routes.leads.get_supabase")
    def test_sort_urgent_orders_by_last_inbound_at_asc(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?sort=urgent")

        self.assertEqual(res.status_code, 200)
        # Check that order was called with last_inbound_at asc, then created_at desc
        order_calls = base.order.call_args_list
        found_last_inbound_asc = False
        for call in order_calls:
            if call[0][0] == "last_inbound_at" and call[1].get("desc") == False:
                found_last_inbound_asc = True
                break
        self.assertTrue(found_last_inbound_asc, "order('last_inbound_at', desc=False, ...) was not called for sort=urgent")

    # Tests for no sort (default ordering)
    @patch("app.routes.leads.get_supabase")
    def test_no_sort_keeps_default_ordering(self, mock_get_db):
        db = MagicMock()
        base = self._wire(db)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/")

        self.assertEqual(res.status_code, 200)
        # Check that order("segment") was called first
        order_calls = base.order.call_args_list
        # The first order call should be for "segment"
        self.assertTrue(len(order_calls) > 0)
        self.assertEqual(order_calls[0][0][0], "segment")

    # Tests for sort validation
    @patch("app.routes.leads.get_supabase")
    def test_sort_invalid_value_returns_422(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?sort=invalid")
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
