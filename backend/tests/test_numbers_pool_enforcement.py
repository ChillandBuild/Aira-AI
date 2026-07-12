"""Phone numbers are unlimited for now; creating a number should not be gated."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


class NumbersPoolEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_supabase")
    def test_create_number_does_not_block_on_purchased_quantity(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.count = 1
        db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "num-1", "number": "+919999999999"}]
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_supabase")
    def test_allowed_when_under_purchased_quantity(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.count = 1
        db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "num-1", "number": "+919999999999"}]
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
