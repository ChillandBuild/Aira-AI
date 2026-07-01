"""
Tests for the track-only, non-blocking usage metering wrapper `meter()`.

Contract under test (product decision): metering must NEVER block, cap, delay,
or break a send/reply/call. `meter()` must swallow any exception raised by
`increment_usage` and must no-op when tenant_id is empty or delta<=0.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import entitlements


class FakeDb:
    """Stand-in for a Supabase client — never actually touched because
    increment_usage is monkeypatched in every test below."""
    pass


class MeterNeverRaisesTests(unittest.TestCase):
    def test_swallows_exception_from_increment_usage(self):
        db = FakeDb()
        with patch.object(
            entitlements, "increment_usage", side_effect=RuntimeError("db is down")
        ) as mock_incr:
            try:
                result = entitlements.meter(db, "tenant-1", "ai_reply")
            except Exception as e:  # pragma: no cover - failure path
                self.fail(f"meter() must never raise, but raised: {e}")
            self.assertIsNone(result)
            mock_incr.assert_called_once_with(db, "tenant-1", "ai_reply", 1)

    def test_skips_when_tenant_id_empty(self):
        db = FakeDb()
        with patch.object(entitlements, "increment_usage") as mock_incr:
            entitlements.meter(db, "", "ai_reply")
            entitlements.meter(db, None, "ai_reply")
            mock_incr.assert_not_called()

    def test_skips_when_delta_not_positive(self):
        db = FakeDb()
        with patch.object(entitlements, "increment_usage") as mock_incr:
            entitlements.meter(db, "tenant-1", "message_sent", delta=0)
            entitlements.meter(db, "tenant-1", "message_sent", delta=-5)
            mock_incr.assert_not_called()

    def test_calls_increment_usage_on_happy_path(self):
        db = FakeDb()
        with patch.object(entitlements, "increment_usage", return_value={"used": 1}) as mock_incr:
            entitlements.meter(db, "tenant-1", "call_minute", delta=3)
            mock_incr.assert_called_once_with(db, "tenant-1", "call_minute", 3)


if __name__ == "__main__":
    unittest.main()
