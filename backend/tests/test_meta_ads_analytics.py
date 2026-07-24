import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_analytics import funnel_stages, leaderboard_sort


def test_funnel_stages_shape():
    out = funnel_stages(clicks=2180, messages=1240, qualified=412, hot=178)
    assert out == [
        {"stage": "Clicked", "count": 2180},
        {"stage": "Messaged", "count": 1240},
        {"stage": "Qualified", "count": 412},
        {"stage": "Hot", "count": 178},
    ]


def test_leaderboard_sort_worst_cost_first_none_last():
    rows = [
        {"name": "A", "cost_per_hot": 45.0, "hot": 10, "spend": 450.0},
        {"name": "B", "cost_per_hot": 112.0, "hot": 2, "spend": 224.0},
        {"name": "C", "cost_per_hot": None, "hot": 0, "spend": 100.0},
    ]
    out = leaderboard_sort(rows)
    assert [r["name"] for r in out] == ["B", "A", "C"]
