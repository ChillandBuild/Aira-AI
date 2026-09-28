"""GET /api/v1/callers/my-stats: SIM clients get no evaluation at all."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CALLER_ID = "caller-1"


def _db():
    today_result = MagicMock(count=3)
    week_result = MagicMock(data=[{"outcome": "converted", "duration_seconds": 120}], count=1)
    hot_result = MagicMock(count=2)
    caller_result = MagicMock(data={"name": "Asha", "phone": "999", "status": "active"})

    call_logs_mock = MagicMock()

    def select_side_effect(fields, count=None):
        q = MagicMock()
        if fields == "id" and count == "exact":
            q.eq.return_value.eq.return_value.gte.return_value.execute.return_value = today_result
        else:
            q.eq.return_value.eq.return_value.gte.return_value.execute.return_value = week_result
        return q

    call_logs_mock.select.side_effect = select_side_effect

    leads_mock = MagicMock()
    leads_mock.select.return_value.eq.return_value.eq.return_value.gte.return_value.is_.return_value.execute.return_value = hot_result

    callers_mock = MagicMock()
    callers_mock.select.return_value.eq.return_value.single.return_value.execute.return_value = caller_result

    tables = {"call_logs": call_logs_mock, "leads": leads_mock, "callers": callers_mock}
    db = MagicMock()
    db.table.side_effect = lambda name: tables[name]
    return db


class MyStatsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "caller", "user_id": "u1", "caller_id": CALLER_ID, "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _get(self, calling_provider):
        month_stats = {CALLER_ID: {"avg_score": 8.4, "scored_calls": 12, "total_calls": 30}}
        with patch("app.routes.callers.get_supabase", return_value=_db()), \
             patch("app.routes.callers.get_telecalling_config", return_value={"calling_provider": calling_provider}), \
             patch("app.routes.callers.period_stats", return_value=month_stats):
            return self.client.get("/api/v1/callers/my-stats")

    def test_sim_tenant_has_no_score_fields(self):
        body = self._get("sim_basic").json()
        self.assertNotIn("avg_score_month", body)
        self.assertNotIn("scored_calls_month", body)
        self.assertEqual(body["total_calls_month"], 30)
        self.assertEqual(body["calls_today"], 3)

    def test_telecmi_tenant_is_unchanged(self):
        body = self._get("telecmi").json()
        self.assertEqual(body["avg_score_month"], 8.4)
        self.assertEqual(body["scored_calls_month"], 12)
        self.assertEqual(body["total_calls_month"], 30)


if __name__ == "__main__":
    unittest.main()
