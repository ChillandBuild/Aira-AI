"""Rules for a sender number's health -- one place, no DB access.

Everything here reads only what Meta reported (meta_status,
meta_code_verification, quality_rating, messaging_tier) plus Anril's own
clock fields (warm_up_started_at, rested_since). Nothing is assumed: a
quality or limit Meta hasn't reported is None, and a number Meta doesn't
call CONNECTED never sends or takes over.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.meta_cloud import parse_messaging_tier

WARM_UP_DAYS = 14
REST_DAYS = 7

# (max_warm_up_day_inclusive, daily_cap) -- broadcasts from a number still
# warming up are capped; replies to customers are never capped.
_WARMUP_DAILY_CAPS: list[tuple[int, int]] = [
    (2, 50), (4, 75), (7, 100), (10, 150), (14, 250),
]

# Meta's Graph API sends GREEN/YELLOW/RED; HIGH/MEDIUM/LOW is the WhatsApp
# Manager wording. UNKNOWN (a number that hasn't sent yet) maps to None.
_QUALITY_MAP = {
    "GREEN": "green", "YELLOW": "yellow", "RED": "red",
    "HIGH": "green", "MEDIUM": "yellow", "LOW": "red",
}


def map_quality(raw: Optional[str]) -> Optional[str]:
    return _QUALITY_MAP.get((raw or "").upper())


def meta_snapshot(meta: dict) -> dict:
    """Meta's phone-number fields -> phone_numbers columns. Keys whose value
    Meta didn't send are left out, so callers never overwrite with a guess."""
    out: dict = {"quality_rating": map_quality(meta.get("quality_rating"))}
    tier = parse_messaging_tier(meta)
    if tier:
        out["messaging_tier"] = tier
    if meta.get("status"):
        out["meta_status"] = str(meta["status"]).upper()
    if meta.get("code_verification_status"):
        out["meta_code_verification"] = str(meta["code_verification_status"]).upper()
    return out


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def is_meta_connected(row: dict) -> bool:
    return (row.get("meta_status") or "").upper() == "CONNECTED"


def warm_up_day(row: dict, now: datetime) -> int:
    started = _parse_ts(row.get("warm_up_started_at"))
    if not started:
        return 0
    return max(0, min(WARM_UP_DAYS, (now - started).days))


def rest_day(row: dict, now: datetime) -> int:
    since = _parse_ts(row.get("rested_since"))
    if not since:
        return 0
    return max(0, (now - since).days)


def is_resting(row: dict) -> bool:
    return row.get("status") == "restricted"


def warmup_daily_cap(day: int) -> int:
    for max_day, cap in _WARMUP_DAILY_CAPS:
        if day <= max_day:
            return cap
    return _WARMUP_DAILY_CAPS[-1][1]


def broadcast_cap(row: dict, now: datetime) -> Optional[int]:
    """Today's broadcast cap for this number, or None when Meta hasn't
    reported a messaging limit (the number can't broadcast until it does)."""
    tier = row.get("messaging_tier")
    if not tier:
        return None
    day = warm_up_day(row, now)
    if day < WARM_UP_DAYS:
        return min(tier, warmup_daily_cap(day))
    return tier


def portfolio_limit(rows: list[dict]) -> Optional[int]:
    """The business's one daily limit, shared by all its numbers, or None when
    Meta hasn't reported it on any of them."""
    tiers = [r["messaging_tier"] for r in rows if r.get("messaging_tier")]
    return max(tiers) if tiers else None


def can_broadcast(row: dict, now: datetime, unlocked_ids: set[str]) -> bool:
    """May this number send broadcasts right now (before today's count)?"""
    return (
        is_meta_connected(row)
        and row.get("status") in ("active", "warming")
        and row.get("quality_rating") != "red"
        and not row.get("paused_outbound")
        and row["id"] in unlocked_ids
        and broadcast_cap(row, now) is not None
    )


def standby_candidates(rows: list[dict], exclude_id: Optional[str], unlocked_ids: set[str]) -> list[dict]:
    """Standbys that may take over as primary, best first: CONNECTED on Meta,
    not paused, not resting, not Red, not locked. A number still warming up
    qualifies (its broadcasts stay capped); the one furthest into warm-up wins."""
    now = datetime.now(timezone.utc)
    pool = [
        r for r in rows
        if r.get("id") != exclude_id
        and r.get("role") == "standby"
        and r.get("status") in ("active", "warming")
        and is_meta_connected(r)
        and r.get("quality_rating") != "red"
        and not r.get("paused_outbound")
        and r["id"] in unlocked_ids
    ]
    return sorted(pool, key=lambda r: warm_up_day(r, now), reverse=True)


def recovered(row: dict, now: datetime) -> bool:
    """A resting number is back once it has rested 7 days AND Meta reports Green."""
    return is_resting(row) and rest_day(row, now) >= REST_DAYS and row.get("quality_rating") == "green"


def lifecycle_updates(row: dict, now: datetime, unlocked: bool) -> dict:
    """Status/warm-up changes implied by the row's current Meta snapshot.
    Does not handle turning Red -- that's failover.handle_quality_red."""
    updates: dict = {}
    if is_meta_connected(row) and not row.get("warm_up_started_at"):
        updates["warm_up_started_at"] = now.isoformat()
        row = {**row, **updates}

    day = warm_up_day(row, now)
    if day != row.get("warm_up_day"):
        updates["warm_up_day"] = day

    status = row.get("status")
    if status == "restricted":
        if recovered(row, now):
            updates["rested_since"] = None
            updates["status"] = "active" if day >= WARM_UP_DAYS and unlocked else "warming"
    elif status in ("active", "warming"):
        ready = is_meta_connected(row) and day >= WARM_UP_DAYS and unlocked
        target = "active" if ready else "warming"
        if target != status:
            updates["status"] = target
    return updates


def health(row: dict, now: datetime) -> dict:
    """What the Sender Numbers page shows, derived only from Meta's fields
    and Anril's clocks. state is one of: archived, meta_pending, resting,
    warming, active."""
    day = warm_up_day(row, now)
    base = {
        "meta_status": row.get("meta_status"),
        "meta_code_verification": row.get("meta_code_verification"),
        "warm_up_day": day,
        "warm_up_days": WARM_UP_DAYS,
        "rest_day": rest_day(row, now),
        "rest_days": REST_DAYS,
        "broadcast_cap": broadcast_cap(row, now),
    }
    if row.get("status") == "archived":
        return {**base, "state": "archived"}
    if not is_meta_connected(row):
        return {**base, "state": "meta_pending"}
    if is_resting(row):
        return {**base, "state": "resting"}
    if day < WARM_UP_DAYS:
        return {**base, "state": "warming"}
    return {**base, "state": "active"}
