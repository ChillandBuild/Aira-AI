"""Meta's edit limit for approved templates.

Meta: "Approved templates can be edited up to 10 times in a 30-day window, or
1 time in a 24-hour window." Rejected and paused templates can be edited any
number of times. Edits are logged in template_edit_log -- both Anril's own and
the ones Meta reports from WhatsApp Manager -- because Meta counts all of them.
"""
from datetime import datetime, timedelta, timezone

EDITS_PER_DAY = 1
EDITS_PER_30_DAYS = 10
_DAY = timedelta(hours=24)
_30_DAYS = timedelta(days=30)
# Meta also reports Anril's own edit as a components update; one arriving this
# soon after an Anril edit is that same edit, not a second one.
_SAME_EDIT_WINDOW = timedelta(minutes=15)
_IST = timedelta(hours=5, minutes=30)


def _ts(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def edit_allowance(edits: list, now: datetime | None = None) -> dict:
    """Can this approved template be edited now? edits = times of past edits."""
    now = now or datetime.now(timezone.utc)
    times = sorted(_ts(e) for e in edits)
    last_day = [t for t in times if now - t < _DAY]
    last_30 = [t for t in times if now - t < _30_DAYS]
    base = {"edits_30_days": len(last_30), "limit_30_days": EDITS_PER_30_DAYS}
    if len(last_day) >= EDITS_PER_DAY:
        return {**base, "allowed": False, "reason": "daily", "next_allowed_at": (last_day[0] + _DAY).isoformat()}
    if len(last_30) >= EDITS_PER_30_DAYS:
        # The oldest edit that still counts drops out of the window first.
        oldest_counted = last_30[len(last_30) - EDITS_PER_30_DAYS]
        return {**base, "allowed": False, "reason": "monthly", "next_allowed_at": (oldest_counted + _30_DAYS).isoformat()}
    return {**base, "allowed": True, "reason": None, "next_allowed_at": None}


def blocked_message(allowance: dict) -> str:
    when = _ts(allowance["next_allowed_at"]) + _IST
    if allowance["reason"] == "daily":
        return (f"Meta allows one edit of an approved template every 24 hours. "
                f"You can edit this again from {when:%d %b, %I:%M %p} (India time).")
    return (f"Meta's limit of {EDITS_PER_30_DAYS} edits in 30 days is used up for this template. "
            f"You can edit it again from {when:%d %b, %I:%M %p} (India time).")


def load_edits(db, tenant_id: str, template_ids: list[str]) -> dict[str, list[str]]:
    if not template_ids:
        return {}
    since = (datetime.now(timezone.utc) - _30_DAYS).isoformat()
    rows = (
        db.table("template_edit_log").select("template_id,edited_at")
        .eq("tenant_id", tenant_id).in_("template_id", template_ids).gte("edited_at", since)
        .execute().data or []
    )
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["template_id"], []).append(r["edited_at"])
    return out


def record_edit(db, tenant_id: str, template_id: str, source: str) -> None:
    db.table("template_edit_log").insert({"tenant_id": tenant_id, "template_id": template_id, "source": source}).execute()


def is_echo_of_anril_edit(db, template_id: str) -> bool:
    since = (datetime.now(timezone.utc) - _SAME_EDIT_WINDOW).isoformat()
    rows = (
        db.table("template_edit_log").select("id")
        .eq("template_id", template_id).eq("source", "anril").gte("edited_at", since)
        .limit(1).execute().data or []
    )
    return bool(rows)
