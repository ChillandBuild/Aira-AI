"""Per-creative ad performance.

Meta provides delivery/click/spend. Aira counts each lead once per Meta ad from
lead_meta_ad_attributions, so repeat messages from the same lead and ad do not
duplicate the conversion, while the same lead may count once for another ad.
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
      date_from/to    -> bound insights and first lead/ad attribution date
    """
    from app.services.meta_ads_insights_sync import (
        _get_ads_credentials,
        fetch_unique_reach_by_ad,
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
            db.table("ad_campaigns").select(
                "id,campaign_name,effective_status,daily_budget,lifetime_budget"
            )
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("id", campaign_ids)
            .execute()
            .data
        ) or []
        campaigns = {c["id"]: c for c in campaign_rows}

    adset_ids = sorted({c["meta_adset_id"] for c in creatives if c.get("meta_adset_id")})
    adsets: dict[str, dict] = {}
    if adset_ids:
        adset_rows = (
            db.table("ad_sets").select(
                "meta_adset_id,daily_budget,lifetime_budget"
            )
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("meta_adset_id", adset_ids)
            .execute()
            .data
        ) or []
        adsets = {a["meta_adset_id"]: a for a in adset_rows}

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

    unique_reach_by_ad: dict[str, int] = {}
    credentials = _get_ads_credentials(db, tenant_id)
    if credentials:
        try:
            unique_reach_by_ad = fetch_unique_reach_by_ad(
                *credentials,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as error:
            logger.warning("Meta unique reach fetch failed for tenant %s: %s", tenant_id, error)

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

    # Unique lead/ad relationships. The table primary key prevents the same
    # lead from being counted twice for the same Meta ad.
    meta_ad_ids = [c["meta_ad_id"] for c in creatives if c.get("meta_ad_id")]
    attributions: list[dict] = []
    if meta_ad_ids:
        attribution_q = (
            db.table("lead_meta_ad_attributions")
            .select("lead_id,meta_ad_id,first_seen_at")
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("meta_ad_id", meta_ad_ids)
        )
        if date_from:
            attribution_q = attribution_q.gte("first_seen_at", date_from)
        if date_to:
            attribution_q = attribution_q.lte("first_seen_at", date_to + "T23:59:59")
        attributions = (attribution_q.execute().data) or []

    lead_ids = sorted({row["lead_id"] for row in attributions if row.get("lead_id")})
    leads_by_id: dict[str, dict] = {}
    if lead_ids:
        leads = (
            db.table("leads")
            .select("id,segment")
            .eq("tenant_id", tenant_id)
            .in_("id", lead_ids)
            .is_("deleted_at", "null")
            .execute()
            .data
        ) or []
        leads_by_id = {lead["id"]: lead for lead in leads}

    funnel: dict[str, dict] = {}
    for attribution in attributions:
        lead = leads_by_id.get(attribution.get("lead_id"))
        ad_id = attribution.get("meta_ad_id")
        if not lead or not ad_id:
            continue
        f = funnel.setdefault(ad_id, {"messages": 0, "hot": 0})
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
        fn = funnel.get(c["meta_ad_id"], {"messages": 0, "hot": 0})
        campaign = campaigns.get(c.get("campaign_id"), {})
        adset = adsets.get(c.get("meta_adset_id"), {})
        uses_adset_budget = (
            adset.get("daily_budget") is not None
            or adset.get("lifetime_budget") is not None
        )
        clicks = ins["inline_link_clicks"]
        messages = fn["messages"]
        no_message = max(clicks - messages, 0)
        spend = round(ins["spend"], 2)
        impressions = ins["impressions"]
        reach = unique_reach_by_ad.get(c["meta_ad_id"], ins["reach"])
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
            "daily_budget": (
                adset.get("daily_budget") if uses_adset_budget
                else campaign.get("daily_budget")
            ),
            "lifetime_budget": (
                adset.get("lifetime_budget") if uses_adset_budget
                else campaign.get("lifetime_budget")
            ),
            "budget_level": (
                "ad_set" if uses_adset_budget
                else "campaign" if (
                    campaign.get("daily_budget") is not None
                    or campaign.get("lifetime_budget") is not None
                )
                else None
            ),
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
            "meta_conversation_rate": (
                (_safe_div(ins["meta_conversations"], clicks) or 0) * 100
                if clicks else None
            ),
            "no_message_rate": (_safe_div(no_message, clicks) or 0) * 100 if clicks else None,
            "hot_rate": (
                (_safe_div(fn["hot"], messages) or 0) * 100
                if messages else None
            ),
            "attribution_gap": messages - ins["meta_conversations"],
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
            "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,"
            "campaign_id,prefilled_message_code"
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
             "meta_ad_id": c.get("meta_ad_id"),
             "tracking_code": c.get("prefilled_message_code"),
             "adset_id": c.get("meta_adset_id"), "campaign_id": c.get("campaign_id")}
            for c in creatives
        ],
        "account_id": account,
    }
