"""GET /numbers/ marks over-quota rows as locked; PATCH enforces the lock."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


class NumbersLockingGetTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.get_supabase")
    def test_list_marks_over_quota_numbers_locked(self, mock_get_db, mock_limit, mock_unlocked):
        db = MagicMock()
        rows = [
            {"id": "a", "role": "primary", "status": "active", "quality_rating": "green"},
            {"id": "b", "role": "standby", "status": "warming", "quality_rating": "green"},
        ]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(data=rows)
        mock_get_db.return_value = db
        mock_limit.return_value = 1
        mock_unlocked.return_value = {"a"}

        res = self.client.get("/api/v1/numbers/")
        self.assertEqual(res.status_code, 200)
        by_id = {n["id"]: n for n in res.json()["data"]}
        self.assertFalse(by_id["a"]["locked"])
        self.assertTrue(by_id["b"]["locked"])

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.get_supabase")
    def test_archived_numbers_never_locked(self, mock_get_db, mock_limit, mock_unlocked):
        db = MagicMock()
        rows = [{"id": "c", "role": "standby", "status": "archived", "quality_rating": "green"}]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(data=rows)
        mock_get_db.return_value = db
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.get("/api/v1/numbers/")
        self.assertFalse(res.json()["data"][0]["locked"])


if __name__ == "__main__":
    unittest.main()
