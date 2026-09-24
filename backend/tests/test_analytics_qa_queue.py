"""GET /api/v1/analytics/qa-queue: the window's scored calls, lowest score first."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class _Q:
    """Records the filters and ordering the route applies."""

    def __init__(self, rec, table):
        self.rec, self.table = rec, table
        rec.setdefault(table, []).append(self)
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return call

    @property
    def not_(self):
        self.calls.append(("not_", (), {}))
        return self

    def execute(self):
        if self.table == "tenant_users":
            return MagicMock(data=[{"user_id": "owner-user"}])
        if self.table == "callers":
            return MagicMock(data=[{"id": "owner-caller"}])
        return MagicMock(data=[{"id": "c1", "score": 3.1, "transcript": "Telecaller: hi\nCustomer: no\nCustomer: bye"}], count=7)


class QaQueueTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "owner", "user_id": "u1", "caller_id": None, "permissions": [],
        }
        self.rec = {}
        db = MagicMock()
        db.table.side_effect = lambda name: _Q(self.rec, name)
        patcher = patch("app.routes.analytics.get_supabase", return_value=db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _call_log_query(self):
        return self.rec["call_logs"][0].calls

    def test_scored_calls_lowest_first_in_the_ist_window(self):
        res = self.client.get("/api/v1/analytics/qa-queue?from=2026-09-24&to=2026-09-25")
        self.assertEqual(res.status_code, 200)
        calls = self._call_log_query()
        self.assertIn(("eq", ("score_status", "scored"), {}), calls)
        self.assertIn(("gte", ("created_at", "2026-09-23T18:30:00+00:00"), {}), calls)
        self.assertIn(("lt", ("created_at", "2026-09-25T18:30:00+00:00"), {}), calls)
        order = [c for c in calls if c[0] == "order"]
        self.assertEqual(order[0][1], ("score",))

    def test_owner_calls_are_excluded_and_transcripts_masked(self):
        body = self.client.get("/api/v1/analytics/qa-queue").json()
        self.assertIn(("in_", ("caller_id", ["owner-caller"]), {}), self._call_log_query())
        self.assertEqual(body["total"], 7)
        row = body["data"][0]
        self.assertNotIn("transcript", row)
        self.assertEqual(row["transcript_preview"]["hidden_lines"], 1)

    def test_one_telecaller_can_be_selected(self):
        cid = "11111111-2222-3333-4444-555555555555"
        self.client.get(f"/api/v1/analytics/qa-queue?caller_id={cid}")
        self.assertIn(("eq", ("caller_id", cid), {}), self._call_log_query())

    def test_bad_date_is_a_400(self):
        self.assertEqual(self.client.get("/api/v1/analytics/qa-queue?from=yesterday").status_code, 400)


if __name__ == "__main__":
    unittest.main()
