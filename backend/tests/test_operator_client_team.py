"""GET /api/v1/operator/clients/{tenant_id}/team: SIM clients get no evaluation
at all -- no avg_score_month for their callers, but calling_provider always
tells the operator console which client it's looking at."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin

TENANT_ID = "tenant-1"


def _db():
    db = MagicMock()
    db.auth.admin.get_user_by_id.side_effect = Exception("no auth backend in tests")

    tenant_users_calls = {"n": 0}

    def table(name):
        tbl = MagicMock()
        if name == "tenants":
            tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"id": TENANT_ID}
            )
        elif name == "callers":
            tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"id": "c1", "name": "Asha", "active": True, "shift_start_hour": 9, "shift_end_hour": 18, "user_id": "u-caller"}]
            )
        elif name == "tenant_users":
            tenant_users_calls["n"] += 1
            if tenant_users_calls["n"] == 1:
                # owner lookup
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data={"user_id": "u-owner", "created_at": "2026-01-01T00:00:00+00:00"}
                )
            else:
                # role map
                tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"user_id": "u-caller", "role": "caller"}, {"user_id": "u-owner", "role": "owner"}]
                )
        return tbl

    db.table.side_effect = table
    return db


class ClientTeamGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _get(self, calling_provider):
        with patch("app.routes.operator.get_supabase", return_value=_db()), \
             patch("app.routes.operator.get_telecalling_config", return_value={"calling_provider": calling_provider}), \
             patch("app.services.telecaller_performance.period_stats", return_value={"c1": {"avg_score": 91.5}}):
            return self.client.get(f"/api/v1/operator/clients/{TENANT_ID}/team")

    def test_sim_client_has_no_avg_score_but_keeps_activity(self):
        res = self._get("sim_basic")
        body = res.json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body["calling_provider"], "sim_basic")
        caller = body["callers"][0]
        self.assertNotIn("avg_score_month", caller)
        self.assertEqual(caller["name"], "Asha")
        self.assertTrue(caller["active"])

    def test_telecmi_client_is_unchanged(self):
        res = self._get("telecmi")
        body = res.json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body["calling_provider"], "telecmi")
        self.assertEqual(body["callers"][0]["avg_score_month"], 91.5)


if __name__ == "__main__":
    unittest.main()
