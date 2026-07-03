"""
Tests for `resolve_entitlements`, rewritten for the itemized-cart model
(migration 128). A tenant's entitlements now come from
`tenant_subscription_items` joined against `feature_catalog` (for
`depends_on` and `usage_metric`/`included_qty`), not a single `plans.plan_id`.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import resolve_entitlements


def _query(data):
    result = MagicMock()
    result.data = data
    return result


class ResolveEntitlementsTests(unittest.TestCase):
    def _make_db(self, items_data, catalog_data):
        def table(name):
            tbl = MagicMock()
            if name == "tenant_subscription_items":
                tbl.select.return_value.eq.return_value.execute.return_value = _query(items_data)
            elif name == "feature_catalog":
                tbl.select.return_value.execute.return_value = _query(catalog_data)
            return tbl

        db = MagicMock()
        db.table.side_effect = table
        return db

    def test_no_items_returns_empty(self):
        db = self._make_db([], [])
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_flat_item_with_no_dependents_enables_only_itself(self):
        db = self._make_db(
            [{"feature_key": "notifications", "quantity": 1}],
            [{"feature_key": "notifications", "depends_on": ["push_notifications", "callbacks"], "usage_metric": None, "included_qty": None}],
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(sorted(result["features"]), ["callbacks", "notifications", "push_notifications"])
        self.assertEqual(result["quotas"], {})

    def test_metered_item_multiplies_included_qty_by_quantity(self):
        db = self._make_db(
            [{"feature_key": "outbound_messaging", "quantity": 2}],
            [{"feature_key": "outbound_messaging", "depends_on": ["whatsapp"], "usage_metric": "message_sent", "included_qty": 1000}],
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(sorted(result["features"]), ["outbound_messaging", "whatsapp"])
        self.assertEqual(result["quotas"], {"message_sent": 2000})

    def test_item_not_in_catalog_is_still_enabled_but_contributes_no_quota(self):
        db = self._make_db([{"feature_key": "ghost_item", "quantity": 1}], [])
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result["features"], ["ghost_item"])
        self.assertEqual(result["quotas"], {})


if __name__ == "__main__":
    unittest.main()
