from app.services.segmentation import new_lead_score_and_segment, score_to_segment


def test_fixed_thresholds_define_contiguous_score_ranges():
    expected = {
        0: "D",
        1: "C", 2: "C", 3: "C",
        4: "B", 5: "B", 6: "B", 7: "B",
        8: "A", 9: "A", 10: "A",
    }

    assert {score: score_to_segment(score) for score in range(0, 11)} == expected


def test_new_lead_starts_at_the_fixed_cold_floor():
    assert new_lead_score_and_segment("tenant-1") == (1, "C")
