"""Full-account Meta Ads performance rollup for the Meta Ads dashboard.
Reads the same tables as services/ad_performance.py but rolls up to
campaign / ad-set / ad level and includes impressions/reach/results.
Pure read; no Meta calls (the sync job already populated the DB).
"""
import logging

logger = logging.getLogger(__name__)


def _safe_div(n: float, d: float):
    return (n / d) if d else None


def roll_up_rows(level: str, rows: list[dict]) -> list[dict]:
    """Group per-creative metric dicts by group_id, sum numeric fields, derive
    cost_per_result and clicked_no_message. `level` is metadata only. Sorted by
    spend desc."""
    groups: dict[str, dict] = {}
    for r in rows:
        gid = r.get("group_id") or ""
        g = groups.get(gid)
        if not g:
            g = {
                "group_id": gid, "name": r.get("group_name") or "—",
                "status": r.get("status"), "budget_label": r.get("budget_label"),
                "result_label": r.get("result_label") or "Results",
                "spend": 0.0, "impressions": 0, "reach": 0, "results": 0,
                "clicks": 0, "messages": 0, "qualified": 0, "hot": 0,
            }
            groups[gid] = g
        g["spend"] += float(r.get("spend", 0) or 0)
        g["impressions"] += int(r.get("impressions", 0) or 0)
        g["reach"] += int(r.get("reach", 0) or 0)
        g["results"] += int(r.get("results", 0) or 0)
        g["clicks"] += int(r.get("clicks", 0) or 0)
        g["messages"] += int(r.get("messages", 0) or 0)
        g["qualified"] += int(r.get("qualified", 0) or 0)
        g["hot"] += int(r.get("hot", 0) or 0)

    out = []
    for g in groups.values():
        g["spend"] = round(g["spend"], 2)
        g["cost_per_result"] = _safe_div(g["spend"], g["results"])
        g["clicked_no_message"] = max(g["clicks"] - g["messages"], 0)
        out.append(g)
    out.sort(key=lambda x: x["spend"], reverse=True)
    return out


def build_account_performance(db, tenant_id: str, *, level: str = "campaign",
                              date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """One row per campaign/adset/ad with Meta metrics + Aira funnel counts."""
    from app.services.meta_ads_insights_sync import (
        extract_result_metric,
        get_current_ads_account_id,
    )

    account = get_current_ads_account_id(db, tenant_id)
    if not account:
        return []

    creatives = (
        db.table("ad_creatives").select(
            "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,meta_campaign_id,campaign_id"
        ).eq("tenant_id", tenant_id)
        .eq("meta_ad_account_id", account)
        .eq("is_click_to_whatsapp", True)
        .execute().data
    ) or []
    if not creatives:
        return []
    creative_ids = [c["id"] for c in creatives]

    # Campaign meta (status/budget/name) by ad_campaigns.id
    camp_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    camps = {}
    if camp_ids:
        for c in (db.table("ad_campaigns").select(
            "id,campaign_name,objective,effective_status,daily_budget,lifetime_budget"
            ).eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", account)
            .in_("id", camp_ids).execute().data or []):
            camps[c["id"]] = c

    # Insights summed per creative
    ins_q = db.table("ad_insights_daily").select(
        "ad_creative_id,inline_link_clicks,spend,impressions,reach,actions"
    ).eq("tenant_id", tenant_id).eq(
        "meta_ad_account_id", account
    ).in_("ad_creative_id", creative_ids)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    ins_by_creative: dict[str, dict] = {}
    for r in (ins_q.execute().data or []):
        acc = ins_by_creative.setdefault(r["ad_creative_id"],
            {"clicks": 0, "spend": 0.0, "impressions": 0, "reach": 0, "actions": []})
        acc["clicks"] += int(r.get("inline_link_clicks", 0) or 0)
        acc["spend"] += float(r.get("spend", 0) or 0)
        acc["impressions"] += int(r.get("impressions", 0) or 0)
        acc["reach"] += int(r.get("reach", 0) or 0)
        acc["actions"].extend(r.get("actions") or [])

    # Funnel counts (messages/qualified/hot) per creative — mirrors ad_performance.py
    lead_q = db.table("leads").select("segment,attributed_ad_creative_id,created_at").eq(
        "tenant_id", tenant_id).in_("attributed_ad_creative_id", creative_ids).is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    funnel: dict[str, dict] = {}
    for lead in (lead_q.execute().data or []):
        cid = lead.get("attributed_ad_creative_id")
        if not cid:
            continue
        f = funnel.setdefault(cid, {"messages": 0, "qualified": 0, "hot": 0})
        f["messages"] += 1
        if lead.get("segment") in ("A", "B"):
            f["qualified"] += 1
        if lead.get("segment") == "A":
            f["hot"] += 1

    # Build per-creative metric rows keyed to the requested grouping level.
    per_creative = []
    for c in creatives:
        ins = ins_by_creative.get(c["id"], {"clicks": 0, "spend": 0.0, "impressions": 0, "reach": 0, "actions": []})
        fn = funnel.get(c["id"], {"messages": 0, "qualified": 0, "hot": 0})
        camp = camps.get(c.get("campaign_id"), {})
        result_label, results = extract_result_metric({
            "optimization_goal": camp.get("objective"),
            "actions": ins["actions"],
            "inline_link_clicks": ins["clicks"],
        })
        if level == "campaign":
            gid, gname = c.get("campaign_id") or "none", camp.get("campaign_name") or "Unknown Campaign"
            status = camp.get("effective_status")
            budget_label = _budget_label(camp)
        elif level == "adset":
            gid, gname = c.get("meta_adset_id") or "none", c.get("meta_adset_name") or "—"
            status, budget_label = None, None
        else:  # ad
            gid, gname = c["id"], c["creative_label"]
            status, budget_label = None, None
        per_creative.append({
            "group_id": gid, "group_name": gname, "status": status, "budget_label": budget_label,
            "result_label": result_label, "results": results,
            "spend": ins["spend"], "impressions": ins["impressions"], "reach": ins["reach"],
            "clicks": ins["clicks"], "messages": fn["messages"],
            "qualified": fn["qualified"], "hot": fn["hot"],
        })

    return roll_up_rows(level, per_creative)


def _budget_label(camp: dict) -> str | None:
    if camp.get("daily_budget"):
        return f"₹{camp['daily_budget']:.0f}/day"
    if camp.get("lifetime_budget"):
        return f"₹{camp['lifetime_budget']:.0f} total"
    return None
