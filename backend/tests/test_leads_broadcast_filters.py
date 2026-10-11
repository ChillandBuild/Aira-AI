"""Segments 'Message Hot leads': the broadcast reaches exactly the leads the table
shows under the current filters, and the preview count matches what gets sent."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import leads as leads_route
from tests.fake_supabase import FakeSupabase

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(hours=2)).isoformat()
OLD = (NOW - timedelta(days=3)).isoformat()


class BroadcastFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "owner", "user_id": "u1", "permissions": [],
        }
        self.db = FakeSupabase()

        def lead(lead_id, **extra):
            row = dict(id=lead_id, tenant_id="t1", segment="A", source="whatsapp", phone=f"+9198000{lead_id[-5:]}",
                       assigned_to=None, opted_out=None, whatsapp_undeliverable=None, deleted_at=None,
                       opt_in_source="inbound", created_at=OLD)
            row.update(extra)
            self.db.add("leads", **row)

        lead("lead-00001", assigned_to="karthik")            # matches, window open
        lead("lead-00002", assigned_to="karthik")            # matches, window closed
        lead("lead-00003", assigned_to="karthik", opt_in_source=None)  # matches, never opted in
        lead("lead-00004", assigned_to="divya")              # other caller: filtered out
        lead("lead-00005", assigned_to="karthik", segment="B")  # other segment
        lead("lead-00006", assigned_to="karthik", deleted_at=OLD)  # deleted
        lead("lead-00007", assigned_to="karthik", opted_out=True)  # opted out
        lead("lead-00008", tenant_id="t2", assigned_to="karthik")  # another business
        for lead_id in ("lead-00001", "lead-00004", "lead-00005", "lead-00006", "lead-00007", "lead-00008"):
            self.db.add("messages", lead_id=lead_id, tenant_id="t1", direction="inbound", created_at=RECENT)
        self.db.add("messages", lead_id="lead-00002", tenant_id="t1", direction="inbound", created_at=OLD)

        p = patch.object(leads_route, "get_supabase", side_effect=lambda: self.db)
        p.start()
        self.addCleanup(p.stop)
        self.filters = {"segment": "A", "assigned_to": "karthik"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_preview_counts_only_the_filtered_leads(self):
        res = self.client.post("/api/v1/leads/broadcast/preview", json=self.filters)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json(), {"matching": 3, "reachable": 1, "outside_window": 1, "no_opt_in": 1})

    def test_send_reaches_only_what_the_preview_promised(self):
        sender = AsyncMock(return_value="wamid.1")
        with patch.object(leads_route, "send_whatsapp", sender):
            res = self.client.post("/api/v1/leads/broadcast", json={**self.filters, "message": "Diwali offer"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json(), {"total": 2, "sent": 1, "failed": 0, "skipped_window": 1})
        self.assertEqual([c.args[0] for c in sender.await_args_list], ["+919800000001"])

    def test_no_filters_still_skips_deleted_and_opted_out_leads(self):
        sender = AsyncMock(return_value="wamid.1")
        with patch.object(leads_route, "send_whatsapp", sender):
            res = self.client.post("/api/v1/leads/broadcast", json={"segment": "A", "message": "Hi"})
        self.assertEqual(res.json()["sent"], 2)  # lead-00001 and lead-00004; never 6, 7 or 8
        self.assertEqual(sorted(c.args[0] for c in sender.await_args_list), ["+919800000001", "+919800000004"])

    def test_reply_window_filter_applies_to_the_broadcast(self):
        self.db.rows("leads")[0]["last_inbound_at"] = RECENT
        res = self.client.post("/api/v1/leads/broadcast/preview", json={**self.filters, "reply_window": "open"})
        self.assertEqual(res.json()["matching"], 1)

    def test_empty_message_is_refused(self):
        res = self.client.post("/api/v1/leads/broadcast", json={**self.filters, "message": "  "})
        self.assertEqual(res.status_code, 400)

    def test_preview_needs_leads_manage(self):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "caller", "user_id": "u1", "permissions": ["leads.view"],
        }
        self.assertEqual(self.client.post("/api/v1/leads/broadcast/preview", json=self.filters).status_code, 403)


if __name__ == "__main__":
    unittest.main()
