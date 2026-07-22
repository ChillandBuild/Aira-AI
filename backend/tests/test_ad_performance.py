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
