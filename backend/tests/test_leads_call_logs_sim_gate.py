"""GET /api/v1/leads/{lead_id}/call-logs: SIM clients get no evaluation at all --
the lead's call history must not carry score/evaluation fields either."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id

LEAD_ID = "0761bbde-8626-42c3-963e-327f162ca37e"


class LeadCallLogsGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "t-1"

    def tearDown(self):
        app.dependency_overrides.clear()

    def _get(self, calling_provider):
        db = MagicMock()
        chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = MagicMock(data=[{
            "id": "c1", "score": 82.0, "score_status": "scored", "score_final": True,
            "evaluation": {"checks": []}, "call_group": "real_conversation", "talk_share": 0.6,
            "interruption_count": 1, "interruptions_per_5min": 0.5,
        }])
        with patch("app.routes.leads.get_supabase", return_value=db), \
             patch("app.routes.leads.get_telecalling_config", return_value={"calling_provider": calling_provider}):
            return self.client.get(f"/api/v1/leads/{LEAD_ID}/call-logs")

    def test_sim_lead_call_logs_have_no_evaluation_fields(self):
        row = self._get("sim_basic").json()["data"][0]
        for field in ("score", "score_status", "score_final", "evaluation", "call_group", "talk_share",
                      "interruption_count", "interruptions_per_5min"):
            self.assertNotIn(field, row)

    def test_telecmi_lead_call_logs_are_unchanged(self):
        row = self._get("telecmi").json()["data"][0]
        self.assertEqual(row["score"], 82.0)
        self.assertEqual(row["score_status"], "scored")


if __name__ == "__main__":
    unittest.main()
