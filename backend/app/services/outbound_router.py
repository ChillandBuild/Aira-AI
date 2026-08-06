import logging

from app.db.supabase import get_supabase
from app.services.numbers_pool import get_unlocked_number_ids

logger = logging.getLogger(__name__)

_TIER_DAILY_LIMITS: dict[int, int] = {1000: 1_000, 10000: 10_000, 100000: 100_000}

_WARMUP_DAILY_CAPS: list[tuple[int, int]] = [
    # (max_warm_up_day_inclusive, daily_cap)
    (2, 50), (4, 75), (7, 100), (10, 150), (14, 250),
]


def _warmup_daily_cap(warm_up_day: int) -> int:
    for max_day, cap in _WARMUP_DAILY_CAPS:
        if warm_up_day <= max_day:
            return cap
    return 250


async def get_best_number(tenant_id: str) -> dict | None:
    db = get_supabase()
    rows = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .neq("quality_rating", "red")
        .gte("warm_up_day", 14)
        .eq("paused_outbound", False)
        .execute()
        .data
        or []
    )
    if not rows:
        logger.warning("No healthy outbound numbers available")
        return None

    unlocked_ids = get_unlocked_number_ids(db, tenant_id)
    rows = [r for r in rows if r["id"] in unlocked_ids]
    if not rows:
        logger.warning("All outbound numbers are locked by the numbers pool quota")
        return None

    def _sort_key(row: dict) -> tuple:
        # green before yellow (alphabetically, "green" < "yellow")
        quality_rank = 0 if row.get("quality_rating", "").lower() == "green" else 1
        tier = row.get("messaging_tier") or 1000
        ratio = (row.get("daily_send_count") or 0) / tier
        return (quality_rank, ratio)

    rows = [
        r for r in rows
        if (r.get("daily_send_count") or 0) < _TIER_DAILY_LIMITS.get(r.get("messaging_tier") or 1000, 1_000)
    ]
    if not rows:
        logger.warning("All outbound numbers have hit their daily tier limit")
        return None

    rows = [
        r for r in rows
        if r.get("status") != "warming" or (r.get("daily_send_count") or 0) < _warmup_daily_cap(r.get("warm_up_day") or 0)
    ]
    if not rows:
        logger.warning("All outbound numbers have hit their daily warm-up cap")
        return None

    rows.sort(key=_sort_key)
    return rows[0]


async def increment_send_count(number_id: str, delta: int = 1) -> None:
    db = get_supabase()
    # Atomic increment via Postgres function to avoid read-modify-write races.
    db.rpc(
        "increment_phone_daily_send_count",
        {"row_id": number_id, "delta": delta},
    ).execute()


async def reset_daily_counts() -> None:
    db = get_supabase()
    db.table("phone_numbers").update({"daily_send_count": 0}).neq(
        "id", ""
    ).execute()
