"""Tests for the subscription request submit/approve/reject service (migration 128)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.subscription_requests import submit_request, approve_request, reject_request


def _result(data):
    r = MagicMock()
    r.data = data
    return r


class SubmitRequestTests(unittest.TestCase):
    def test_computes_total_from_catalog_prices_and_creates_pending_subscription(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "feature_catalog":
                tbl.select.return_value.in_.return_value.execute.return_value = _result([
                    {"feature_key": "inbound_messaging", "monthly_price": 1500, "unit_price": None},
                    {"feature_key": "telecaller_seats", "monthly_price": 0, "unit_price": 199},
                ])
            elif name == "subscription_requests":
                tbl.insert.return_value.execute.return_value = _result([{"id": "req-1", "status": "submitted"}])
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(None)
            return tbl

        db.table.side_effect = table

        result = submit_request(
            db, "tenant-1",
            requested_items=[
                {"feature_key": "inbound_messaging", "quantity": 1},
                {"feature_key": "telecaller_seats", "quantity": 3},
            ],
        )

        # base 1500 + 3 seats * 199 = 2097
        self.assertEqual(result["total_amount"], 2097)
        self.assertEqual(result["id"], "req-1")

        subs_table = [c for c in db.table.call_args_list if c == call("tenant_subscriptions")]
        self.assertTrue(subs_table)


class ApproveRequestTests(unittest.TestCase):
    def test_approve_upserts_items_and_activates_subscription(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "subscription_requests":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result({
                    "id": "req-1", "tenant_id": "tenant-1", "status": "submitted",
                    "requested_items": [{"feature_key": "inbound_messaging", "quantity": 1, "unit_price": 1500}],
                    "package_id": None, "total_amount": 1500,
                })
                tbl.update.return_value.eq.return_value.execute.return_value = _result([{"id": "req-1", "status": "approved"}])
            elif name == "tenant_subscription_items":
                tbl.upsert.return_value.execute.return_value = _result([{"feature_key": "inbound_messaging", "quantity": 1}])
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(None)
                # Single-.eq() chain is shared by resolve_entitlements' item
                # lookup and approve_request's final mrr-sum lookup — give it
                # a row shape that satisfies both readers.
                tbl.select.return_value.eq.return_value.execute.return_value = _result([
                    {"feature_key": "inbound_messaging", "quantity": 1, "unit_price_snapshot": 1500}
                ])
            elif name == "feature_catalog":
                tbl.select.return_value.execute.return_value = _result([])
            return tbl

        db.table.side_effect = table

        result = approve_request(db, "req-1", reviewer_user_id="admin-1")
        self.assertEqual(result["status"], "approved")

        self.assertIn(call("tenant_subscription_items"), db.table.call_args_list)
        self.assertIn(call("tenant_subscriptions"), db.table.call_args_list)


class RejectRequestTests(unittest.TestCase):
    def test_reject_sets_status_and_reason_without_touching_items(self):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "subscription_requests":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result({
                    "id": "req-1", "tenant_id": "tenant-1", "status": "submitted",
                })
                tbl.update.return_value.eq.return_value.execute.return_value = _result([{"id": "req-1", "status": "rejected"}])
            return tbl

        db.table.side_effect = table

        result = reject_request(db, "req-1", reviewer_user_id="admin-1", reason="Payment not received")
        self.assertEqual(result["status"], "rejected")
        self.assertNotIn(call("tenant_subscription_items"), db.table.call_args_list)


if __name__ == "__main__":
    unittest.main()
