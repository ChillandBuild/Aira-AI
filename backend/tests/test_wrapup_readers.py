"""Readers of call outcomes after wrap-up v2: analytics, recycler, workload, AI call context, operator."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.main import app
from app.routes import analytics
from app.services import assignment, contact_recycler
from app.services.ai_reply import _call_context_block
from app.services.call_wrapup import CONNECTS
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc


class AnalyticsTests(unittest.TestCase):
    def test_connect_rate_is_connected_over_wrapups(self):
        logs = [
            {"created_at": "2026-09-27T05:00:00+00:00", "manual_status": "connected", "outcome": "converted", "duration_seconds": 60, "caller_id": "c1"},
            {"created_at": "2026-09-27T05:10:00+00:00", "manual_status": "not_picked", "outcome": None, "duration_seconds": 0, "caller_id": "c1"},
            {"created_at": "2026-09-27T05:20:00+00:00", "manual_status": None, "outcome": None, "duration_seconds": None, "caller_id": "c1"},
        ]
        out = analytics._window_aggregate(logs, [], [], datetime(2026, 9, 27, tzinfo=UTC), datetime(2026, 9, 28, tzinfo=UTC), 1)
        self.assertEqual((out["calls"], out["connect_rate"], out["conversions"]), (3.0, 0.5, 1.0))

    def test_followups_scheduled_counts_only_call_later_outcomes(self):
        logs = [
            {"outcome": "call_later", "next_action_at": "2026-09-27T10:00:00+00:00"},
            {"outcome": "interested_booked", "next_action_at": "2026-09-27T11:00:00+00:00"},
            {"outcome": None, "manual_status": "not_picked", "next_action_at": "2026-09-27T12:00:00+00:00"},
            {"outcome": "call_later", "next_action_at": "2026-09-27T13:00:00+00:00"},
        ]
        self.assertEqual(analytics._followups_scheduled(logs), 2)

    def test_manual_status_breakdown_is_the_four_connect_values(self):
        counts = analytics._manual_status_breakdown([{"manual_status": "busy"}, {"manual_status": "switched_off"}, {"manual_status": None}])
        self.assertEqual(set(counts), set(CONNECTS))
        self.assertEqual((counts["busy"], counts["switched_off"], counts["connected"]), (1, 1, 0))

    def test_old_helpers_are_gone(self):
        self.assertFalse(hasattr(analytics, "_is_connected"))
        self.assertFalse(hasattr(analytics, "MANUAL_STATUS_KEYS"))


class RecyclerTests(unittest.TestCase):
    def test_only_trying_leads_whose_last_call_never_connected_are_recycled(self):
        db = FakeSupabase()
        old = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
        for lead_id, status in (("l1", "trying"), ("l2", "trying"), ("l3", "hot")):
            db.add("leads", id=lead_id, tenant_id="t1", call_status=status, converted_at=None, deleted_at=None,
                   do_not_call=False, assigned_to="c1")
        db.add("call_logs", tenant_id="t1", lead_id="l1", outcome=None, manual_status="not_picked", created_at=old)
        db.add("call_logs", tenant_id="t1", lead_id="l2", outcome="interested_needs_time", manual_status="connected", created_at=old)
        db.add("call_logs", tenant_id="t1", lead_id="l3", outcome=None, manual_status="busy", created_at=old)
        cfg = {"enabled": True, "delay_hours": 4, "max_retries": 3, "start_hour": 0, "end_hour": 24, "max_call_attempts": 4}
        with patch.object(contact_recycler, "get_supabase", return_value=db), \
             patch.object(contact_recycler, "_get_recycle_config", return_value=cfg):
            count = contact_recycler.recycle_leads_for_tenant("t1")
        statuses = {r["id"]: r["call_status"] for r in db.rows("leads")}
        self.assertEqual(count, 1)
        self.assertEqual(statuses, {"l1": "new", "l2": "trying", "l3": "hot"})


class WorkloadTests(unittest.TestCase):
    def test_disqualified_leads_do_not_count_as_open_work(self):
        db = FakeSupabase()
        for status in ("warm", "disqualified", "dnc"):
            db.add("leads", tenant_id="t1", assigned_to="c1", segment="B", converted_at=None, do_not_call=False, call_status=status)
        self.assertEqual(assignment._open_lead_count(db, "t1", "c1"), 1)


class AiCallContextTests(unittest.TestCase):
    def test_uses_readable_labels(self):
        block = _call_context_block([
            {"created_at": "2026-09-27T05:00:00", "outcome": "interested_needs_time", "manual_status": "connected", "ai_summary": {"brief": "b"}},
            {"created_at": "2026-09-26T05:00:00", "outcome": None, "manual_status": "busy", "ai_summary": {"next_action": "retry"}},
        ])
        self.assertIn("outcome: Interested, needs time or more information", block)
        self.assertIn("2026-09-26 — Busy — retry", block)


LEAD_ID = "0761bbde-8626-42c3-963e-327f162ca37e"


class PreCallBriefTests(unittest.TestCase):
    """Regression: the pre-call brief's calls_res select once left out manual_status,
    so a not_picked/busy call showed 'outcome: unknown' here while ai_reply's identical
    _call_context_block correctly showed 'Not picked' -- the two call-facing surfaces
    disagreed about the same call. Covers the fetch path, not just the pure function."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @staticmethod
    def _table_mock(data):
        m = MagicMock()
        for method in ("select", "eq", "order", "limit", "maybe_single", "update"):
            getattr(m, method).return_value = m
        m.execute.return_value = MagicMock(data=data)
        return m

    def _db(self, call_rows):
        lead_row = {
            "name": "Priya", "score": 7, "segment": "A", "source": "whatsapp",
            "ad_campaign_id": None, "assigned_at": "2026-09-27T04:00:00+00:00",
            "needs_human_attention": False, "precall_brief": None,
            "precall_brief_fingerprint": None,
        }
        tables = {
            "leads": self._table_mock(lead_row),
            "messages": self._table_mock([]),
            "call_logs": self._table_mock(call_rows),
            "lead_conversation_state": self._table_mock([]),
        }
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db, tables

    @patch("app.routes.leads.gemini_chat_completion_json", new_callable=AsyncMock)
    @patch("app.routes.leads.get_supabase")
    def test_not_picked_call_reads_not_picked_not_unknown(self, mock_get_db, mock_gemini):
        db, tables = self._db([
            {"outcome": None, "manual_status": "not_picked", "duration_seconds": 0,
             "created_at": "2026-09-27T05:00:00+00:00", "ai_summary": None},
        ])
        mock_get_db.return_value = db
        mock_gemini.return_value = {"brief": "b", "opener": "o"}

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/pre-call-brief")

        self.assertEqual(res.status_code, 200)
        select_arg = tables["call_logs"].select.call_args[0][0]
        self.assertIn("manual_status", select_arg)
        prompt = mock_gemini.call_args.kwargs["user_prompt"]
        self.assertIn("outcome: Not picked", prompt)
        self.assertNotIn("outcome: unknown", prompt)


class StaticReaderTests(unittest.TestCase):
    def test_operator_uses_the_shared_connect_rate(self):
        src = (ROOT / "app/routes/operator.py").read_text(encoding="utf-8")
        self.assertNotIn("_is_connected_call", src)
        self.assertIn("wrapup_connect_rate(", src)

    def test_unused_outcome_literal_removed(self):
        self.assertNotIn("OutcomeType", (ROOT / "app/models/schemas.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
