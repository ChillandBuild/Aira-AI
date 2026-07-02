import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CreateClientEntitlementsChecks(unittest.TestCase):
    """
    Static/source-text checks for the create_client -> entitlements wiring.
    No Supabase client is instantiated here; these assertions just verify the
    route source contains the expected contracts (mirrors the pattern used in
    test_logic_contracts_static.py).
    """

    def setUp(self):
        self.source = read("backend/app/routes/operator.py")

    def test_only_one_setting_keys_definition_exists(self):
        matches = re.findall(r"^_SETTING_KEYS\s*[:=]", self.source, flags=re.MULTILINE)
        self.assertEqual(len(matches), 1, "Expected exactly one module-level _SETTING_KEYS definition")

    def test_tenant_insert_carries_contact_fields(self):
        self.assertIn('"business_type": payload.business_type', self.source)
        self.assertIn('"contact_name": payload.contact_name', self.source)
        self.assertIn('"contact_phone": payload.contact_phone', self.source)
        self.assertIn('"billing_region": payload.billing_region', self.source)

    def test_migration_adds_contact_columns(self):
        migration = read("backend/supabase/migrations/125_tenant_contact_columns.sql")
        for column in ("business_type", "contact_name", "contact_phone", "billing_region"):
            self.assertRegex(migration, rf"add column if not exists {column} text")

    def test_resolve_entitlements_runs_after_subscription_insert(self):
        sub_insert_idx = self.source.index('db.table("tenant_subscriptions").insert(')
        resolve_idx = self.source.index("resolve_entitlements(db, tenant_id)")
        self.assertGreater(resolve_idx, sub_insert_idx)

    def test_usage_counter_metric_mapping(self):
        expected_mapping = {
            "message_sent": 'quotas.get("message_sent", 0)',
            "ai_reply": 'quotas.get("ai_reply", 0)',
            "call_minute": 'quotas.get("call_minute", 0)',
            "team_seat_active": 'quotas.get("team_seat_active", 0)',
            "storage_gb": 'quotas.get("storage_gb", 0)',
            "ai_call_summary": 'quotas.get("ai_call_summary", 0)',
            "ai_call_scoring": 'quotas.get("ai_call_scoring", 0)',
        }
        for metric, quota_expr in expected_mapping.items():
            self.assertRegex(self.source, rf'"{metric}":\s*{re.escape(quota_expr)}')

    def test_usage_counters_seeded_in_single_insert_call(self):
        self.assertIn('db.table("tenant_usage_counters").insert(', self.source)
        # only one insert call against tenant_usage_counters in create_client
        self.assertEqual(self.source.count('db.table("tenant_usage_counters").insert('), 1)

    def test_cleanup_on_failure_deletes_orphaned_auth_user(self):
        self.assertIn("except Exception as e:", self.source)
        self.assertIn("db.auth.admin.delete_user(user_id)", self.source)
        self.assertIn('detail="Client setup failed; user account cleaned up."', self.source)


if __name__ == "__main__":
    unittest.main()
