"""Phone number creation is capped at 1 free number per purchased messaging
module (inbound/outbound) plus any additionally purchased `numbers_pool`
quantity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


def _mock_db(purchased_quantity, current_count, has_messaging_module=False):
    db = MagicMock()

    # `_numbers_pool_limit` reads `tenant_subscription_items` two different
    # ways: `resolve_entitlements` (select(...).eq(tenant_id).execute(), no
    # feature_key filter -- used to detect the free messaging-module
    # baseline) and `get_purchased_quantity` (select(...).eq(tenant_id)
    # .eq(feature_key).execute() -- the additionally-purchased top-up
    # quantity). Both hit the same table mock at different points in the
    # chain, so no conflict.
    items_tbl = MagicMock()
    entitlement_items = []
    if has_messaging_module:
        entitlement_items.append({"feature_key": "outbound_messaging", "quantity": 1})
    if purchased_quantity:
        entitlement_items.append({"feature_key": "numbers_pool", "quantity": purchased_quantity})
    items_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=entitlement_items)
    items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"quantity": purchased_quantity}] if purchased_quantity else []
    )

    catalog_tbl = MagicMock()
    catalog_tbl.select.return_value.execute.return_value = MagicMock(data=[])

    numbers_tbl = MagicMock()
    numbers_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(count=current_count)
    numbers_tbl.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "num-1", "number": "+919999999999"}]
    )

    def table(name):
        return {
            "tenant_subscription_items": items_tbl,
            "feature_catalog": catalog_tbl,
            "phone_numbers": numbers_tbl,
        }[name]

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

    @patch("app.routes.numbers.get_supabase")
    def test_messaging_module_grants_one_free_number_with_no_topup(self, mock_get_db):
        # Buying inbound/outbound messaging includes 1 free phone number --
        # no numbers_pool top-up purchased at all, still 1 number allowed.
        mock_get_db.return_value = _mock_db(purchased_quantity=0, current_count=0, has_messaging_module=True)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.numbers.get_supabase")
    def test_messaging_module_free_number_blocked_after_first_use(self, mock_get_db):
        # The 1 free number from the messaging module is already used (1
        # existing number, 0 additionally purchased) -- a 2nd must be blocked.
        mock_get_db.return_value = _mock_db(purchased_quantity=0, current_count=1, has_messaging_module=True)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("(1/1)", res.json()["detail"])

    @patch("app.routes.numbers.get_supabase")
    def test_messaging_module_free_number_plus_topup(self, mock_get_db):
        # Messaging module's free number + 1 additionally purchased = 2 total.
        mock_get_db.return_value = _mock_db(purchased_quantity=1, current_count=1, has_messaging_module=True)

        res = self.client.post("/api/v1/numbers/", json={
            "number": "+919999999999", "display_name": "Test Number",
        })
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
