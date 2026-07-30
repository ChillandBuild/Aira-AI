"""Unit tests for app/services/analytics_compare.py -- pure period math, no DB."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analytics_compare import resolve_period, previous_period


class ResolvePeriodTests(unittest.TestCase):
    TODAY = date(2026, 7, 30)

    def test_this_month_runs_from_the_first_to_today(self):
        self.assertEqual(
            resolve_period("this_month", None, None, self.TODAY),
            (date(2026, 7, 1), date(2026, 7, 30)),
        )

    def test_last_month_is_the_whole_previous_calendar_month(self):
        self.assertEqual(
            resolve_period("last_month", None, None, self.TODAY),
            (date(2026, 6, 1), date(2026, 6, 30)),
        )

    def test_last_7d_includes_today_and_spans_seven_days(self):
        start, end = resolve_period("last_7d", None, None, self.TODAY)
        self.assertEqual((start, end), (date(2026, 7, 24), date(2026, 7, 30)))
        self.assertEqual((end - start).days + 1, 7)

    def test_last_14d_spans_fourteen_days(self):
        start, end = resolve_period("last_14d", None, None, self.TODAY)
        self.assertEqual((start, end), (date(2026, 7, 17), date(2026, 7, 30)))

    def test_custom_uses_the_supplied_dates(self):
        self.assertEqual(
            resolve_period("custom", "2026-03-05", "2026-03-19", self.TODAY),
            (date(2026, 3, 5), date(2026, 3, 19)),
        )

    def test_custom_without_dates_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("custom", None, None, self.TODAY)

    def test_reversed_custom_range_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("custom", "2026-03-19", "2026-03-05", self.TODAY)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("since_the_dawn_of_time", None, None, self.TODAY)


class PreviousPeriodTests(unittest.TestCase):
    def test_month_preset_compares_to_the_previous_calendar_month(self):
        # July 1-30 vs June 1-30 -- calendar months, not "the 30 days before".
        self.assertEqual(
            previous_period(date(2026, 7, 1), date(2026, 7, 30), "this_month"),
            (date(2026, 6, 1), date(2026, 6, 30)),
        )

    def test_custom_range_compares_to_the_immediately_preceding_equal_block(self):
        # 14 days (Jul 17-30) -> the 14 days before it (Jul 3-16), no overlap.
        self.assertEqual(
            previous_period(date(2026, 7, 17), date(2026, 7, 30), "custom"),
            (date(2026, 7, 3), date(2026, 7, 16)),
        )

    def test_previous_block_never_overlaps_the_current_one(self):
        prev_start, prev_end = previous_period(date(2026, 7, 24), date(2026, 7, 30), "last_7d")
        self.assertLess(prev_end, date(2026, 7, 24))

    def test_single_day_compares_to_the_day_before(self):
        self.assertEqual(
            previous_period(date(2026, 7, 30), date(2026, 7, 30), "custom"),
            (date(2026, 7, 29), date(2026, 7, 29)),
        )


if __name__ == "__main__":
    unittest.main()
