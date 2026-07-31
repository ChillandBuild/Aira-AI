"""Phone number creation is capped at the tenant's purchased `numbers_pool` quantity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


def _mock_db(purchased_quantity, current_count):
    db = MagicMock()

    items_tbl = MagicMock()
    items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"quantity": purchased_quantity}] if purchased_quantity else []
    )

    numbers_tbl = MagicMock()
    numbers_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(count=current_count)
    numbers_tbl.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "num-1", "number": "+919999999999"}]
    )

    def table(name):
        return {"tenant_subscription_items": items_tbl, "phone_numbers": numbers_tbl}[name]

    db.table.side_effect = table
    return db


class NumbersPoolEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_supabase")
    def test_blocked_when_at_purchased_quantity(self, mock_get_db):
        mock_get_db.return_value = _mock_db(purchased_quantity=4, current_count=4)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("limit reached", res.json()["detail"].lower())

    @patch("app.routes.numbers.get_supabase")
    def test_allowed_when_under_purchased_quantity(self, mock_get_db):
        mock_get_db.return_value = _mock_db(purchased_quantity=4, current_count=2)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_supabase")
    def test_blocked_when_nothing_purchased(self, mock_get_db):
        mock_get_db.return_value = _mock_db(purchased_quantity=0, current_count=0)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("limit reached", res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
