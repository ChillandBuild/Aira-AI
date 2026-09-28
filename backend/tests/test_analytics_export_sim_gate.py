"""GET /api/v1/analytics/telecalling/export: SIM clients get no evaluation at
all -- the CSV must not carry score/score_status columns either."""
import csv
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class ExportSimGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "owner", "user_id": "user-1", "caller_id": None, "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _export(self, calling_provider):
        db = MagicMock()
        chain = db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
        chain.execute.return_value = MagicMock(data=[{
            "id": "c1", "created_at": "2026-09-28T05:00:00+00:00", "caller_id": "cid",
            "duration_seconds": 90, "outcome": "converted", "score": 82.0, "score_status": "scored",
        }])
        with patch("app.routes.analytics.get_supabase", return_value=db), \
             patch("app.routes.analytics.get_telecalling_config", return_value={"calling_provider": calling_provider}):
            res = self.client.get("/api/v1/analytics/telecalling/export")
        rows = list(csv.DictReader(io.StringIO(res.text)))
        return rows[0]

    def test_sim_export_has_no_score_columns(self):
        row = self._export("sim_basic")
        self.assertNotIn("score", row)
        self.assertNotIn("score_status", row)

    def test_telecmi_export_is_unchanged(self):
        row = self._export("telecmi")
        self.assertEqual(row["score"], "82.0")
        self.assertEqual(row["score_status"], "scored")


if __name__ == "__main__":
    unittest.main()
