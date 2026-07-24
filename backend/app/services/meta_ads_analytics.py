"""Analytics series for the Meta Ads dashboard Analytics tab. Builds funnel,
leaderboard, trend, heatmap, quadrant and spend-distribution from the same
tables as meta_ads_reporting. Revenue/ROAS deliberately absent — no conversion
value source exists yet (see spec)."""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))


def funnel_stages(clicks: int, messages: int, qualified: int, hot: int) -> list[dict]:
    return [
        {"stage": "Clicked", "count": int(clicks)},
        {"stage": "Messaged", "count": int(messages)},
        {"stage": "Qualified", "count": int(qualified)},
        {"stage": "Hot", "count": int(hot)},
    ]


def leaderboard_sort(rows: list[dict]) -> list[dict]:
    """Worst (highest) cost_per_hot first; None costs sorted last."""
    return sorted(rows, key=lambda r: (r["cost_per_hot"] is None, -(r["cost_per_hot"] or 0)))


def build_analytics(db, tenant_id: str, *, date_from: str | None = None,
                    date_to: str | None = None) -> dict:
    from app.services.meta_ads_reporting import build_account_performance

    per_creative = build_account_performance(db, tenant_id, level="ad",
                                             date_from=date_from, date_to=date_to)

    tot_clicks = sum(r["clicks"] for r in per_creative)
    tot_msgs = sum(r["messages"] for r in per_creative)
    tot_qual = sum(r["qualified"] for r in per_creative)
    tot_hot = sum(r["hot"] for r in per_creative)
    tot_spend = round(sum(r["spend"] for r in per_creative), 2)

    leaderboard = leaderboard_sort([
        {"name": r["name"],
         "cost_per_hot": round(r["spend"] / r["hot"], 2) if r["hot"] else None,
         "hot": r["hot"], "spend": r["spend"]}
        for r in per_creative
    ])
    quadrant = [
        {"name": r["name"], "spend": r["spend"],
         "cost_per_hot": round(r["spend"] / r["hot"], 2) if r["hot"] else None, "hot": r["hot"]}
        for r in per_creative if r["spend"] > 0
    ]
    spend_distribution = [{"name": r["name"], "spend": r["spend"]} for r in per_creative if r["spend"] > 0]

    return {
        "kpis": {
            "spend": tot_spend, "messages": tot_msgs, "qualified": tot_qual, "hot": tot_hot,
            "cost_per_hot": round(tot_spend / tot_hot, 2) if tot_hot else None,
            "roas": None, "revenue_available": False,
        },
        "funnel": funnel_stages(tot_clicks, tot_msgs, tot_qual, tot_hot),
        "leaderboard": leaderboard[:12],
        "trend": _build_trend(db, tenant_id, date_from, date_to),
        "heatmap": _build_heatmap(db, tenant_id, date_from, date_to),
        "quadrant": quadrant,
        "spend_distribution": spend_distribution,
    }


def _build_trend(db, tenant_id, date_from, date_to) -> list[dict]:
    """spend/day (from insights) joined with qualified-leads/day (from leads, IST)."""
    ins_q = db.table("ad_insights_daily").select("insight_date,spend").eq("tenant_id", tenant_id)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    spend_by_day: dict[str, float] = {}
    for r in (ins_q.execute().data or []):
        spend_by_day[r["insight_date"]] = spend_by_day.get(r["insight_date"], 0.0) + float(r.get("spend", 0) or 0)

    lead_q = db.table("leads").select("segment,created_at").eq("tenant_id", tenant_id).in_(
        "segment", ["A", "B"]).not_.is_("attributed_ad_creative_id", "null").is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    qual_by_day: dict[str, int] = {}
    for lead in (lead_q.execute().data or []):
        d = _ist_date(lead.get("created_at"))
        if d:
            qual_by_day[d] = qual_by_day.get(d, 0) + 1

    days = sorted(set(spend_by_day) | set(qual_by_day))
    return [{"date": d, "spend": round(spend_by_day.get(d, 0.0), 2),
             "qualified": qual_by_day.get(d, 0)} for d in days]


def _build_heatmap(db, tenant_id, date_from, date_to) -> list[dict]:
    """qualified leads by IST day-of-week (0=Mon) × hour (0-23)."""
    lead_q = db.table("leads").select("segment,created_at").eq("tenant_id", tenant_id).in_(
        "segment", ["A", "B"]).not_.is_("attributed_ad_creative_id", "null").is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    grid: dict[tuple[int, int], int] = {}
    for lead in (lead_q.execute().data or []):
        dt = _ist_dt(lead.get("created_at"))
        if not dt:
            continue
        key = (dt.weekday(), dt.hour)
        grid[key] = grid.get(key, 0) + 1
    return [{"dow": dow, "hour": hour, "qualified": count} for (dow, hour), count in sorted(grid.items())]


def _ist_dt(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_IST)
    except Exception:
        return None


def _ist_date(iso: str | None):
    dt = _ist_dt(iso)
    return dt.strftime("%Y-%m-%d") if dt else None
