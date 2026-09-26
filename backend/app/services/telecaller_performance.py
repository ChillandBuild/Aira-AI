"""Per-telecaller call totals, average score and the daily/monthly winner.

Every placed call counts toward total calls; only scored calls feed the average.
Winner points = 70% average score + 30% volume, where volume is the telecaller's
total calls relative to the busiest telecaller in the same period (x10). Days and
months are IST calendar periods.
"""
from datetime import datetime, timedelta, timezone

from app.services.call_marking import CHECKS, check_marks

IST_OFFSET = timedelta(hours=5, minutes=30)
COUNTED_STATUSES = ("completed", "no_answer", "missed")
QUALITY_WEIGHT = 0.7
VOLUME_WEIGHT = 0.3
MIN_SCORED_DAILY = 3
MIN_SCORED_MONTHLY = 20
_PAGE = 1000


def ist_day_bounds(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    ist = now + IST_OFFSET
    start = datetime(ist.year, ist.month, ist.day, tzinfo=timezone.utc) - IST_OFFSET
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


def ist_month_bounds(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    ist = now + IST_OFFSET
    start = datetime(ist.year, ist.month, 1, tzinfo=timezone.utc) - IST_OFFSET
    next_month = datetime(ist.year + (ist.month == 12), ist.month % 12 + 1, 1, tzinfo=timezone.utc) - IST_OFFSET
    return start.isoformat(), next_month.isoformat()


def _fetch_calls(db, tenant_id: str, start_iso: str, end_iso: str, caller_ids: list[str] | None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        query = (
            db.table("call_logs")
            .select("id,caller_id,status,score,score_status,evaluation")
            .eq("tenant_id", tenant_id)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .in_("status", list(COUNTED_STATUSES))
        )
        if caller_ids is not None:
            query = query.in_("caller_id", caller_ids)
        page = query.order("created_at").range(offset, offset + _PAGE - 1).execute().data or []
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


def summarize_calls(rows: list[dict]) -> dict:
    """Totals for one telecaller's calls in a period."""
    scores = [float(r["score"]) for r in rows if r.get("score_status") in ("scored",) and r.get("score") is not None]
    breakdown = {"scored": len(scores), "short_call": 0, "no_answer": 0, "not_scored": 0}
    criteria_sums: dict[str, float] = {}
    criteria_counts: dict[str, int] = {}
    for r in rows:
        status = r.get("score_status")
        if status == "scored":
            evaluation = r.get("evaluation") or {}
            for check in evaluation.get("checks") or []:
                if check.get("level") and check.get("full"):
                    key = check["key"]
                    criteria_sums[key] = criteria_sums.get(key, 0.0) + check_marks(key, check["level"]) / check["full"] * 100
                    criteria_counts[key] = criteria_counts.get(key, 0) + 1
        elif status in ("short_call", "no_answer"):
            breakdown[status] += 1
        else:
            breakdown["not_scored"] += 1
    criteria_avg = {c["key"]: round(criteria_sums[c["key"]] / criteria_counts[c["key"]], 1) for c in CHECKS if c["key"] in criteria_counts}
    return {
        "total_calls": len(rows),
        "scored_calls": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "breakdown": breakdown,
        "criteria_avg": criteria_avg,
        "weakest_criterion": min(criteria_avg, key=criteria_avg.get) if criteria_avg else None,
    }


def period_stats(db, tenant_id: str, start_iso: str, end_iso: str, caller_ids: list[str] | None = None) -> dict[str, dict]:
    """{caller_id: summary} for everyone with at least one counted call in the period."""
    by_caller: dict[str, list[dict]] = {}
    for row in _fetch_calls(db, tenant_id, start_iso, end_iso, caller_ids):
        if row.get("caller_id"):
            by_caller.setdefault(str(row["caller_id"]), []).append(row)
    return {cid: summarize_calls(rows) for cid, rows in by_caller.items()}


def rank_winner(stats: dict[str, dict], min_scored: int) -> dict | None:
    """The top telecaller by winner points, or None when nobody qualifies."""
    if not stats:
        return None
    busiest = max(s["total_calls"] for s in stats.values()) or 1
    ranked = []
    for cid, s in stats.items():
        if s["scored_calls"] < min_scored or s["avg_score"] is None:
            continue
        volume = s["total_calls"] / busiest * 100
        points = QUALITY_WEIGHT * s["avg_score"] + VOLUME_WEIGHT * volume
        ranked.append((round(points, 2), s["total_calls"], cid, round(volume, 2)))
    if not ranked:
        return None
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    points, _, cid, volume = ranked[0]
    return {
        "caller_id": cid,
        "points": points,
        "avg_score": stats[cid]["avg_score"],
        "total_calls": stats[cid]["total_calls"],
        "scored_calls": stats[cid]["scored_calls"],
        "volume_points": volume,
    }
