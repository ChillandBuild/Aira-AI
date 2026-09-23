"""Mandatory call-feedback gate: pending list, dismiss, sync heartbeat, direction."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import calls


class FakeQuery:
    """Chainable stand-in for a supabase query; records calls, returns fixed data."""

    def __init__(self, data):
        self.data = data
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        if name == "not_":
            return self

        def _record(*args, **kwargs):
            self.calls.append((name, args))
            return self

        return _record

    def execute(self):
        return MagicMock(data=self.data)

    def has(self, name, *args):
        return (name, args) in self.calls


class FakeDb:
    def __init__(self, by_table):
        self.by_table = by_table
        self.queries: dict[str, list[FakeQuery]] = {}

    def table(self, name):
        data = self.by_table.get(name, [])
        q = FakeQuery(list(data))
        self.queries.setdefault(name, []).append(q)
        return q


class DirectionTests(unittest.TestCase):
    def test_maps_android_call_types(self):
        self.assertEqual(calls._sim_direction(2), "outgoing")
        self.assertEqual(calls._sim_direction(1), "incoming")
        self.assertEqual(calls._sim_direction(3), "missed")

    def test_unknown_type_is_none(self):
        self.assertIsNone(calls._sim_direction(5))


class HeartbeatTests(unittest.TestCase):
    def test_stamps_last_sync_at(self):
        db = FakeDb({})
        calls._touch_caller_sync(db, "caller-1")
        q = db.queries["callers"][0]
        self.assertEqual(q.calls[0][0], "update")
        self.assertIn("last_sync_at", q.calls[0][1][0])

    def test_never_raises_when_db_fails(self):
        db = MagicMock()
        db.table.side_effect = RuntimeError("boom")
        calls._touch_caller_sync(db, "caller-1")  # must not raise


class GateRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _as(self, role, caller_id=None):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": role, "caller_id": caller_id,
            "user_id": "user-1", "permissions": [],
        }

    @patch("app.routes.calls.get_supabase")
    def test_pending_uses_feedback_marker_not_status_or_outcome(self, mock_get_db):
        self._as("caller", "caller-1")
        row = {"id": "c1", "created_at": "2026-09-25T10:00:00+00:00", "direction": "missed"}
        db = FakeDb({"call_logs": [row]})
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/calls/pending-wrapups")

        self.assertEqual(res.status_code, 200)
        sim_q = db.queries["call_logs"][0]
        self.assertTrue(sim_q.has("eq", "provider", "sim_basic"))
        self.assertTrue(sim_q.has("is_", "feedback_at", "null"))
        self.assertTrue(sim_q.has("is_", "feedback_dismissed_at", "null"))
        self.assertTrue(sim_q.has("gte", "created_at", calls.FEEDBACK_GATE_SINCE))
        self.assertTrue(sim_q.has("eq", "caller_id", "caller-1"))
        self.assertFalse(any(c[0] == "eq" and c[1][0] == "status" for c in sim_q.calls))

    @patch("app.routes.calls.get_supabase")
    def test_pending_route_not_shadowed_and_sorted_oldest_first(self, mock_get_db):
        self._as("caller", "caller-1")
        rows = [
            {"id": "b", "created_at": "2026-09-25T11:00:00+00:00"},
            {"id": "a", "created_at": "2026-09-25T09:00:00+00:00"},
        ]
        mock_get_db.return_value = FakeDb({"call_logs": rows})
        # both queries return the same fake rows; sorting must still hold
        res = self.client.get("/api/v1/calls/pending-wrapups")
        ids = [r["id"] for r in res.json()]
        self.assertEqual(ids, sorted(ids, key=lambda i: {"a": 0, "b": 1}[i]))

    @patch("app.routes.calls.get_supabase")
    def test_summary_is_owner_only(self, mock_get_db):
        self._as("caller", "caller-1")
        mock_get_db.return_value = FakeDb({})
        self.assertEqual(self.client.get("/api/v1/calls/pending-wrapups/summary").status_code, 403)

    @patch("app.routes.calls.get_supabase")
    def test_summary_counts_per_caller(self, mock_get_db):
        self._as("owner")
        mock_get_db.return_value = FakeDb({
            "call_logs": [{"caller_id": "c1"}, {"caller_id": "c1"}, {"caller_id": "c2"}],
            "callers": [
                {"id": "c1", "name": "A", "last_sync_at": None, "sync_token": "t"},
                {"id": "c2", "name": "B", "last_sync_at": "2026-09-25T10:00:00+00:00", "sync_token": None},
            ],
        })
        body = self.client.get("/api/v1/calls/pending-wrapups/summary").json()
        by_id = {r["caller_id"]: r for r in body}
        self.assertEqual(by_id["c1"]["pending_count"], 2)
        self.assertEqual(by_id["c2"]["pending_count"], 1)
        self.assertTrue(by_id["c1"]["has_sync_token"])
        self.assertFalse(by_id["c2"]["has_sync_token"])

    @patch("app.routes.calls.get_supabase")
    def test_dismiss_is_owner_only(self, mock_get_db):
        self._as("caller", "caller-1")
        mock_get_db.return_value = FakeDb({})
        res = self.client.post("/api/v1/calls/x/dismiss-feedback", json={"reason": "wrong number"})
        self.assertEqual(res.status_code, 403)

    @patch("app.routes.calls.get_supabase")
    def test_dismiss_requires_reason(self, mock_get_db):
        self._as("owner")
        mock_get_db.return_value = FakeDb({"call_logs": [{"id": "x"}]})
        res = self.client.post("/api/v1/calls/x/dismiss-feedback", json={"reason": ""})
        self.assertEqual(res.status_code, 422)

    @patch("app.routes.calls.get_supabase")
    def test_dismiss_is_tenant_scoped_and_records_who(self, mock_get_db):
        self._as("owner")
        db = FakeDb({"call_logs": [{"id": "x"}]})
        mock_get_db.return_value = db
        res = self.client.post("/api/v1/calls/x/dismiss-feedback", json={"reason": "wrong number"})
        self.assertEqual(res.status_code, 200)
        q = db.queries["call_logs"][0]
        self.assertTrue(q.has("eq", "tenant_id", "tenant-1"))
        update = q.calls[0][1][0]
        self.assertEqual(update["feedback_dismissed_by"], "user-1")
        self.assertEqual(update["feedback_dismiss_reason"], "wrong number")

    @patch("app.routes.calls.get_supabase")
    def test_dismiss_404_when_no_row_in_tenant(self, mock_get_db):
        self._as("owner")
        mock_get_db.return_value = FakeDb({"call_logs": []})
        res = self.client.post("/api/v1/calls/x/dismiss-feedback", json={"reason": "wrong number"})
        self.assertEqual(res.status_code, 404)


class SourceContractTests(unittest.TestCase):
    src = (Path(__file__).resolve().parents[1] / "app/routes/calls.py").read_text()

    def test_ingest_writes_direction(self):
        self.assertIn('"direction": _sim_direction(entry.call_type)', self.src)

    def test_set_outcome_stamps_feedback_at(self):
        self.assertIn('log_updates["feedback_at"]', self.src)

    def test_apk_updates_never_stamp_feedback_at(self):
        start = self.src.index("updates: dict = {")
        block = self.src[start:start + 400]
        self.assertNotIn("feedback_at", block)

    def test_heartbeat_wired_into_both_apk_routes(self):
        self.assertEqual(self.src.count("_touch_caller_sync(db, caller_id)"), 2)


if __name__ == "__main__":
    unittest.main()


class LeadNumbersTests(unittest.TestCase):
    """sim-lead-numbers: whole tenant, paged past PostgREST's 1000-row cap, heartbeat."""

    def _call(self, pages):
        pages = list(pages)
        db = MagicMock()
        q = MagicMock()
        for m in ("select", "eq", "is_", "order", "range"):
            getattr(q, m).return_value = q
        q.not_ = q
        q.execute.side_effect = [MagicMock(data=p) for p in pages]
        db.table.return_value = q
        request = MagicMock()
        with patch.object(calls, "get_supabase", return_value=db), \
             patch.object(calls, "_resolve_sim_caller", return_value={"id": "c1", "tenant_id": "t1"}), \
             patch.object(calls, "_touch_caller_sync") as touch:
            import asyncio
            out = asyncio.run(calls.sim_lead_numbers(request))
        return out, q, touch

    def test_covers_unassigned_leads_and_stamps_heartbeat(self):
        out, q, touch = self._call([[{"phone": "+919876543210"}]])
        touch.assert_called_once()
        eq_args = [c.args for c in q.eq.call_args_list]
        self.assertNotIn(("assigned_to", "c1"), eq_args)
        self.assertIn(("tenant_id", "t1"), eq_args)
        self.assertEqual(out["numbers"], ["+919876543210"])

    def test_pages_until_short_page(self):
        full = [{"phone": f"+9198765{i:05d}"} for i in range(calls._LEAD_NUMBERS_PAGE)]
        out, q, _ = self._call([full, [{"phone": "+919000000001"}]])
        self.assertEqual(q.execute.call_count, 2)
        self.assertEqual(out["count"], calls._LEAD_NUMBERS_PAGE + 1)
