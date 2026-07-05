"""Telecaller seats are unlimited for now; provider validation still applies."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class TeamSeatEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.team.get_telecalling_config", return_value={"calling_provider": "sim_basic"})
    @patch("app.routes.team.get_supabase")
    def test_invite_does_not_block_on_purchased_seat_quantity(self, mock_get_db, mock_cfg):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 2
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/team/invite", json={
            "email": "new@example.com", "password": "Password123!", "name": "New Caller",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("phone number is required", res.json()["detail"].lower())

    @patch("app.routes.team.get_telecalling_config", return_value={"calling_provider": "sim_basic"})
    @patch("app.routes.team.get_supabase")
    def test_allowed_path_still_proceeds_to_provider_validation(self, mock_get_db, mock_cfg):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 1
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/team/invite", json={
            "email": "new@example.com", "password": "Password123!", "name": "New Caller",
        })
        # Under quota, so the seat check passes; SIM Basic then requires a
        # phone number, which this payload doesn't provide — proves we got
        # past the seat-limit guard rather than being blocked by it.
        self.assertEqual(res.status_code, 400)
        self.assertIn("phone number is required", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
