"""Attendance resolution: admin overrides win, else derive from caller_status_logs activity."""
from datetime import date, datetime, timedelta, timezone


def mark_activity_today(db, caller_id: str, tenant_id: str) -> None:
    """Best-effort presence marker: ensure today has a caller_status_logs row.

    Called from real work events (e.g. dialing a call) so attendance reflects
    actual activity even if the login ping (SessionTracker) never re-fires —
    a long-lived PWA session that stays open across midnight is the common case.
    """
    today_start = date.today().isoformat()
    existing = (
        db.table("caller_status_logs")
        .select("id")
        .eq("caller_id", caller_id)
        .gte("started_at", f"{today_start}T00:00:00")
        .limit(1)
        .execute()
    )
    if existing.data:
        return
    db.table("caller_status_logs").insert({
        "caller_id": caller_id,
        "tenant_id": tenant_id,
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def resolve_day_status(
    target_date: date,
    today: date,
    override_status: str | None,
    has_activity: bool,
) -> str:
    """Resolve a single day's attendance status.

    Priority: holiday override > future dates > admin override > activity-derived presence.
    A holiday override wins even on future dates (so admins can pre-mark upcoming
    holidays) and even if the caller later logs in that day (login/logout activity
    is still recorded as usual, but the attendance status stays "holiday" unless an
    admin manually overrides it to "present"/"absent").
    """
    if override_status == "holiday":
        return "holiday"
    if target_date > today:
        return "future"
    if override_status in ("present", "absent"):
        return override_status
    return "present" if has_activity else "absent"


def date_range(start: date, end: date) -> list[date]:
    """Inclusive list of dates from start to end."""
    span = (end - start).days
    return [start + timedelta(days=i) for i in range(span + 1)]


def build_attendance_map(
    days: list[date],
    today: date,
    overrides: dict[str, str],
    active_dates: set[str],
) -> dict[str, str]:
    """Build {date_iso: status} for one caller given pre-fetched overrides/activity."""
    result: dict[str, str] = {}
    for d in days:
        ds = d.isoformat()
        result[ds] = resolve_day_status(d, today, overrides.get(ds), ds in active_dates)
    return result


def compute_team_summary(grid: dict[str, dict[str, str]], today_iso: str) -> dict:
    """Compute present/absent today + month-to-date attendance rate across all callers."""
    present_today = sum(1 for day_map in grid.values() if day_map.get(today_iso) == "present")
    absent_today = sum(1 for day_map in grid.values() if day_map.get(today_iso) == "absent")
    present_count = 0
    marked_count = 0
    for day_map in grid.values():
        for status in day_map.values():
            if status == "present":
                present_count += 1
                marked_count += 1
            elif status == "absent":
                marked_count += 1
    rate = round(present_count / marked_count, 2) if marked_count else 0.0
    return {
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_rate_month": rate,
    }
