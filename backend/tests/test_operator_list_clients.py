"""
GET /api/v1/operator/clients (list_clients) loops over every tenant and, for
each one, looks up its owner via `tenant_users... .eq("role", "owner")
.maybe_single()`. `maybe_single()` raises `postgrest.APIError` if that query
ever returns more than one row (e.g. a tenant with a duplicate/stale
"owner" tenant_users row) -- and unlike the get_user_by_id lookup right
after it, that call isn't wrapped in a try/except. One bad tenant currently
takes down the whole list for every operator, not just that tenant.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from postgrest import APIError
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorListClientsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_owner_lookup_failure_does_not_500_the_whole_list(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.execute.return_value.data = [
                    {
                        "id": "tenant-1",
                        "name": "Acme Corp",
                        "enabled_features": ["whatsapp"],
                        "status": "active",
                        "created_at": "2026-07-01T00:00:00+00:00",
                    },
                    {
                        "id": "tenant-2",
                        "name": "Beta LLC",
                        "enabled_features": [],
                        "status": "active",
                        "created_at": "2026-07-01T00:00:00+00:00",
                    },
                ]
            elif name == "tenant_users":
                owner_query = tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value
                # tenant-1's owner lookup blows up (e.g. a duplicate "owner"
                # row makes maybe_single()'s "exactly one row" assumption
                # false); tenant-2's succeeds normally.
                owner_query.execute.side_effect = [
                    APIError({
                        "message": "Cannot coerce the result to a single JSON object",
                        "code": "406",
                        "hint": None,
                        "details": "The result contains more than one row.",
                    }),
                    MagicMock(data={"user_id": "user-2"}),
                ]
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        ids = [c["id"] for c in body["data"]]
        self.assertIn("tenant-1", ids)
        self.assertIn("tenant-2", ids)


if __name__ == "__main__":
    unittest.main()
