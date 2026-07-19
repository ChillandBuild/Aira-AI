import json
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_DEFAULT: dict = {
    "enabled": True,
    "timezone": "Asia/Kolkata",
    "open_time": "09:00",
    "close_time": "19:00",
    "working_days": [1, 2, 3, 4, 5, 6],  # ISO weekday, Mon=1 .. Sun=7
}

_DAY_NAMES = {
    1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
    5: "Friday", 6: "Saturday", 7: "Sunday",
}


def get_business_hours(tenant_id: str, db=None) -> dict:
    """Return business_hours from app_settings, merged with defaults."""
    db = db or get_supabase()
    merged = dict(_DEFAULT)
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "business_hours")
            .maybe_single()
            .execute()
        )
        if row and row.data and row.data.get("value"):
            stored = json.loads(row.data["value"])
            if isinstance(stored, dict):
                merged.update(stored)
    except Exception as e:
        logger.warning(f"get_business_hours failed for {tenant_id}: {e}")
    return merged


def save_business_hours(tenant_id: str, config: dict) -> None:
    """Persist business_hours to app_settings."""
    db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "business_hours",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


def _parse_hhmm(value: str | None, fallback: str) -> time:
    try:
        hh, mm = (value or fallback).split(":")
        return time(int(hh), int(mm))
    except Exception:
        hh, mm = fallback.split(":")
        return time(int(hh), int(mm))


def _tz(cfg: dict) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _local_now(cfg: dict, now: datetime | None) -> datetime:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(_tz(cfg))


def is_within_business_hours(cfg: dict, now: datetime | None = None) -> bool:
    """True when the tenant's office is currently open.

    False when disabled, on a non-working day, or outside the open/close
    window. Handles windows that span midnight (open 20:00, close 04:00).
    """
    if not cfg.get("enabled"):
        return False
    local = _local_now(cfg, now)
    if local.isoweekday() not in (cfg.get("working_days") or []):
        return False

    open_t = _parse_hhmm(cfg.get("open_time"), "09:00")
    close_t = _parse_hhmm(cfg.get("close_time"), "19:00")
    current = local.time()

    if open_t == close_t:
        return False
    if open_t < close_t:
        return open_t <= current < close_t
    return current >= open_t or current < close_t


def _fmt12(value: str | None, fallback: str) -> str:
    t = _parse_hhmm(value, fallback)
    suffix = "AM" if t.hour < 12 else "PM"
    hour12 = t.hour % 12 or 12
    return f"{hour12}:{t.minute:02d} {suffix}"


def describe_hours(cfg: dict) -> str:
    """Human-readable office hours for the AI prompt, e.g.
    'Monday to Saturday, 9:00 AM to 7:00 PM IST'."""
    days = sorted(cfg.get("working_days") or [])
    if not days:
        return "not currently published"

    if len(days) > 1 and days == list(range(days[0], days[-1] + 1)):
        day_str = f"{_DAY_NAMES[days[0]]} to {_DAY_NAMES[days[-1]]}"
    else:
        day_str = ", ".join(_DAY_NAMES[d] for d in days)

    tz_label = datetime.now(_tz(cfg)).tzname() or ""
    open_s = _fmt12(cfg.get("open_time"), "09:00")
    close_s = _fmt12(cfg.get("close_time"), "19:00")
    return f"{day_str}, {open_s} to {close_s} {tz_label}".strip()


def next_open_description(cfg: dict, now: datetime | None = None) -> str:
    """When the office next opens, phrased for a customer:
    'later today', 'tomorrow', or 'on Monday'."""
    working = set(cfg.get("working_days") or [])
    if not working:
        return "as soon as we reopen"

    local = _local_now(cfg, now)
    open_t = _parse_hhmm(cfg.get("open_time"), "09:00")

    if local.isoweekday() in working and local.time() < open_t:
        return "later today"

    for offset in range(1, 8):
        candidate = local + timedelta(days=offset)
        if candidate.isoweekday() in working:
            return "tomorrow" if offset == 1 else f"on {_DAY_NAMES[candidate.isoweekday()]}"
    return "as soon as we reopen"
