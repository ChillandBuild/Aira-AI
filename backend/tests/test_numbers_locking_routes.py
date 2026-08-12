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


class NumbersLockingPatchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_blocks_activating_locked_number(self, mock_get_db, mock_unlocked):
        mock_get_db.return_value = MagicMock()
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"status": "active"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("locked", res.json()["detail"].lower())

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_blocks_resuming_locked_number(self, mock_get_db, mock_unlocked):
        mock_get_db.return_value = MagicMock()
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"paused_outbound": False},
        )
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_pausing_a_locked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "paused_outbound": True}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"paused_outbound": True},
        )
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_setting_locked_number_as_primary(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "role": "primary"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()  # currently locked -- Set Primary is the unlock action

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"role": "primary"},
        )
        self.assertEqual(res.status_code, 200)
        mock_unlocked.assert_not_called()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_rename_on_locked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "num-1", "display_name": "New Name"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"display_name": "New Name"},
        )
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_rejects_status_not_in_phone_numbers_status_check(self, mock_get_db, mock_unlocked):
        """Breaks if an invalid status reaches the DB and trips phone_numbers_status_check (23514 -> 500)."""
        mock_get_db.return_value = MagicMock()
        mock_unlocked.return_value = set()

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"status": "inactive"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("invalid status", res.json()["detail"].lower())
        mock_get_db.return_value.table.assert_not_called()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.get_supabase")
    def test_allows_activating_an_unlocked_number(self, mock_get_db, mock_unlocked):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "00000000-0000-0000-0000-000000000001", "status": "active"}]
        )
        mock_get_db.return_value = db
        mock_unlocked.return_value = {"00000000-0000-0000-0000-000000000001"}

        res = self.client.patch(
            "/api/v1/numbers/00000000-0000-0000-0000-000000000001",
            json={"status": "active"},
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
