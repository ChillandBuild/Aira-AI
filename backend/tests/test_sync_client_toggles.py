import sys
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.subscription_requests import sync_client_toggles


def _query(data):
    result = MagicMock()
    result.data = data
    return result


class SyncClientTogglesTests(unittest.TestCase):
    def test_sync_client_toggles_with_active_features(self):
        # Given a tenant with inbound_messaging + telecalling_sim active
        # and pre-existing unrelated "analytics" feature toggle
        db = MagicMock()
        
        # We need to capture updates/upserts
        tenant_updates = []
        app_settings_upserts = []

        def table(name):
            tbl = MagicMock()
            if name == "tenant_subscription_items":
                # Called by:
                # 1) resolve_entitlements
                # 2) sync_client_toggles to check active provider
                tbl.select.return_value.eq.return_value.execute.side_effect = [
                    _query([
                        {"feature_key": "inbound_messaging", "quantity": 1},
                        {"feature_key": "telecalling_sim", "quantity": 1}
                    ]),
                    _query([
                        {"feature_key": "inbound_messaging"},
                        {"feature_key": "telecalling_sim"}
                    ])
                ]
            elif name == "feature_catalog":
                # Called by:
                # 1) resolve_entitlements
                # 2) sync_client_toggles to collect BILLING_DERIVED_KEYS
                tbl.select.return_value.execute.side_effect = [
                    _query([
                        {"feature_key": "inbound_messaging", "depends_on": ["inbound_leads", "push_notifications"]},
                        {"feature_key": "outbound_messaging", "depends_on": ["outbound_leads"]},
                        {"feature_key": "telecalling_sim", "depends_on": ["telecalling", "telecalling.dialer", "telecalling.scheduled", "telecalling.notes"]},
                    ]),
                    _query([
                        {"feature_key": "inbound_messaging", "depends_on": ["inbound_leads", "push_notifications"]},
                        {"feature_key": "outbound_messaging", "depends_on": ["outbound_leads"]},
                        {"feature_key": "telecalling_sim", "depends_on": ["telecalling", "telecalling.dialer", "telecalling.scheduled", "telecalling.notes"]},
                    ])
                ]
            elif name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _query({
                    "enabled_features": ["analytics", "outbound_leads"]
                })
                # Capture the update parameters
                tbl.update.side_effect = lambda data: MagicMock(eq=lambda *args, **kwargs: MagicMock(execute=lambda: tenant_updates.append(data)))
            elif name == "app_settings":
                # Return default telecalling config
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _query({
                    "value": json.dumps({
                        "enabled": False,
                        "calling_provider": "telecmi",
                        "segments": ["A"]
                    })
                })
                # Capture the upsert parameters
                tbl.upsert.side_effect = lambda data, on_conflict: MagicMock(execute=lambda: app_settings_upserts.append(data))
            return tbl

        db.table.side_effect = table

        sync_client_toggles(db, "tenant-1")

        # Assertions:
        # 1. New features list must contain:
        # - inbound_messaging, inbound_leads, push_notifications (derived from inbound_messaging)
        # - telecalling_sim, telecalling, telecalling.dialer, telecalling.scheduled, telecalling.notes (derived from telecalling_sim)
        # - analytics (pre-existing, not billing derived)
        # - must NOT contain outbound_leads (billing derived, but outbound_messaging is not in entitlements)
        self.assertEqual(len(tenant_updates), 1)
        new_features = tenant_updates[0]["enabled_features"]
        
        self.assertIn("analytics", new_features)
        self.assertIn("inbound_messaging", new_features)
        self.assertIn("inbound_leads", new_features)
        self.assertIn("push_notifications", new_features)
        self.assertIn("telecalling_sim", new_features)
        self.assertIn("telecalling", new_features)
        self.assertIn("telecalling.dialer", new_features)
        
        self.assertNotIn("outbound_leads", new_features)

        # 2. Calling provider must be updated to "sim_basic" (since telecalling_sim is active and telecalling_telecmi is not)
        self.assertEqual(len(app_settings_upserts), 1)
        config_val = json.loads(app_settings_upserts[0]["value"])
        self.assertEqual(config_val["calling_provider"], "sim_basic")

    def test_sync_client_toggles_turns_billing_features_off(self):
        # Simulates a tenant with NO telecalling subscription item anymore.
        # Verify that telecalling-related features are correctly turned off.
        db = MagicMock()
        tenant_updates = []

        def table(name):
            tbl = MagicMock()
            if name == "tenant_subscription_items":
                tbl.select.return_value.eq.return_value.execute.side_effect = [
                    _query([
                        {"feature_key": "inbound_messaging", "quantity": 1}
                    ]),
                    _query([
                        {"feature_key": "inbound_messaging"}
                    ])
                ]
            elif name == "feature_catalog":
                tbl.select.return_value.execute.side_effect = [
                    _query([
                        {"feature_key": "inbound_messaging", "depends_on": ["inbound_leads"]},
                        {"feature_key": "telecalling_sim", "depends_on": ["telecalling"]},
                    ]),
                    _query([
                        {"feature_key": "inbound_messaging", "depends_on": ["inbound_leads"]},
                        {"feature_key": "telecalling_sim", "depends_on": ["telecalling"]},
                    ])
                ]
            elif name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _query({
                    "enabled_features": ["analytics", "telecalling", "inbound_leads"]
                })
                tbl.update.side_effect = lambda data: MagicMock(eq=lambda *args, **kwargs: MagicMock(execute=lambda: tenant_updates.append(data)))
            elif name == "app_settings":
                tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _query(None)
            return tbl

        db.table.side_effect = table

        sync_client_toggles(db, "tenant-1")

        self.assertEqual(len(tenant_updates), 1)
        new_features = tenant_updates[0]["enabled_features"]
        
        self.assertIn("analytics", new_features)
        self.assertIn("inbound_leads", new_features)
        self.assertNotIn("telecalling", new_features)


if __name__ == "__main__":
    unittest.main()
