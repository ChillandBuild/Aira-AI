import pytest

from app.services import meta_ads_fields as mf
from app.services.meta_ads_fields import (
    META_FIELD_CATALOG,
    _BY_KEY,
    breakdowns_for_api,
    catalog_for_api,
    extract_value,
    fetch_meta_insights_live,
)
from app.services.meta_ads_insights_sync import _fetch_paged, _fetch_paged_all_statuses


@pytest.fixture(autouse=True)
def _clear_cache():
    mf._CACHE.clear()
    yield
    mf._CACHE.clear()


def _val(key, row, ad=None):
    return extract_value(_BY_KEY[key], row, ad)


# ---- value extraction -----------------------------------------------------

def test_action_first_match_never_sums():
    row = {
        "actions": [
            {"action_type": "omni_purchase", "value": "5"},
            {"action_type": "purchase", "value": "5"},
        ]
    }
    assert _val("purchases", row) == 5


def test_cost_per_action_and_action_value():
    row = {
        "cost_per_action_type": [{"action_type": "lead", "value": "12.5"}],
        "action_values": [{"action_type": "purchase", "value": "900"}],
    }
    assert _val("cost_per_lead", row) == 12.5
    assert _val("purchase_value", row) == 900


def test_list_source_takes_first_entry():
    row = {"purchase_roas": [{"action_type": "omni_purchase", "value": "3.2"}]}
    assert _val("purchase_roas", row) == 3.2


def test_field_passthrough_is_float_and_text_stays_text():
    row = {"ctr": "1.234", "quality_ranking": "ABOVE_AVERAGE"}
    assert _val("ctr", row) == 1.234
    assert _val("quality_ranking", row) == "ABOVE_AVERAGE"


# ---- results --------------------------------------------------------------

def test_results_conversations_goal_and_cost_per_result():
    row = {
        "optimization_goal": "CONVERSATIONS",
        "spend": "100",
        "actions": [{"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "4"}],
    }
    assert _val("results", row) == 4
    assert _val("result_type", row) == "Messaging conversations started"
    assert _val("cost_per_result", row) == 25.0


def test_zero_results_gives_no_cost_per_result():
    row = {"optimization_goal": "CONVERSATIONS", "spend": "100", "actions": []}
    assert _val("results", row) is None
    assert _val("cost_per_result", row) is None


def test_a_real_zero_result_stays_zero():
    row = {"optimization_goal": "LINK_CLICKS", "spend": "50", "inline_link_clicks": "0"}
    assert _val("results", row) == 0
    assert _val("cost_per_result", row) is None


def test_unknown_goal_falls_back_to_link_clicks():
    row = {"optimization_goal": "SOMETHING_NEW", "spend": "10", "inline_link_clicks": "7"}
    assert _val("results", row) == 7
    assert _val("result_type", row) == "Link clicks"
    assert _val("cost_per_result", row) == 10 / 7


def test_thruplay_goal_reads_video_list():
    row = {
        "optimization_goal": "THRUPLAY",
        "spend": "20",
        "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "40"}],
    }
    assert _val("results", row) == 40
    assert _val("cost_per_result", row) == 0.5


# ---- budget ---------------------------------------------------------------

def test_budget_from_adset_daily():
    ad = {"adset": {"daily_budget": "50000"}, "campaign": {}}
    assert _val("budget", {}, ad) == {"amount": 500.0, "type": "daily", "level": "ad_set"}


def test_budget_falls_back_to_campaign_lifetime():
    ad = {"adset": {}, "campaign": {"lifetime_budget": "100000"}}
    assert _val("budget", {}, ad) == {"amount": 1000.0, "type": "lifetime", "level": "campaign"}


def test_budget_none_without_any_budget():
    assert _val("budget", {}, {"adset": {}, "campaign": {}}) is None


# ---- fetch ----------------------------------------------------------------

def _ad(ad_id, name, **extra):
    base = {
        "id": ad_id,
        "name": name,
        "effective_status": "ACTIVE",
        "adset": {"name": f"set {ad_id}", "destination_type": "WHATSAPP", "daily_budget": "10000"},
        "campaign": {"name": f"camp {ad_id}"},
        "creative": {"body": "hi", "title": "t"},
    }
    base.update(extra)
    return base


@pytest.fixture
def graph(monkeypatch):
    """Fake Graph: insights rows and ads list are set per test; calls recorded."""
    state = {
        "insights": [],
        "ads": [],
        "insight_calls": [],
        "ad_calls": 0,
    }

    def fake_paged(url, params):
        assert url.endswith("/insights")
        state["insight_calls"].append(params)
        return list(state["insights"])

    def fake_all_statuses(url, params, *, status_field, statuses):
        assert url.endswith("/ads")
        assert status_field == "ad.effective_status"
        state["ad_calls"] += 1
        return list(state["ads"])

    monkeypatch.setattr(mf, "_fetch_paged", fake_paged)
    monkeypatch.setattr(mf, "_fetch_paged_all_statuses", fake_all_statuses)
    return state


def _fetch(**kw):
    args = dict(token="tok", account="act_1", date_from="2026-10-01", date_to="2026-10-15", keys=["spend"])
    args.update(kw)
    return fetch_meta_insights_live(**args)


def test_ad_ids_filter(graph):
    graph["ads"] = [_ad("A", "Ad A"), _ad("B", "Ad B")]
    graph["insights"] = [
        {"ad_id": "A", "ad_name": "Ad A", "spend": "5"},
        {"ad_id": "B", "ad_name": "Ad B", "spend": "6"},
    ]
    rows = _fetch(ad_ids={"A"})
    assert [r["meta_ad_id"] for r in rows] == ["A"]
    assert rows[0]["values"] == {"spend": 5.0}


def test_zero_delivery_ad_gets_a_row(graph):
    graph["ads"] = [_ad("A", "Ad A"), _ad("C", "Ad C")]
    graph["insights"] = [{"ad_id": "A", "ad_name": "Ad A", "spend": "5"}]
    rows = {r["meta_ad_id"]: r for r in _fetch(keys=["spend", "budget", "destination"])}
    assert set(rows) == {"A", "C"}
    c = rows["C"]
    assert c["ad_name"] == "Ad C"
    assert c["campaign_name"] == "camp C"
    assert c["destination_type"] == "WHATSAPP"
    assert c["breakdown"] is None
    assert c["values"]["spend"] is None
    assert c["values"]["budget"] == {"amount": 100.0, "type": "daily", "level": "ad_set"}


def test_eligible_ad_missing_from_meta_gets_no_blank_row(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = []
    rows = _fetch(ad_ids={"A", "GONE"})
    assert [r["meta_ad_id"] for r in rows] == ["A"]


def test_breakdown_label_joins_columns(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = [
        {"ad_id": "A", "publisher_platform": "facebook", "platform_position": "feed", "spend": "3"}
    ]
    rows = _fetch(breakdown="placement", keys=["spend"])
    assert len(rows) == 1
    assert rows[0]["breakdown"] == "facebook · feed"
    params = graph["insight_calls"][-1]
    assert params["breakdowns"] == "publisher_platform,platform_position"


def test_ranking_keys_dropped_with_breakdown(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = [{"ad_id": "A", "age": "25-34", "spend": "1", "quality_ranking": "X"}]
    rows = _fetch(breakdown="age", keys=["spend", "quality_ranking"])
    assert set(rows[0]["values"]) == {"spend"}
    assert rows[0]["breakdown"] == "25-34"


def test_ranking_keys_kept_without_breakdown(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = [{"ad_id": "A", "quality_ranking": "ABOVE_AVERAGE"}]
    rows = _fetch(keys=["quality_ranking"])
    assert rows[0]["values"] == {"quality_ranking": "ABOVE_AVERAGE"}


def test_unknown_breakdown_raises(graph):
    with pytest.raises(ValueError):
        _fetch(breakdown="nonsense")


def test_unknown_keys_ignored(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = [{"ad_id": "A", "spend": "2"}]
    rows = _fetch(keys=["spend", "no_such_key"])
    assert set(rows[0]["values"]) == {"spend"}


def test_second_identical_call_hits_cache(graph):
    graph["ads"] = [_ad("A", "Ad A")]
    graph["insights"] = [{"ad_id": "A", "spend": "2"}]
    first = _fetch(keys=["spend"])
    calls_after_first = (len(graph["insight_calls"]), graph["ad_calls"])
    second = _fetch(keys=["spend"])
    assert (len(graph["insight_calls"]), graph["ad_calls"]) == calls_after_first
    assert second == first


def test_insight_params_shape(graph):
    graph["ads"] = []
    _fetch(keys=["spend", "quality_ranking"])
    params = graph["insight_calls"][-1]
    assert params["level"] == "ad"
    assert "breakdowns" not in params
    assert "time_increment" not in params
    assert '"since": "2026-10-01"' in params["time_range"]
    assert params["access_token"] == "tok"
    fields = params["fields"].split(",")
    assert "spend" in fields and "quality_ranking" in fields
    assert len(fields) == len(set(fields))


# ---- catalogue sanity -----------------------------------------------------

def test_catalog_keys_unique():
    keys = [e["key"] for e in META_FIELD_CATALOG]
    assert len(keys) == len(set(keys))


def test_every_group_non_empty():
    groups = {e["group"] for e in META_FIELD_CATALOG}
    for g in groups:
        assert any(e["group"] == g for e in META_FIELD_CATALOG)
    assert len(groups) == 9


def test_catalog_for_api_has_no_source():
    api = catalog_for_api()
    assert len(api) == len(META_FIELD_CATALOG)
    assert all("source" not in e for e in api)
    by_key = {e["key"]: e for e in api}
    assert by_key["quality_ranking"]["breakdown_ok"] is False
    assert by_key["spend"]["breakdown_ok"] is True


def test_breakdowns_for_api():
    out = breakdowns_for_api()
    assert {"key": "placement", "label": "Placement"} in out
    assert len(out) == 6


def test_module_reuses_sync_helpers():
    assert mf._fetch_paged is _fetch_paged
    assert mf._fetch_paged_all_statuses is _fetch_paged_all_statuses
