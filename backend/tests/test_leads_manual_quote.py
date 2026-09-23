"""Tests for POST /api/v1/leads/{lead_id}/quote -- manual deal entry for a
sale with no WhatsApp trail (phone call, walk-in, cash). A human confirming
a real sale is enough to log it, and enough to deduct stock when it's tied
to a catalog item -- unlike an AI catalog quote, which is interest, not a
confirmed sale, and never deducts.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routes import leads as leads_route
from app.dependencies.auth import get_current_user

LEAD_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "22222222-2222-2222-2222-222222222222"


class ManualQuoteRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[leads_route.require_leads_manage] = lambda: {
            "tenant_id": "tenant-1", "user_id": "user-1", "role": "owner", "permissions": [],
        }
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _db_with_lead_found(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "leads":
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data={"id": LEAD_ID}
                )
            elif name == "catalog_quotes":
                tbl.upsert.return_value.execute.return_value = MagicMock(data=[{}])
            return tbl

        db.table.side_effect = table
        return db

    @patch("app.routes.leads.get_supabase")
    def test_records_a_manual_sale_with_no_catalog_item(self, mock_get_db):
        db = self._db_with_lead_found()
        mock_get_db.return_value = db

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "Custom framing job", "amount_paise": 150000,
        })

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"recorded": True, "stock_warning": False})
        upsert_payload = db.table.return_value.upsert.call_args
        # side_effect means db.table.return_value is the LAST table() call's
        # return, i.e. catalog_quotes -- check the real call args instead.
        calls = [c for c in db.table.mock_calls if c[1] == ("catalog_quotes",)]
        self.assertTrue(calls)

    @patch("app.routes.leads.get_supabase")
    def test_lead_not_found_for_this_tenant_is_404(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        mock_get_db.return_value = db

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "Something", "amount_paise": 1000,
        })

        self.assertEqual(res.status_code, 404)

    @patch("app.routes.leads.get_supabase")
    def test_negative_amount_is_400(self, mock_get_db):
        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "Something", "amount_paise": -1,
        })
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.leads.get_supabase")
    def test_zero_qty_is_400(self, mock_get_db):
        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "Something", "amount_paise": 1000, "qty": 0,
        })
        self.assertEqual(res.status_code, 400)

    @patch("app.services.catalog_stock.decrement_stock")
    @patch("app.routes.leads.get_supabase")
    def test_catalog_item_with_enough_stock_deducts_and_no_warning(self, mock_get_db, mock_decrement):
        db = self._db_with_lead_found()
        mock_get_db.return_value = db
        mock_decrement.return_value = True

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "DSLR Bag", "amount_paise": 320000, "catalog_item_id": ITEM_ID, "qty": 2,
        })

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["stock_warning"])
        mock_decrement.assert_called_once_with("tenant-1", ITEM_ID, 2, db=db)

    @patch("app.services.catalog_stock.decrement_stock")
    @patch("app.routes.leads.get_supabase")
    def test_insufficient_stock_still_records_the_sale_but_warns(self, mock_get_db, mock_decrement):
        """A human confirming a real sale happened must not be blocked by the
        stock count disagreeing -- the sale is recorded either way, just
        flagged so the owner knows to check inventory."""
        db = self._db_with_lead_found()
        mock_get_db.return_value = db
        mock_decrement.return_value = False

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "DSLR Bag", "amount_paise": 320000, "catalog_item_id": ITEM_ID,
        })

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["recorded"])
        self.assertTrue(res.json()["stock_warning"])

    @patch("app.services.catalog_stock.decrement_stock")
    @patch("app.routes.leads.get_supabase")
    def test_stock_deduction_error_does_not_fail_the_sale(self, mock_get_db, mock_decrement):
        db = self._db_with_lead_found()
        mock_get_db.return_value = db
        mock_decrement.side_effect = Exception("db unreachable")

        res = self.client.post(f"/api/v1/leads/{LEAD_ID}/quote", json={
            "item_name": "DSLR Bag", "amount_paise": 320000, "catalog_item_id": ITEM_ID,
        })

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["recorded"])
        self.assertTrue(res.json()["stock_warning"])


if __name__ == "__main__":
    unittest.main()
