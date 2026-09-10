from app.services.ad_performance import compute_cost_metrics


def test_cpc_uses_inline_link_clicks():
    row = {"inline_link_clicks": 422, "messages": 38, "qualified": 22,
           "hot": 12, "spend": 3624.79, "revenue": 0}
    out = compute_cost_metrics(row)
    assert round(out["cpc"], 2) == 8.59


def test_cost_per_message_and_hot():
    row = {"inline_link_clicks": 65, "messages": 9, "qualified": 5,
           "hot": 2, "spend": 421.13, "revenue": 0}
    out = compute_cost_metrics(row)
    assert round(out["cost_per_message"], 2) == 46.79
    assert round(out["cost_per_hot"], 2) == 210.56


def test_zero_denominators_do_not_crash():
    row = {"inline_link_clicks": 0, "messages": 0, "qualified": 0,
           "hot": 0, "spend": 0, "revenue": 0}
    out = compute_cost_metrics(row)
    assert out["cpc"] is None
    assert out["cost_per_message"] is None
    assert out["roas"] is None


def test_roas_when_revenue_present():
    row = {"inline_link_clicks": 422, "messages": 38, "qualified": 22,
           "hot": 12, "spend": 4000, "revenue": 10000}
    out = compute_cost_metrics(row)
    assert out["roas"] == 2.5


# --- Delivery-status filter (Meta Ads tab "Delivery" dropdown + CSV export) ---

from app.services.ad_performance import DELIVERY_GROUPS, filter_by_delivery


def _rows():
    return [
        {"creative_label": "Live one", "delivery_status": "ACTIVE"},
        {"creative_label": "Paused above", "delivery_status": "CAMPAIGN_PAUSED"},
        {"creative_label": "Removed", "delivery_status": "ARCHIVED"},
        {"creative_label": "Gone", "delivery_status": "DELETED"},
        {"creative_label": "Rejected", "delivery_status": "DISAPPROVED"},
    ]


def test_no_filter_returns_everything():
    assert len(filter_by_delivery(_rows(), None)) == 5
    assert len(filter_by_delivery(_rows(), "")) == 5


def test_active_excludes_archived_and_paused():
    out = filter_by_delivery(_rows(), "active")
    assert [r["creative_label"] for r in out] == ["Live one"]


def test_paused_covers_campaign_and_adset_level_pauses():
    """An ad whose campaign is paused isn't delivering either -- users reading
    the dashboard don't care which level the pause came from."""
    out = filter_by_delivery(_rows(), "paused")
    assert [r["creative_label"] for r in out] == ["Paused above"]


def test_removed_groups_archived_and_deleted():
    out = filter_by_delivery(_rows(), "removed")
    assert {r["creative_label"] for r in out} == {"Removed", "Gone"}


def test_unknown_key_falls_back_to_unfiltered():
    """A stale bookmark or typo'd query param should show the table, not nothing."""
    assert len(filter_by_delivery(_rows(), "nonsense")) == 5


def test_filter_key_is_case_and_whitespace_tolerant():
    assert len(filter_by_delivery(_rows(), "  Active ")) == 1


def test_rows_with_no_status_are_excluded_by_any_filter():
    rows = [{"creative_label": "Never synced", "delivery_status": None}]
    assert filter_by_delivery(rows, "active") == []
    assert len(filter_by_delivery(rows, None)) == 1


def test_frontend_dropdown_keys_all_exist_server_side():
    """AdPerformanceTab.tsx sends these keys with the CSV export request; a key
    missing here would silently return an unfiltered download."""
    for key in ("active", "paused", "archived", "deleted", "issues"):
        assert key in DELIVERY_GROUPS
