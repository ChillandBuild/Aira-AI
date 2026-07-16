"""
GET /api/v1/operator/clients/{tenant_id}/overview (client_overview) looks up
the tenant's owner via `tenant_users...eq("role", "owner").maybe_single()`.
`maybe_single().execute()` returns `None` outright (not an object with
`.data = None`) when zero rows match -- e.g. a tenant with no owner row yet.
The handler's `if owner_row.data:` crashes with AttributeError in that case,
which the frontend renders as a generic "Internal server error" banner on
the operator console's Product Overview page.

Same landmine as the one fixed in list_clients (see
test_operator_list_clients.py / commit 05218a8), just not patched here yet.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClientOverviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_missing_owner_row_does_not_500(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data={
                        "id": "tenant-1",
                        "name": "Acme Corp",
                        "status": "active",
                        "enabled_features": ["whatsapp"],
                        "created_at": "2026-07-01T00:00:00+00:00",
                        "plan": None,
                    }
                )
            elif name == "tenant_users":
                # Zero rows -> maybe_single().execute() returns None outright.
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = None
            else:
                # leads / messages / callers / call_logs count queries.
                empty = MagicMock(data=[], count=0)
                chain = tbl.select.return_value
                chain.eq.return_value = chain
                chain.is_.return_value = chain
                chain.in_.return_value = chain
                chain.gte.return_value = chain
                chain.order.return_value = chain
                chain.limit.return_value = chain
                chain.execute.return_value = empty
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/overview")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["owner"], {"user_id": None, "email": None, "created_at": None})
        self.assertEqual(body["tenant"]["id"], "tenant-1")


if __name__ == "__main__":
    unittest.main()
