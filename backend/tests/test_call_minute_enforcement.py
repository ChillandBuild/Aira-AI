"""Test that call initiation is blocked once the call_minute quota is exhausted."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class CallMinuteEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.calls.check_quota", return_value=False)
    @patch("app.routes.calls.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.calls.get_setting", return_value="secret")
    @patch("app.routes.calls.get_supabase")
    def test_blocked_when_call_minute_quota_exhausted(self, mock_get_db, mock_setting, mock_cfg, mock_check_quota):
        res = self.client.post("/api/v1/calls/initiate", json={"phone": "+919999999999"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("call minute quota", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
