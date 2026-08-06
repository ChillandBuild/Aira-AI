"""Pure lock-slot algorithm: primary always wins a slot, remaining slots
fill oldest-first among the rest, and nothing is auto-filled without a
primary present."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.numbers_pool import compute_unlocked_ids, normalize_phone_number


class ComputeUnlockedIdsTests(unittest.TestCase):
    def test_no_primary_locks_everything_regardless_of_limit(self):
        rows = [
            {"id": "a", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "c", "role": "standby", "created_at": "2026-01-03T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=1), set())
        self.assertEqual(compute_unlocked_ids(rows, limit=3), set())

    def test_primary_always_unlocked_even_if_not_oldest(self):
        rows = [
            {"id": "a", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "primary", "created_at": "2026-01-05T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=1), {"b"})

    def test_remaining_slots_fill_oldest_first_among_non_primary(self):
        rows = [
            {"id": "primary", "role": "primary", "created_at": "2026-01-10T00:00:00Z"},
            {"id": "oldest", "role": "standby", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "middle", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "newest", "role": "standby", "created_at": "2026-01-03T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=2), {"primary", "oldest"})
        self.assertEqual(compute_unlocked_ids(rows, limit=3), {"primary", "oldest", "middle"})

    def test_limit_zero_locks_everything_including_primary(self):
        rows = [{"id": "a", "role": "primary", "created_at": "2026-01-01T00:00:00Z"}]
        self.assertEqual(compute_unlocked_ids(rows, limit=0), set())

    def test_limit_exceeds_row_count_unlocks_all(self):
        rows = [
            {"id": "a", "role": "primary", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "role": "standby", "created_at": "2026-01-02T00:00:00Z"},
        ]
        self.assertEqual(compute_unlocked_ids(rows, limit=10), {"a", "b"})


class NormalizePhoneNumberTests(unittest.TestCase):
    def test_strips_spaces_and_dashes_keeps_leading_plus(self):
        self.assertEqual(normalize_phone_number("+91 98765-43210"), "+919876543210")

    def test_no_leading_plus_stays_bare_digits(self):
        self.assertEqual(normalize_phone_number("919876543210"), "919876543210")

    def test_handles_empty_string(self):
        self.assertEqual(normalize_phone_number(""), "")


if __name__ == "__main__":
    unittest.main()
