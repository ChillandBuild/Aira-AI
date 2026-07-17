import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import require_owner


class FollowUpsAiGateTests(unittest.TestCase):
    """ai_auto_reply_enabled is the master switch for every automated AI-authored outbound
    message, not just inbound replies -- /follow-ups/run must not send anything while a
    tenant has it off, and must leave due jobs untouched (still "pending") rather than
    marking them skipped/consumed, so they resume once the tenant re-enables."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[require_owner] = lambda: {"tenant_id": "tenant-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.follow_ups.build_follow_up_summary", return_value={"pending": 0})
    @patch("app.routes.follow_ups.get_setting", return_value="false")
    @patch("app.routes.follow_ups.get_supabase")
    def test_run_skips_entirely_when_ai_auto_reply_disabled(self, mock_get_db, mock_get_setting, mock_summary):
        db = MagicMock()
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/follow-ups/run")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {
            "processed": 0, "sent": 0, "failed": 0, "skipped": 0, "summary": {"pending": 0},
        })
        mock_get_setting.assert_called_once_with("ai_auto_reply_enabled", fallback="true", tenant_id="tenant-1")
        # Never even queries for due jobs -- they stay "pending" untouched.
        db.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
