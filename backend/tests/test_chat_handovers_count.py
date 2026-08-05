"""Tests for GET /api/v1/chat-handovers/count -- the dashboard 'Escalations'
KPI (today_only=true) and the sidebar/conversations-page backlog badge
(today_only omitted, must keep counting the full pending queue)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class ChatHandoverCountTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, count):
        db = MagicMock()
        tbl = MagicMock()
        base_chain = tbl.select.return_value.eq.return_value.eq.return_value
        base_chain.execute.return_value = MagicMock(count=count)
        base_chain.gte.return_value.execute.return_value = MagicMock(count=count)
        db.table.return_value = tbl
        mock_get_db.return_value = db
        return tbl, base_chain

    @patch("app.routes.chat_handovers.get_supabase")
    def test_default_counts_the_full_pending_backlog_without_a_date_filter(self, mock_get_db):
        tbl, base_chain = self._mock_db(mock_get_db, count=4)

        res = self.client.get("/api/v1/chat-handovers/count")

        self.assertEqual(res.json(), {"count": 4})
        base_chain.gte.assert_not_called()

    @patch("app.routes.chat_handovers.get_supabase")
    def test_today_only_filters_on_opened_at_since_ist_midnight(self, mock_get_db):
        tbl, base_chain = self._mock_db(mock_get_db, count=1)

        res = self.client.get("/api/v1/chat-handovers/count?today_only=true")

        self.assertEqual(res.json(), {"count": 1})
        base_chain.gte.assert_called_once()
        args, _ = base_chain.gte.call_args
        self.assertEqual(args[0], "opened_at")
        cutoff = datetime.fromisoformat(args[1])
        now = datetime.now(timezone.utc)
        # Cutoff is IST midnight expressed in UTC -- always in the past and
        # never more than 24h ago (a fresh IST midnight rolls over daily).
        self.assertLess(cutoff, now)
        self.assertGreater(cutoff, now - timedelta(hours=24))


if __name__ == "__main__":
    unittest.main()
