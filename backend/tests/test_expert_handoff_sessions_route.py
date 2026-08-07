import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class ExpertHandoffSessionsListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.expert_handoff.get_supabase")
    def test_lists_sessions_for_the_requested_bucket(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = [
            {"id": "sess-1", "lead_id": "lead-1", "status": "awaiting_payment",
             "collected_data": {"name": "Priya"}, "amount_paise": 2900,
             "payment_link": "https://rzp.io/x", "paid_at": None,
             "created_at": "2026-08-07T00:00:00Z", "leads": {"name": "Priya", "phone": "+919876543210"}},
        ]
        chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=awaiting_payment")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["leads"]["name"], "Priya")
        db.table.return_value.select.return_value.eq.assert_any_call("tenant_id", "t-1")

    @patch("app.routes.expert_handoff.get_supabase")
    def test_rejects_invalid_bucket(self, mock_get_db):
        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=collecting")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.expert_handoff.get_supabase")
    def test_empty_bucket_returns_empty_list_not_error(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = []
        chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=paid")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"data": []})


if __name__ == "__main__":
    unittest.main()
