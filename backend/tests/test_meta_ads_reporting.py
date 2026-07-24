import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_reporting import roll_up_rows


def _row(group_id, group_name, **m):
    base = {"group_id": group_id, "group_name": group_name,
            "spend": 0, "impressions": 0, "reach": 0, "results": 0,
            "clicks": 0, "messages": 0, "qualified": 0, "hot": 0,
            "result_label": "Messaging conversations"}
    base.update(m)
    return base


def test_rollup_sums_numeric_within_group():
    rows = [
        _row("c1", "Astro", spend=100.0, clicks=50, messages=10, results=8),
        _row("c1", "Astro", spend=50.0, clicks=25, messages=5, results=4),
        _row("c2", "Diwali", spend=200.0, clicks=80, messages=20, results=15),
    ]
    out = roll_up_rows("campaign", rows)
    astro = next(r for r in out if r["group_id"] == "c1")
    assert astro["spend"] == 150.0
    assert astro["clicks"] == 75
    assert astro["messages"] == 15
    assert astro["results"] == 12
    assert astro["name"] == "Astro"


def test_rollup_computes_cost_per_result_and_no_message():
    rows = [_row("c1", "Astro", spend=120.0, clicks=100, messages=40, results=8)]
    out = roll_up_rows("campaign", rows)
    r = out[0]
    assert r["cost_per_result"] == 15.0          # 120 / 8
    assert r["clicked_no_message"] == 60         # 100 - 40


def test_rollup_cost_per_result_none_when_zero_results():
    rows = [_row("c1", "Astro", spend=120.0, clicks=100, messages=0, results=0)]
    out = roll_up_rows("campaign", rows)
    assert out[0]["cost_per_result"] is None


def test_rollup_sorts_by_spend_desc():
    rows = [
        _row("c1", "Small", spend=10.0),
        _row("c2", "Big", spend=500.0),
    ]
    out = roll_up_rows("campaign", rows)
    assert [r["name"] for r in out] == ["Big", "Small"]
