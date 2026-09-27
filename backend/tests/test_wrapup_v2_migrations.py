"""Migration contract: 208 widens to old ∪ new and adds columns; 209 narrows to exactly the new sets."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import call_wrapup as cw

OLD_OUTCOMES = {"converted", "interested", "callback", "not_interested", "no_answer"}
OLD_MANUAL = {"connected", "not_picked", "busy", "wrong_number", "interested", "not_interested", "callback"}
OLD_LEAD = {"new", "in_progress", "callback", "converted", "not_interested", "dnc", "unreachable"}


def check_values(sql: str, name: str) -> set[str]:
    match = re.search(rf"ADD CONSTRAINT {name} CHECK \((.*?)\);", sql, re.S)
    assert match, f"{name} not found"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


class Migration208Tests(unittest.TestCase):
    sql = (ROOT / "supabase/migrations/208_call_wrapup_v2_widen.sql").read_text(encoding="utf-8")

    def test_outcome_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "call_logs_outcome_check"), OLD_OUTCOMES | set(cw.OUTCOMES))

    def test_manual_status_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "call_logs_manual_status_check"), OLD_MANUAL | set(cw.CONNECTS))

    def test_lead_call_status_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "leads_call_status_check"), OLD_LEAD | set(cw.LEAD_CALL_STATUSES))

    def test_new_columns_and_their_checks(self):
        for col in ("outcome_reason text", "preferred_language text", "next_action_at timestamptz", "ai_call_status text"):
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {col}", self.sql)
        self.assertEqual(check_values(self.sql, "call_logs_outcome_reason_check"), set(cw.REASONS))
        self.assertEqual(check_values(self.sql, "call_logs_preferred_language_check"), set(cw.LANGUAGES))
        self.assertEqual(check_values(self.sql, "call_logs_ai_call_status_check"), set(cw.AI_CALL_STATUSES))

    def test_safe_before_deploy(self):
        self.assertNotIn("DROP COLUMN", self.sql.upper())
        self.assertNotIn("UPDATE ", self.sql.upper())


if __name__ == "__main__":
    unittest.main()
