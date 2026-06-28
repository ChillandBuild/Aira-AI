import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class LogicContractChecks(unittest.TestCase):
    def test_manual_lead_source_is_allowed_by_schema(self):
        schemas = read("backend/app/models/schemas.py")
        migration = read("backend/supabase/migrations/033_tenant_contract_fixes.sql")

        self.assertIn('"manual"', schemas)
        self.assertRegex(migration, r"source\s+in\s+\([^)]*'manual'")

    def test_bulk_send_does_not_write_invalid_reply_source(self):
        upload = read("backend/app/routes/upload.py")

        self.assertNotIn('"reply_source": "template_broadcast"', upload)

    def test_outbound_number_selection_is_tenant_scoped_and_uses_actual_tiers(self):
        router = read("backend/app/services/outbound_router.py")
        upload = read("backend/app/routes/upload.py")

        self.assertRegex(router, r"async def get_best_number\(tenant_id: str\)")
        self.assertIn('.eq("tenant_id", tenant_id)', router)
        self.assertIn("_TIER_DAILY_LIMITS: dict[int, int] = {1000: 1_000, 10000: 10_000, 100000: 100_000}", router)
        self.assertIn("get_best_number(tenant_id)", upload)

    def test_tenant_uniqueness_migration_uses_composite_keys(self):
        migration = read("backend/supabase/migrations/033_tenant_contract_fixes.sql")

        self.assertRegex(migration, r"UNIQUE\s*\(tenant_id,\s*phone\)")
        self.assertRegex(migration, r"UNIQUE\s*\(tenant_id,\s*name\)")
        self.assertRegex(migration, r"PRIMARY KEY\s*\(tenant_id,\s*key\)")

    def test_settings_upserts_are_tenant_key_conflicts(self):
        assignment = read("backend/app/services/assignment.py")
        failover = read("backend/app/services/failover.py")

        self.assertIn('on_conflict="tenant_id,key"', assignment)
        self.assertIn('on_conflict="tenant_id,key"', failover)

    def test_opt_out_lookup_is_tenant_scoped(self):
        webhook = read("backend/app/routes/webhook.py")

        self.assertRegex(webhook, r"def _handle_opt_out\(phone: str, tenant_id: str, db\)")
        self.assertRegex(webhook, r'\.eq\("tenant_id", tenant_id\)')


if __name__ == "__main__":
    unittest.main()
