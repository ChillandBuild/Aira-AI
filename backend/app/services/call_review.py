"""Call Review: per-lead roll-up of one telecaller's calls and notes in a date range.

The admin page lists every lead the telecaller owns, called or wrote a note on,
and shows totals above the list. The totals are summed from these rows on the
client, so they always match the visible filters.
"""
from app.services.call_wrapup import cloud_never_connected

NEEDS_REVIEW_BELOW = 60


def is_connected(call: dict) -> bool:
    if call.get("manual_status") == "connected":
        return True
    return not cloud_never_connected(call) and (call.get("duration_seconds") or 0) > 0


def summarize_leads(
    calls: list[dict],
    notes: list[dict],
    leads: list[dict],
    assigned_ids: set[str],
) -> list[dict]:
    """One row per lead, most recent activity first; assigned-but-untouched leads last."""
    rows: dict[str, dict] = {}
    for lead in leads:
        lid = str(lead["id"])
        rows[lid] = {
            **lead,
            "id": lid,
            "assigned": lid in assigned_ids,
            "calls": 0,
            "connected": 0,
            "talk_seconds": 0,
            "scored": 0,
            "score_sum": 0.0,
            "avg_score": None,
            "early_exits": 0,
            "needs_review": False,
            "notes": 0,
            "last_call_at": None,
            "last_call": None,
            "last_activity_at": None,
        }

    for call in sorted(calls, key=lambda c: c.get("created_at") or ""):
        row = rows.get(str(call.get("lead_id")))
        if row is None:
            continue
        row["calls"] += 1
        if is_connected(call):
            row["connected"] += 1
            row["talk_seconds"] += call.get("duration_seconds") or 0
        status = call.get("score_status")
        if status == "scored" and call.get("score") is not None:
            score = float(call["score"])
            row["scored"] += 1
            row["score_sum"] += score
            if score < NEEDS_REVIEW_BELOW:
                row["needs_review"] = True
        elif status == "early_exit":
            row["early_exits"] += 1
        row["last_call_at"] = call.get("created_at")
        row["last_call"] = {
            "score": call.get("score"),
            "score_status": status,
            "call_group": call.get("call_group"),
            "provider": call.get("provider"),
        }
        row["last_activity_at"] = max(row["last_activity_at"] or "", call.get("created_at") or "") or None

    for note in notes:
        row = rows.get(str(note.get("lead_id")))
        if row is None:
            continue
        row["notes"] += 1
        row["last_activity_at"] = max(row["last_activity_at"] or "", note.get("created_at") or "") or None

    for row in rows.values():
        row["score_sum"] = round(row["score_sum"], 2)
        if row["scored"]:
            row["avg_score"] = round(row["score_sum"] / row["scored"], 1)

    return sorted(rows.values(), key=lambda r: r["last_activity_at"] or "", reverse=True)
