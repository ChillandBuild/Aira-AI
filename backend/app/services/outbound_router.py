import logging
from datetime import datetime, timezone

from app.db.supabase import get_supabase
from app.services.number_health import broadcast_cap, can_broadcast, portfolio_limit
from app.services.numbers_pool import get_unlocked_number_ids

logger = logging.getLogger(__name__)

# Re-read the pool every N sends so a mid-broadcast failover (or a pause) is
# picked up without a DB round-trip per message.
_REFRESH_EVERY = 5


def _eligible(rows: list[dict], sent_now: dict[str, int], unlocked_ids: set[str]) -> list[dict]:
    """Numbers that may broadcast now and are under today's cap, primary first,
    then green before unrated/yellow, then least used."""
    now = datetime.now(timezone.utc)
    # Meta's limit belongs to the business portfolio and every number shares
    # it (Meta reports the same value on each), so today's sends are summed
    # across the pool -- per-number caps alone would let a second number
    # broadcast past it once the first is full.
    limit = portfolio_limit(rows)
    pool_used = sum((r.get("daily_send_count") or 0) + sent_now.get(r["id"], 0) for r in rows)
    if limit is None or pool_used >= limit:
        return []
    out = []
    for r in rows:
        if not can_broadcast(r, now, unlocked_ids):
            continue
        used = (r.get("daily_send_count") or 0) + sent_now.get(r["id"], 0)
        cap = broadcast_cap(r, now)
        if used >= cap:
            continue
        out.append((r, used / cap))

    def _key(item: tuple[dict, float]) -> tuple:
        r, ratio = item
        return (0 if r.get("role") == "primary" else 1, 0 if r.get("quality_rating") == "green" else 1, ratio)

    return [r for r, _ in sorted(out, key=_key)]


def _load_rows(db, tenant_id: str) -> list[dict]:
    return (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .neq("status", "archived")
        .execute()
        .data
        or []
    )


async def get_best_number(tenant_id: str) -> dict | None:
    db = get_supabase()
    rows = _eligible(_load_rows(db, tenant_id), {}, get_unlocked_number_ids(db, tenant_id))
    if not rows:
        logger.warning(f"No number can broadcast right now for tenant {tenant_id}")
        return None
    return rows[0]


class SenderPicker:
    """Chooses the sender for each broadcast message. Counts each send
    against the number's daily cap as it goes, and re-reads the pool every
    few sends so a failover mid-broadcast moves the rest to the new primary."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._db = get_supabase()
        self._rows: list[dict] = []
        self._unlocked: set[str] = set()
        self._sent_since_refresh: dict[str, int] = {}
        self._calls = 0
        self.used_numbers: list[str] = []

    def _refresh(self) -> None:
        self._rows = _load_rows(self._db, self.tenant_id)
        self._unlocked = get_unlocked_number_ids(self._db, self.tenant_id)
        self._sent_since_refresh = {}

    def next(self) -> dict | None:
        if self._calls % _REFRESH_EVERY == 0:
            self._refresh()
        self._calls += 1
        rows = _eligible(self._rows, self._sent_since_refresh, self._unlocked)
        if not rows:
            # Counts may be stale-high or a standby may just have been promoted.
            self._refresh()
            rows = _eligible(self._rows, {}, self._unlocked)
        return rows[0] if rows else None

    async def record_sent(self, number: dict) -> None:
        self._sent_since_refresh[number["id"]] = self._sent_since_refresh.get(number["id"], 0) + 1
        if number.get("number") and number["number"] not in self.used_numbers:
            self.used_numbers.append(number["number"])
        await increment_send_count(number["id"], delta=1)

    def numbers_used_label(self) -> str | None:
        return ", ".join(self.used_numbers) or None


async def increment_send_count(number_id: str, delta: int = 1) -> None:
    db = get_supabase()
    # Atomic increment via Postgres function to avoid read-modify-write races.
    db.rpc(
        "increment_phone_daily_send_count",
        {"row_id": number_id, "delta": delta},
    ).execute()


async def reset_daily_counts() -> None:
    """Midnight IST: today's broadcast counts start over."""
    db = get_supabase()
    db.table("phone_numbers").update({
        "daily_send_count": 0,
        "last_reset_at": datetime.now(timezone.utc).isoformat(),
    }).gt("daily_send_count", 0).execute()
