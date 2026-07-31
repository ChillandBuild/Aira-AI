"""GET /api/v1/operator/clients/{tenant_id}/roles -- read-only operator
visibility into a client's roles + role-assigned users (no editing; that
stays on the client's own Roles page)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClientRolesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.ensure_default_roles")
    @patch("app.routes.operator.get_supabase")
    def test_lists_roles_and_users(self, mock_get_db, mock_ensure_roles):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data={"id": "tenant-1"}
                )
            elif name == "tenant_roles":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "role-owner", "name": "Owner", "slug": "owner", "is_system_template": True, "permissions": []},
                        {
                            "id": "role-tc", "name": "Telecaller", "slug": "telecaller",
                            "is_system_template": True, "permissions": ["telecalling.dialer"],
                        },
                    ]
                )
            elif name == "tenant_users":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=[
                        {"user_id": "u-owner", "role": "owner", "role_id": None, "full_name": "Boss", "created_at": "2026-01-01"},
                        {"user_id": "u-1", "role": "caller", "role_id": "role-tc", "full_name": "Caller One", "created_at": "2026-01-02"},
                    ]
                )
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/roles")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["roles"]), 2)
        tc_role = next(r for r in body["roles"] if r["slug"] == "telecaller")
        self.assertTrue(tc_role["is_telecaller"])
        self.assertEqual(len(body["users"]), 2)
        self.assertEqual(body["users"][1]["role_name"], "Telecaller")

    @patch("app.routes.operator.get_supabase")
    def test_404_when_tenant_not_found(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-missing/roles")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
