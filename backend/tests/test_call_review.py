"""Call Review: per-lead roll-up and the admin-only routes behind it."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.services.call_review import is_connected, summarize_leads


def _lead(lid, **kw):
    return {"id": lid, "name": f"Lead {lid}", "phone": "+910000000000", "segment": "warm", "score": 5, "assigned_to": None, **kw}


class SummarizeLeadsTests(unittest.TestCase):
    def test_totals_per_lead(self):
        calls = [
            {"lead_id": "a", "created_at": "2026-10-01T10:00:00+00:00", "status": "completed", "duration_seconds": 300, "score": 80, "score_status": "scored"},
            {"lead_id": "a", "created_at": "2026-10-02T10:00:00+00:00", "status": "completed", "duration_seconds": 120, "score": 50, "score_status": "scored"},
            {"lead_id": "a", "created_at": "2026-10-03T10:00:00+00:00", "status": "no_answer", "duration_seconds": 0, "score_status": "not_connected"},
        ]
        [row] = summarize_leads(calls, [], [_lead("a")], set())
        self.assertEqual(row["calls"], 3)
        self.assertEqual(row["connected"], 2)
        self.assertEqual(row["talk_seconds"], 420)
        self.assertEqual(row["scored"], 2)
        self.assertEqual(row["avg_score"], 65.0)
        self.assertTrue(row["needs_review"])
        self.assertEqual(row["last_call_at"], "2026-10-03T10:00:00+00:00")
        self.assertEqual(row["last_call"]["score_status"], "not_connected")

    def test_provisional_and_early_exit_are_not_averaged(self):
        calls = [
            {"lead_id": "a", "created_at": "1", "status": "completed", "duration_seconds": 40, "score": 30, "score_status": "provisional"},
            {"lead_id": "a", "created_at": "2", "status": "completed", "duration_seconds": 40, "score_status": "early_exit"},
        ]
        [row] = summarize_leads(calls, [], [_lead("a")], set())
        self.assertIsNone(row["avg_score"])
        self.assertEqual(row["early_exits"], 1)
        self.assertFalse(row["needs_review"])

    def test_assigned_untouched_leads_sort_last_and_notes_count(self):
        leads = [_lead("idle"), _lead("noted"), _lead("called")]
        calls = [{"lead_id": "called", "created_at": "2026-10-01T00:00:00+00:00", "status": "completed", "duration_seconds": 10}]
        notes = [{"lead_id": "noted", "created_at": "2026-10-02T00:00:00+00:00"}]
        rows = summarize_leads(calls, notes, leads, {"idle"})
        self.assertEqual([r["id"] for r in rows], ["noted", "called", "idle"])
        self.assertTrue(rows[2]["assigned"])
        self.assertEqual(rows[0]["notes"], 1)

    def test_rows_for_unknown_leads_are_ignored(self):
        calls = [{"lead_id": "gone", "created_at": "1", "status": "completed", "duration_seconds": 5}]
        self.assertEqual(summarize_leads(calls, [], [], set()), [])

    def test_manual_connected_counts_even_without_duration(self):
        self.assertTrue(is_connected({"manual_status": "connected", "status": "completed", "duration_seconds": None}))
        self.assertFalse(is_connected({"status": "missed", "duration_seconds": 30}))


class CallReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _as(self, role, permissions=()):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": role, "caller_id": "caller-1", "permissions": list(permissions),
        }

    RANGE = "start=2026-10-01T00:00:00%2B05:30&end=2026-10-04T00:00:00%2B05:30"

    def test_telecaller_without_team_manage_is_refused(self):
        self._as("caller", ["telecalling.notes"])
        self.assertEqual(self.client.get(f"/api/v1/call-review/leads?{self.RANGE}").status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/v1/call-review/leads/00000000-0000-0000-0000-000000000001/calls?{self.RANGE}").status_code,
            403,
        )

    def test_bad_range_is_rejected(self):
        self._as("owner")
        res = self.client.get("/api/v1/call-review/leads?start=2026-10-04T00:00:00&end=2026-10-01T00:00:00")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(self.client.get("/api/v1/call-review/leads?start=yesterday&end=today").status_code, 422)

    @patch("app.routes.call_review.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.call_review.get_supabase")
    def test_manager_gets_rows_scoped_to_tenant(self, mock_get_db, _cfg):
        self._as("member", ["team.manage"])
        db = MagicMock()
        q = MagicMock()
        for name in ("select", "eq", "gte", "lt", "is_", "in_", "order", "range", "not_", "like"):
            setattr(q, name, MagicMock(return_value=q))
        q.not_ = q
        lead = _lead("11111111-1111-1111-1111-111111111111")
        q.execute.side_effect = [
            MagicMock(data=[{"lead_id": lead["id"], "created_at": "2026-10-02T10:00:00+00:00", "status": "completed", "duration_seconds": 60, "score": 72, "score_status": "scored"}]),
            MagicMock(data=[]),
            MagicMock(data=[lead]),
        ]
        db.table.return_value = q
        mock_get_db.return_value = db

        res = self.client.get(f"/api/v1/call-review/leads?{self.RANGE}")

        self.assertEqual(res.status_code, 200, res.text)
        [row] = res.json()["data"]
        self.assertEqual(row["avg_score"], 72.0)
        q.eq.assert_any_call("tenant_id", "tenant-1")


if __name__ == "__main__":
    unittest.main()


class NoteAuthorTests(unittest.TestCase):
    """Call Review filters notes by telecaller, so a new note must record who wrote it."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "caller", "caller_id": "caller-me", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.lead_notes.get_supabase")
    def test_note_is_stamped_with_the_writers_caller_profile(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "n1"}])
        mock_get_db.return_value = db

        res = self.client.post(
            "/api/v1/lead-notes/00000000-0000-0000-0000-000000000001",
            json={"content": "Wants a callback", "caller_id": "someone-else"},
        )

        self.assertEqual(res.status_code, 200, res.text)
        inserted = db.table.return_value.insert.call_args.args[0]
        self.assertEqual(inserted["caller_id"], "caller-me")
        self.assertEqual(inserted["tenant_id"], "tenant-1")
