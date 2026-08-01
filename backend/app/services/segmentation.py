from app.models.schemas import SegmentType

# Fixed segment bands (not tenant-configurable): Hot 8-10, Warm 4-7, Cold 1-3,
# Not Interested (D) = 0 only.
_THRESHOLDS = {"A": 8, "B": 4, "C": 1}


def score_to_segment(score: int) -> SegmentType:
    """Map a 0-10 score to a segment label per the fixed scoring bands."""
    if score >= _THRESHOLDS["A"]:
        return "A"
    elif score >= _THRESHOLDS["B"]:
        return "B"
    elif score >= _THRESHOLDS["C"]:
        return "C"
    else:
        return "D"


def new_lead_score_and_segment(tenant_id: str) -> tuple[int, SegmentType]:
    """Start a new lead at the Cold-range floor."""
    return _THRESHOLDS["C"], "C"
