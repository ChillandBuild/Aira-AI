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


def _lead_has_converted_column(db, tenant_id: str) -> bool:
    """Detect whether leads.converted_at exists; if a select on it errors we
    treat sales/revenue as unavailable (0). Cached per process is unnecessary."""
    try:
        db.table("leads").select("converted_at").eq("tenant_id", tenant_id).limit(1).execute()
        return True
    except Exception:
        return False


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
    q = db.table("ad_creatives").select(
        "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,campaign_id"
    ).eq("tenant_id", tenant_id)
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

    # Insights (summed over the date range) per creative.
    ins_q = db.table("ad_insights_daily").select(
        "ad_creative_id,inline_link_clicks,clicks,spend,insight_date"
    ).eq("tenant_id", tenant_id).in_("ad_creative_id", creative_ids)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    insights = (ins_q.execute().data) or []

    ins_by_creative: dict[str, dict] = {}
    for r in insights:
        acc = ins_by_creative.setdefault(
            r["ad_creative_id"], {"inline_link_clicks": 0, "clicks": 0, "spend": 0.0}
        )
        acc["inline_link_clicks"] += int(r.get("inline_link_clicks", 0) or 0)
        acc["clicks"] += int(r.get("clicks", 0) or 0)
        acc["spend"] += float(r.get("spend", 0) or 0)

    # Leads attributed to these creatives (funnel counts).
    has_converted = _lead_has_converted_column(db, tenant_id)
    lead_cols = "id,segment,attributed_ad_creative_id,created_at" + (
        ",converted_at" if has_converted else ""
    )
    lead_q = db.table("leads").select(lead_cols).eq("tenant_id", tenant_id).in_(
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
        f = funnel.setdefault(cid, {"messages": 0, "qualified": 0, "hot": 0, "sales": 0})
        f["messages"] += 1
        seg = lead.get("segment")
        if seg in ("A", "B"):
            f["qualified"] += 1
        if seg == "A":
            f["hot"] += 1
        if has_converted and lead.get("converted_at"):
            f["sales"] += 1

    out: list[dict] = []
    for c in creatives:
        ins = ins_by_creative.get(c["id"], {"inline_link_clicks": 0, "clicks": 0, "spend": 0.0})
        fn = funnel.get(c["id"], {"messages": 0, "qualified": 0, "hot": 0, "sales": 0})
        clicks = ins["inline_link_clicks"]
        messages = fn["messages"]
        row = {
            "ad_creative_id": c["id"],
            "creative_label": c["creative_label"],
            "meta_ad_id": c["meta_ad_id"],
            "adset_id": c.get("meta_adset_id"),
            "adset_name": c.get("meta_adset_name"),
            "campaign_id": c.get("campaign_id"),
            "inline_link_clicks": clicks,
            "messages": messages,
            "clicked_no_message": max(clicks - messages, 0),
            "qualified": fn["qualified"],
            "hot": fn["hot"],
            "sales": fn["sales"],
            "spend": round(ins["spend"], 2),
            "revenue": 0,  # no revenue source yet; see plan status-mapping note
        }
        compute_cost_metrics(row)
        out.append(row)

    out.sort(key=lambda r: r["inline_link_clicks"], reverse=True)
    return out


def build_ad_filter_tree(db, tenant_id: str) -> dict:
    """Campaign -> adset -> creative option tree for cascading dropdowns."""
    creatives = (
        db.table("ad_creatives").select(
            "id,creative_label,meta_adset_id,meta_adset_name,campaign_id"
        ).eq("tenant_id", tenant_id).execute().data
    ) or []

    campaign_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    camp_names: dict[str, str] = {}
    if campaign_ids:
        camps = (
            db.table("ad_campaigns").select("id,campaign_name")
            .eq("tenant_id", tenant_id).in_("id", campaign_ids).execute().data
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
    }
