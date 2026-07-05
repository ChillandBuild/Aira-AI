"""
Tests for `check_quota`. During the current unlimited phase, included counters
are informational only; only an explicit hard_cap blocks.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import check_quota


def _row(data):
    result = MagicMock()
    result.data = data
    return result


class CheckQuotaTests(unittest.TestCase):
    def _make_db(self, counter_row):
        tbl = MagicMock()
        # tenant_subscriptions lookup (single .eq) inside get_billing_period,
        # called before the counter read — no anchor configured, so it falls
        # back to the plain calendar-month period key.
        tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _row(None)
        # tenant_usage_counters lookup (three .eq calls) — the actual quota row.
        tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _row(counter_row)
        db = MagicMock()
        db.table.return_value = tbl
        return db

    def test_no_counter_row_is_unlimited_for_now(self):
        db = self._make_db(None)
        self.assertTrue(check_quota(db, "tenant-1", "message_sent"))

    def test_included_zero_is_unlimited_without_hard_cap(self):
        db = self._make_db({"used": 0, "included": 0, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent"))

    def test_hard_cap_blocks_even_when_included_zero(self):
        db = self._make_db({"used": 10, "included": 0, "hard_cap": 10})
        self.assertFalse(check_quota(db, "tenant-1", "message_sent"))

    def test_under_included_is_allowed(self):
        db = self._make_db({"used": 500, "included": 1000, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent"))

    def test_delta_pushing_past_included_is_allowed_without_hard_cap(self):
        db = self._make_db({"used": 999, "included": 1000, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent", delta=5))

    def test_exactly_at_included_after_delta_is_allowed(self):
        db = self._make_db({"used": 995, "included": 1000, "hard_cap": None})
        self.assertTrue(check_quota(db, "tenant-1", "message_sent", delta=5))

    def test_does_not_mutate_state(self):
        db = self._make_db({"used": 0, "included": 1000, "hard_cap": None})
        check_quota(db, "tenant-1", "message_sent")
        db.table.return_value.upsert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
