"""Per-creative ad performance: join ad_creatives x ad_insights_daily x leads,
compute funnel counts and cost metrics. Pure aggregation; no external calls.
"""
import logging

logger = logging.getLogger(__name__)


def _safe_div(numer: float, denom: float):
    if not denom:
        return None
    return numer / denom


def compute_cost_metrics(row: dict) -> dict:
    """Add cpc / cost_per_message / cost_per_qualified / cost_per_hot / roas.
    All guard against divide-by-zero (return None). Mutates and returns row.
    CPC uses inline_link_clicks to match the 'Clicks' column shown in the UI.
    """
    spend = float(row.get("spend", 0) or 0)
    clicks = float(row.get("inline_link_clicks", 0) or 0)
    messages = float(row.get("messages", 0) or 0)
    qualified = float(row.get("qualified", 0) or 0)
    hot = float(row.get("hot", 0) or 0)
    revenue = float(row.get("revenue", 0) or 0)

    row["cpc"] = _safe_div(spend, clicks)
    row["cost_per_message"] = _safe_div(spend, messages)
    row["cost_per_qualified"] = _safe_div(spend, qualified)
    row["cost_per_hot"] = _safe_div(spend, hot)
    row["roas"] = _safe_div(revenue, spend)
    return row


def build_creative_performance(
    db,
    tenant_id: str,
    *,
    campaign_id: str | None = None,
    adset_id: str | None = None,
    ad_creative_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """One row per creative with volume/quality/money metrics.

    Filters:
      campaign_id     -> ad_creatives.campaign_id (Aira ad_campaigns FK)
      adset_id        -> ad_creatives.meta_adset_id
      ad_creative_id  -> ad_creatives.id
      date_from/to    -> bound both ad_insights_daily.insight_date and leads.created_at
    """
    from app.services.meta_ads_insights_sync import (
        get_current_ads_account_id,
        sum_actions,
    )

    account = get_current_ads_account_id(db, tenant_id)
    if not account:
        return []

    q = db.table("ad_creatives").select(
        "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,"
        "campaign_id,effective_status"
    ).eq("tenant_id", tenant_id).eq(
        "meta_ad_account_id", account
    ).eq("is_click_to_whatsapp", True)
    if campaign_id:
        q = q.eq("campaign_id", campaign_id)
    if adset_id:
        q = q.eq("meta_adset_id", adset_id)
    if ad_creative_id:
        q = q.eq("id", ad_creative_id)
    creatives = (q.execute().data) or []
    if not creatives:
        return []
    creative_ids = [c["id"] for c in creatives]
    campaign_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    campaigns: dict[str, dict] = {}
    if campaign_ids:
        campaign_rows = (
            db.table("ad_campaigns").select("id,campaign_name,effective_status")
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("id", campaign_ids)
            .execute()
            .data
        ) or []
        campaigns = {c["id"]: c for c in campaign_rows}

    # Insights (summed over the date range) per creative.
    ins_q = db.table("ad_insights_daily").select(
        "ad_creative_id,inline_link_clicks,clicks,spend,impressions,reach,actions,insight_date"
    ).eq("tenant_id", tenant_id).eq(
        "meta_ad_account_id", account
    ).in_("ad_creative_id", creative_ids)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    insights = (ins_q.execute().data) or []

    ins_by_creative: dict[str, dict] = {}
    for r in insights:
        acc = ins_by_creative.setdefault(
            r["ad_creative_id"],
            {
                "inline_link_clicks": 0,
                "clicks": 0,
                "spend": 0.0,
                "impressions": 0,
                "reach": 0,
                "meta_conversations": 0,
            },
        )
        acc["inline_link_clicks"] += int(r.get("inline_link_clicks", 0) or 0)
        acc["clicks"] += int(r.get("clicks", 0) or 0)
        acc["spend"] += float(r.get("spend", 0) or 0)
        acc["impressions"] += int(r.get("impressions", 0) or 0)
        acc["reach"] += int(r.get("reach", 0) or 0)
        acc["meta_conversations"] += sum_actions(
            r.get("actions"),
            {"onsite_conversion.total_messaging_connection"},
        )

    # Leads attributed to these creatives (funnel counts).
    lead_q = db.table("leads").select(
        "id,segment,attributed_ad_creative_id,created_at"
    ).eq("tenant_id", tenant_id).in_(
        "attributed_ad_creative_id", creative_ids
    ).is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    leads = (lead_q.execute().data) or []

    funnel: dict[str, dict] = {}
    for lead in leads:
        cid = lead.get("attributed_ad_creative_id")
        if not cid:
            continue
        f = funnel.setdefault(cid, {"messages": 0, "hot": 0})
        f["messages"] += 1
        if lead.get("segment") == "A":
            f["hot"] += 1

    out: list[dict] = []
    for c in creatives:
        ins = ins_by_creative.get(c["id"], {
            "inline_link_clicks": 0,
            "clicks": 0,
            "spend": 0.0,
            "impressions": 0,
            "reach": 0,
            "meta_conversations": 0,
        })
        fn = funnel.get(c["id"], {"messages": 0, "hot": 0})
        campaign = campaigns.get(c.get("campaign_id"), {})
        clicks = ins["inline_link_clicks"]
        messages = fn["messages"]
        no_message = max(clicks - messages, 0)
        spend = round(ins["spend"], 2)
        impressions = ins["impressions"]
        reach = ins["reach"]
        row = {
            "ad_creative_id": c["id"],
            "creative_label": c["creative_label"],
            "meta_ad_id": c["meta_ad_id"],
            "meta_ad_account_id": account,
            "adset_id": c.get("meta_adset_id"),
            "adset_name": c.get("meta_adset_name"),
            "campaign_id": c.get("campaign_id"),
            "campaign_name": campaign.get("campaign_name") or "—",
            "campaign_status": campaign.get("effective_status") or c.get("effective_status"),
            "impressions": impressions,
            "reach": reach,
            "clicks_all": ins["clicks"],
            "inline_link_clicks": clicks,
            "messages": messages,
            "meta_conversations": ins["meta_conversations"],
            "clicked_no_message": no_message,
            "hot": fn["hot"],
            "spend": spend,
            "frequency": _safe_div(impressions, reach),
            "ctr": (_safe_div(clicks, impressions) or 0) * 100 if impressions else None,
            "cpm": _safe_div(spend * 1000, impressions),
            "conversation_rate": (_safe_div(messages, clicks) or 0) * 100 if clicks else None,
            "no_message_rate": (_safe_div(no_message, clicks) or 0) * 100 if clicks else None,
            "revenue": 0,
        }
        compute_cost_metrics(row)
        out.append(row)

    out.sort(key=lambda r: r["inline_link_clicks"], reverse=True)
    return out


def build_ad_filter_tree(db, tenant_id: str) -> dict:
    """Campaign -> adset -> creative option tree for cascading dropdowns."""
    from app.services.meta_ads_insights_sync import get_current_ads_account_id

    account = get_current_ads_account_id(db, tenant_id)
    if not account:
        return {"campaigns": [], "adsets": [], "creatives": [], "account_id": None}

    creatives = (
        db.table("ad_creatives").select(
            "id,creative_label,meta_adset_id,meta_adset_name,campaign_id"
        ).eq("tenant_id", tenant_id)
        .eq("meta_ad_account_id", account)
        .eq("is_click_to_whatsapp", True)
        .execute().data
    ) or []

    campaign_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    camp_names: dict[str, str] = {}
    if campaign_ids:
        camps = (
            db.table("ad_campaigns").select("id,campaign_name")
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("id", campaign_ids).execute().data
        ) or []
        camp_names = {c["id"]: c["campaign_name"] for c in camps}

    return {
        "campaigns": [{"id": cid, "name": camp_names.get(cid, "—")} for cid in campaign_ids],
        "adsets": [
            {"id": aid, "name": name, "campaign_id": campc}
            for aid, name, campc in sorted({
                (c["meta_adset_id"], c.get("meta_adset_name") or "—", c.get("campaign_id"))
                for c in creatives if c.get("meta_adset_id")
            })
        ],
        "creatives": [
            {"id": c["id"], "name": c["creative_label"],
             "adset_id": c.get("meta_adset_id"), "campaign_id": c.get("campaign_id")}
            for c in creatives
        ],
        "account_id": account,
    }
