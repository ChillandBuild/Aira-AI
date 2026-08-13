import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id


LEAD_ID = "0761bbde-8626-42c3-963e-327f162ca37e"


class ClearChatTests(unittest.TestCase):
    """Clear Chat used to delete messages and nothing else, so the intake session,
    the Tamil lock and the compacted conversation summary all survived -- a cleared
    lead walked straight back into mid-flow on its next message (observed live
    2026-08-13: a fresh 'Hii' was answered with the pending details summary)."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "t-1"

    def tearDown(self):
        app.dependency_overrides.clear()

    def _db(self):
        db = MagicMock()
        lead = MagicMock()
        lead.data = {"id": LEAD_ID}
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = lead
        return db

    def _tables_touched(self, db):
        return [c.args[0] for c in db.table.call_args_list]

    @patch("app.routes.leads.get_supabase")
    def test_clears_messages_and_conversation_state(self, mock_get_db):
        db = self._db()
        mock_get_db.return_value = db

        res = self.client.delete(f"/api/v1/leads/{LEAD_ID}/clear-chat")

        self.assertEqual(res.status_code, 200)
        touched = self._tables_touched(db)
        self.assertIn("messages", touched)
        self.assertIn("lead_conversation_state", touched)

    @patch("app.routes.leads.get_supabase")
    def test_cancels_any_active_intake_session(self, mock_get_db):
        db = self._db()
        mock_get_db.return_value = db

        res = self.client.delete(f"/api/v1/leads/{LEAD_ID}/clear-chat")

        self.assertEqual(res.status_code, 200)
        self.assertIn("intake_sessions", self._tables_touched(db))

    @patch("app.routes.leads.get_supabase")
    def test_resets_the_tamil_lock(self, mock_get_db):
        db = self._db()
        mock_get_db.return_value = db

        self.client.delete(f"/api/v1/leads/{LEAD_ID}/clear-chat")

        lead_updates = [
            c.args[0] for c in db.table.return_value.update.call_args_list
            if isinstance(c.args[0], dict) and "tamil_locked" in c.args[0]
        ]
        self.assertTrue(lead_updates, "expected a leads update clearing tamil_locked")
        self.assertIs(lead_updates[0]["tamil_locked"], False)
        self.assertIs(lead_updates[0]["ai_enabled"], True)

    @patch("app.routes.leads.get_supabase")
    def test_404_for_a_lead_in_another_tenant(self, mock_get_db):
        db = MagicMock()
        missing = MagicMock()
        missing.data = None
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = missing
        mock_get_db.return_value = db

        res = self.client.delete(f"/api/v1/leads/{LEAD_ID}/clear-chat")

        self.assertEqual(res.status_code, 404)
        self.assertNotIn("intake_sessions", self._tables_touched(db))


if __name__ == "__main__":
    unittest.main()
