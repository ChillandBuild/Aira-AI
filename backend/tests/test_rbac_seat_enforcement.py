"""Telecaller user creation via the Roles page (POST /api/v1/rbac/users) is
capped at the tenant's purchased `telecaller_seats` quantity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

TELECALLER_ROLE = {
    "id": "role-telecaller",
    "tenant_id": "tenant-1",
    "name": "Telecaller",
    "slug": "telecaller",
    "permissions": ["telecalling.dialer"],
}


def _mock_db(purchased_quantity, active_count, role=TELECALLER_ROLE):
    db = MagicMock()

    roles_tbl = MagicMock()
    roles_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[role] if role else []
    )

    items_tbl = MagicMock()
    items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"quantity": purchased_quantity}] if purchased_quantity else []
    )

    callers_tbl = MagicMock()
    eq_chain = callers_tbl.select.return_value.eq.return_value.eq.return_value
    eq_chain.execute.return_value = MagicMock(count=active_count)
    eq_chain.limit.return_value.execute.return_value = MagicMock(data=[])

    tenant_users_tbl = MagicMock()

    def table(name):
        return {
            "tenant_roles": roles_tbl,
            "tenant_subscription_items": items_tbl,
            "callers": callers_tbl,
            "tenant_users": tenant_users_tbl,
        }[name]

    db.table.side_effect = table
    return db


class RbacSeatEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_blocked_when_at_seat_limit(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=2, active_count=2)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("seat limit reached", res.json()["detail"].lower())

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_allowed_when_under_seat_limit(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=4, active_count=2)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["created"])

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_blocked_when_nothing_purchased(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=0, active_count=0)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("seat limit reached", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
