"""GET /api/v1/analytics/telecalling: SIM clients get no evaluation at all --
no per-caller score, no scored-call count, no team quality average."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CALL_ROW = {
    "id": "log1", "duration_seconds": 610, "outcome": "converted", "manual_status": "connected",
    "next_action_at": None, "provider": "telecmi", "feedback_source": "automatic",
    "caller_id": "c1", "created_at": "2026-09-28T05:00:00+00:00",
    "score": 82.0, "score_status": "scored", "lead_id": None,
}


def _db():
    """One active caller, one scored call today for them; everything else
    (owner lookup, status logs, comparison window, RPC) is a bare MagicMock,
    which the route already tolerates by iterating/len'ing it as empty."""
    db = MagicMock()
    callers_tbl = MagicMock()
    callers_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "c1", "name": "Asha", "user_id": "u-caller"}]
    )
    call_counter = {"n": 0}

    def table_side_effect(name):
        if name == "callers":
            return callers_tbl
        if name == "call_logs":
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                m = MagicMock()
                m.select.return_value.eq.return_value.gte.return_value.execute.return_value = SimpleNamespace(data=[CALL_ROW])
                return m
            return MagicMock()
        return MagicMock()

    db.table.side_effect = table_side_effect
    return db


class TelecallingAnalyticsGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _get(self, calling_provider):
        with patch("app.routes.analytics.get_supabase", return_value=_db()), \
             patch("app.routes.analytics.get_telecalling_config", return_value={"calling_provider": calling_provider}):
            return self.client.get("/api/v1/analytics/telecalling")

    def test_sim_tenant_has_no_score_fields_anywhere(self):
        res = self._get("sim_basic")
        body = res.json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(body["per_caller"]), 1)
        self.assertNotIn("overall_score", body["per_caller"][0])
        self.assertNotIn("scored_calls", body["per_caller"][0])
        self.assertNotIn("quality_avg", body)

    def test_telecmi_tenant_is_unchanged(self):
        res = self._get("telecmi")
        body = res.json()
        self.assertEqual(res.status_code, 200)
        row = body["per_caller"][0]
        self.assertEqual(row["overall_score"], 82.0)
        self.assertEqual(row["scored_calls"], 1)
        self.assertEqual(body["quality_avg"], 82.0)


if __name__ == "__main__":
    unittest.main()
