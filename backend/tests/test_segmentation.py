from unittest.mock import patch

from app.services.segmentation import new_lead_score_and_segment, score_to_segment


def test_custom_thresholds_define_contiguous_score_ranges():
    thresholds = {"A": 8, "B": 6, "C": 3}
    expected = {
        1: "D", 2: "D", 3: "C", 4: "C", 5: "C",
        6: "B", 7: "B", 8: "A", 9: "A", 10: "A",
    }

    assert {score: score_to_segment(score, thresholds) for score in range(1, 11)} == expected


def test_new_lead_starts_at_the_saved_cold_score():
    with patch("app.config_dynamic.get_setting", return_value='{"A": 9, "B": 7, "C": 6}'):
        assert new_lead_score_and_segment("tenant-1") == (6, "C")


def test_new_lead_starts_at_cold_three_when_configured():
    with patch("app.config_dynamic.get_setting", return_value='{"A": 8, "B": 6, "C": 3}'):
        assert new_lead_score_and_segment("tenant-1") == (3, "C")
