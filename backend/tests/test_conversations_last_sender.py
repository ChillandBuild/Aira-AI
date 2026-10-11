"""Inbox rows say "AI replied" / prefix "AI:" only when the AI really sent the last
message, so GET /api/v1/conversations reports who sent each lead's last message."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import conversations as conv_route
from tests.fake_supabase import FakeSupabase


class LastSenderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "owner", "user_id": "u1", "permissions": [],
        }
        db = self.db = FakeSupabase()
        for lid in ("ai", "human", "customer"):
            db.add("leads", id=lid, tenant_id="t1", deleted_at=None, archived_at=None, blocked_at=None)
        msgs = [
            ("ai", "inbound", False, "2026-10-10T09:00:00+00:00"),
            ("ai", "outbound", True, "2026-10-10T09:01:00+00:00"),
            ("human", "inbound", False, "2026-10-10T10:00:00+00:00"),
            ("human", "outbound", False, "2026-10-10T10:05:00+00:00"),
            ("customer", "outbound", True, "2026-10-10T08:00:00+00:00"),
            ("customer", "inbound", False, "2026-10-10T08:30:00+00:00"),
            ("ai", "inbound", False, "2026-10-10T09:00:00+00:00"),
        ]
        for lid, direction, ai, at in msgs:
            db.add("messages", tenant_id="t1", lead_id=lid, direction=direction, is_ai_generated=ai, created_at=at)
        db.add("messages", tenant_id="t2", lead_id="human", direction="outbound", is_ai_generated=True,
               created_at="2026-10-10T11:00:00+00:00")  # another business: must not count
        last = {"ai": "2026-10-10T09:01:00+00:00", "human": "2026-10-10T10:05:00+00:00", "customer": "2026-10-10T08:30:00+00:00"}
        db.rpc_handlers["get_conversation_leads"] = lambda params: [
            {"lead_id": lid, "last_reply_at": at, "last_message_content": "x", "total": 3} for lid, at in last.items()
        ]
        p = patch.object(conv_route, "get_supabase", return_value=db)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_each_row_reports_who_sent_the_last_message(self):
        res = self.client.get("/api/v1/conversations")
        self.assertEqual(res.status_code, 200, res.text)
        got = {l["id"]: (l["last_message_direction"], l["last_message_is_ai"]) for l in res.json()["leads"]}
        self.assertEqual(got, {
            "ai": ("outbound", True),
            "human": ("outbound", False),
            "customer": ("inbound", False),
        })

    def test_lookup_failure_leaves_the_sender_unknown_not_wrong(self):
        with patch.object(conv_route, "_last_message_senders", return_value={}):
            res = self.client.get("/api/v1/conversations")
        self.assertTrue(all(l["last_message_direction"] is None and l["last_message_is_ai"] is None for l in res.json()["leads"]))


if __name__ == "__main__":
    unittest.main()
