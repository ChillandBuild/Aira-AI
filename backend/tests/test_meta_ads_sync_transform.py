import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_insights_sync import sum_actions, extract_result_metric


def test_sum_actions_matches_types():
    actions = [
        {"action_type": "onsite_conversion.total_messaging_connection", "value": "12"},
        {"action_type": "link_click", "value": "40"},
        {"action_type": "post_engagement", "value": "99"},
    ]
    assert sum_actions(actions, {"onsite_conversion.total_messaging_connection"}) == 12
    assert sum_actions(actions, {"link_click"}) == 40
    assert sum_actions(actions, {"nonexistent"}) == 0


def test_sum_actions_handles_empty():
    assert sum_actions([], {"link_click"}) == 0
    assert sum_actions(None, {"link_click"}) == 0


def test_extract_result_metric_messaging():
    row = {
        "optimization_goal": "CONVERSATIONS",
        "actions": [{"action_type": "onsite_conversion.total_messaging_connection", "value": "7"}],
        "inline_link_clicks": "50",
    }
    label, count = extract_result_metric(row)
    assert label == "Messaging conversations"
    assert count == 7


def test_extract_result_metric_app_installs():
    row = {
        "optimization_goal": "APP_INSTALLS",
        "actions": [{"action_type": "mobile_app_install", "value": "5"}],
        "inline_link_clicks": "50",
    }
    label, count = extract_result_metric(row)
    assert label == "App installs"
    assert count == 5


def test_extract_result_metric_defaults_to_link_clicks():
    row = {"optimization_goal": "LINK_CLICKS", "actions": [], "inline_link_clicks": "40"}
    label, count = extract_result_metric(row)
    assert label == "Link clicks"
    assert count == 40
