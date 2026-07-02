"""
Tests for `resolve_entitlements`, which looks up a tenant's single assigned
plan and returns its feature_keys/quotas. Replaces the old
messaging-plan + telecalling-plan + ai_tier merge logic (migration 127).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import resolve_entitlements


def _single(data):
    result = MagicMock()
    result.data = data
    return result


class ResolveEntitlementsTests(unittest.TestCase):
    def _make_db(self, tenant_data, subscription_data, plan_data):
        responses = {
            "tenants": tenant_data,
            "tenant_subscriptions": subscription_data,
            "plans": plan_data,
        }

        def table(name):
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                _single(responses[name])
            return tbl

        db = MagicMock()
        db.table.side_effect = table
        return db

    def test_no_tenant_returns_empty(self):
        db = self._make_db(None, None, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_tenant_with_no_subscription_row_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, None, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_subscription_with_no_plan_id_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, {"plan_id": None}, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})

    def test_assigned_plan_returns_its_features_and_quotas(self):
        db = self._make_db(
            {"id": "tenant-1"},
            {"plan_id": "plan-1"},
            {"feature_keys": ["whatsapp", "broadcast"], "quotas": {"message_sent": 1000, "ai_reply": 500}},
        )
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result["features"], ["whatsapp", "broadcast"])
        self.assertEqual(result["quotas"], {"message_sent": 1000, "ai_reply": 500})

    def test_plan_id_pointing_at_deleted_plan_returns_empty(self):
        db = self._make_db({"id": "tenant-1"}, {"plan_id": "plan-gone"}, None)
        result = resolve_entitlements(db, "tenant-1")
        self.assertEqual(result, {"features": [], "quotas": {}})


if __name__ == "__main__":
    unittest.main()
