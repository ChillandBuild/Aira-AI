"""Unit tests for app/services/analytics_compare.py -- pure period math, no DB."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analytics_compare import (
    align_series,
    build_deltas,
    build_summary,
    compare_csv_rows,
    fill_days,
    summarise_movement,
    pct_delta,
    previous_period,
    resolve_period,
)


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


class PctDeltaTests(unittest.TestCase):
    def test_growth_is_a_positive_whole_percentage(self):
        self.assertEqual(pct_delta(287, 190), 51)

    def test_decline_is_negative(self):
        self.assertEqual(pct_delta(50, 100), -50)

    def test_no_baseline_returns_none_rather_than_infinity(self):
        # 0 -> 287 is not a "% increase", it is new activity.
        self.assertIsNone(pct_delta(287, 0))

    def test_both_zero_returns_none(self):
        self.assertIsNone(pct_delta(0, 0))

    def test_missing_values_return_none(self):
        self.assertIsNone(pct_delta(None, 100))
        self.assertIsNone(pct_delta(100, None))


class FillDaysTests(unittest.TestCase):
    def test_gaps_are_zero_filled(self):
        rows = [{"day": "2026-07-02", "inbound": 5, "outbound": 3}]
        out = fill_days(rows, date(2026, 7, 1), date(2026, 7, 3), ("inbound", "outbound"))
        self.assertEqual(out, [
            {"day": "2026-07-01", "inbound": 0, "outbound": 0},
            {"day": "2026-07-02", "inbound": 5, "outbound": 3},
            {"day": "2026-07-03", "inbound": 0, "outbound": 0},
        ])

    def test_every_day_in_range_is_present(self):
        out = fill_days([], date(2026, 7, 1), date(2026, 7, 31), ("inbound",))
        self.assertEqual(len(out), 31)

    def test_rows_outside_the_range_are_ignored(self):
        rows = [{"day": "2026-06-30", "inbound": 99}]
        out = fill_days(rows, date(2026, 7, 1), date(2026, 7, 1), ("inbound",))
        self.assertEqual(out, [{"day": "2026-07-01", "inbound": 0}])


class AlignSeriesTests(unittest.TestCase):
    def test_series_are_aligned_by_day_index_not_calendar_date(self):
        current = [{"day": "2026-07-01", "v": 10}, {"day": "2026-07-02", "v": 20}]
        previous = [{"day": "2026-06-01", "v": 5}, {"day": "2026-06-02", "v": 7}]
        out = align_series(current, previous, "v")
        self.assertEqual(out[0], {
            "index": 1, "label": "Day 1",
            "current_day": "2026-07-01", "current": 10,
            "previous_day": "2026-06-01", "previous": 5,
        })

    def test_longer_period_leaves_the_shorter_series_empty_at_the_tail(self):
        current = [{"day": "2026-07-01", "v": 1}, {"day": "2026-07-02", "v": 2}]
        previous = [{"day": "2026-06-01", "v": 9}]
        out = align_series(current, previous, "v")
        self.assertEqual(len(out), 2)
        self.assertIsNone(out[1]["previous"])
        self.assertIsNone(out[1]["previous_day"])
        self.assertEqual(out[1]["current"], 2)


class BuildDeltasTests(unittest.TestCase):
    def test_each_metric_carries_both_values_and_the_change(self):
        out = build_deltas({"new_leads": 287}, {"new_leads": 190}, ("new_leads",))
        self.assertEqual(out["new_leads"], {"current": 287, "previous": 190, "delta_pct": 51})

    def test_metric_absent_from_a_period_is_treated_as_zero(self):
        out = build_deltas({}, {"new_leads": 10}, ("new_leads",))
        self.assertEqual(out["new_leads"]["current"], 0)
        self.assertEqual(out["new_leads"]["delta_pct"], -100)


class BuildSummaryTests(unittest.TestCase):
    CURRENT = {
        "new_leads": 287, "hot": 38, "messages_in": 1204,
        "messages_out": 1441, "ai_replies": 1437,
    }
    PREVIOUS = {
        "new_leads": 190, "hot": 31, "messages_in": 890,
        "messages_out": 1102, "ai_replies": 1090,
    }

    def test_summary_states_the_headline_count_and_the_change(self):
        text = build_summary(self.CURRENT, self.PREVIOUS, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("287 new leads", text)
        self.assertIn("51%", text)
        self.assertIn("more", text)

    def test_summary_mentions_hot_leads_and_automation(self):
        text = build_summary(self.CURRENT, self.PREVIOUS, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("38", text)
        self.assertIn("99%", text)

    def test_decline_is_described_as_fewer_not_more(self):
        text = build_summary({"new_leads": 90}, {"new_leads": 180}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("fewer", text)
        self.assertNotIn("more", text)

    def test_no_baseline_avoids_a_percentage_claim(self):
        text = build_summary({"new_leads": 50}, {"new_leads": 0}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("50 new leads", text)
        self.assertNotIn("%", text.split(".")[0])

    def test_empty_period_reads_as_plain_english_not_a_crash(self):
        text = build_summary({}, {}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("0 new leads", text)

    def test_huge_growth_reads_as_a_multiple_not_a_four_digit_percentage(self):
        # 290 vs 3 is +9567%, which is arithmetically right and useless to a
        # human. A client should read "97x more", not a four-digit percentage.
        text = build_summary({"new_leads": 290}, {"new_leads": 3},
                             date(2026, 7, 18), date(2026, 7, 31))
        self.assertIn("97x more", text)
        self.assertNotIn("9567", text)

    def test_ordinary_growth_still_reads_as_a_percentage(self):
        text = build_summary({"new_leads": 287}, {"new_leads": 190},
                             date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("51% more", text)
        self.assertNotIn("x more", text)


class CompareCsvRowsTests(unittest.TestCase):
    SERIES = {
        "leads_inbound": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 5,
             "previous_day": "2026-06-01", "previous": 2},
        ],
        "leads_outbound": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 0,
             "previous_day": "2026-06-01", "previous": 0},
        ],
        "messages_in": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 40,
             "previous_day": "2026-06-01", "previous": 20},
        ],
        "messages_out": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 45,
             "previous_day": "2026-06-01", "previous": 22},
        ],
    }

    def test_one_row_per_day_index_with_both_periods_side_by_side(self):
        rows = compare_csv_rows(self.SERIES)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day_index"], 1)
        self.assertEqual(rows[0]["current_date"], "2026-07-01")
        self.assertEqual(rows[0]["current_leads_inbound"], 5)
        self.assertEqual(rows[0]["previous_date"], "2026-06-01")
        self.assertEqual(rows[0]["previous_messages_out"], 22)

    def test_missing_previous_day_becomes_blank_not_a_crash(self):
        series = {k: [dict(v[0], previous_day=None, previous=None)]
                  for k, v in self.SERIES.items()}
        rows = compare_csv_rows(series)
        self.assertEqual(rows[0]["previous_date"], "")
        self.assertEqual(rows[0]["previous_leads_inbound"], "")


class SummariseMovementTests(unittest.TestCase):
    # Shape returned by analytics_segment_movement, using real proportions.
    ROWS = [
        {"from_segment": "C", "to_segment": "B", "total": 170},
        {"from_segment": "C", "to_segment": "A", "total": 37},
        {"from_segment": "B", "to_segment": "A", "total": 29},
        {"from_segment": "B", "to_segment": "C", "total": 16},
        {"from_segment": "A", "to_segment": "B", "total": 6},
        {"from_segment": "C", "to_segment": "D", "total": 4},
    ]

    def test_counts_moves_toward_hot_as_promotions(self):
        out = summarise_movement(self.ROWS)
        # C->B 170 + C->A 37 + B->A 29
        self.assertEqual(out["promoted"], 236)

    def test_counts_moves_away_from_hot_as_demotions(self):
        out = summarise_movement(self.ROWS)
        # B->C 16 + A->B 6 + C->D 4
        self.assertEqual(out["demoted"], 26)

    def test_promoted_to_hot_counts_only_arrivals_at_segment_a(self):
        out = summarise_movement(self.ROWS)
        self.assertEqual(out["promoted_to_hot"], 66)

    def test_flows_are_sorted_largest_first_for_display(self):
        out = summarise_movement(self.ROWS)
        self.assertEqual(out["flows"][0], {"from": "C", "to": "B", "total": 170})
        totals = [f["total"] for f in out["flows"]]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_empty_input_yields_zeros_not_a_crash(self):
        out = summarise_movement([])
        self.assertEqual(out["promoted"], 0)
        self.assertEqual(out["demoted"], 0)
        self.assertEqual(out["promoted_to_hot"], 0)
        self.assertEqual(out["flows"], [])

    def test_unknown_segment_labels_are_ignored_rather_than_miscounted(self):
        out = summarise_movement([{"from_segment": "X", "to_segment": "A", "total": 5}])
        self.assertEqual(out["promoted"], 0)
        self.assertEqual(out["demoted"], 0)


if __name__ == "__main__":
    unittest.main()
