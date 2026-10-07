"""'This week: Anril handled 71 of 84 chats.' A per-chat aggregation over the last 7 days
in Asia/Kolkata (no per-chat counter exists; the existing ones are per message).

Definitions (blueprint section 7):
  chats            leads with at least one inbound message in the window
  handed_over      chats with a chat_handovers row opened in the window
  handled_by_aira  chats with at least one AI reply outbound and no handover
  unanswered       the rest

AI reply vs human, verified in code: an AI reply is stored is_ai_generated=true with
reply_source 'ai' or 'knowledge' (ai_reply.py:1933-1934, 2139-2140). A human reply is
is_ai_generated=false with no reply_source (routes/leads.py:915-923). is_ai_generated
alone is NOT enough: the canned reply after an LLM exception is is_ai_generated=false with
reply_source='ai' (ai_reply.py:2005-2007), and follow-ups (routes/follow_ups.py:105-112)
are is_ai_generated=true with no reply_source. So a reply counts as Anril's answer only when
both hold: is_ai_generated true AND reply_source in ('ai', 'knowledge')."""
import time
from datetime import datetime, timedelta
from datetime import time as clock_time
from zoneinfo import ZoneInfo

from app.services.brain import handovers as handover_kinds
from app.services.brain.paging import fetch_bounded

IST = ZoneInfo("Asia/Kolkata")
WINDOW_DAYS = 7
AI_REPLY_SOURCES = frozenset({"ai", "knowledge"})
CACHE_TTL_SECONDS = 60  # the hub polls; the headline scans a week of messages

# tenant_id -> (monotonic time computed, result). In-process, so each worker keeps its own.
_cache: dict[str, tuple[float, dict]] = {}


def clear_cache() -> None:
    _cache.clear()


def window_start(now: datetime | None = None) -> datetime:
    """Midnight IST, WINDOW_DAYS-1 days before today (today counts as day 7)."""
    local_now = (now or datetime.now(IST)).astimezone(IST)
    first_day = local_now.date() - timedelta(days=WINDOW_DAYS - 1)
    return datetime.combine(first_day, clock_time.min, tzinfo=IST)


def is_aira_reply(message: dict) -> bool:
    return (
        message.get("direction") == "outbound"
        and message.get("is_ai_generated") is True
        and message.get("reply_source") in AI_REPLY_SOURCES
    )


def aggregate(messages: list[dict], handovers: list[dict]) -> dict:
    """Pure: messages and handovers already limited to the window and one tenant."""
    chats = {m["lead_id"] for m in messages if m.get("direction") == "inbound"}
    answered = {m["lead_id"] for m in messages if is_aira_reply(m)}
    kinds_by_chat: dict[str, set[str]] = {}
    for h in handovers:
        if h["lead_id"] in chats:
            kinds_by_chat.setdefault(h["lead_id"], set()).add(handover_kinds.classify_reason(h.get("reason")))
    top_kinds = [next(k for k in handover_kinds.KIND_PRIORITY if k in kinds) for kinds in kinds_by_chat.values()]
    handed = set(kinds_by_chat)
    handled = (chats & answered) - handed
    return {
        "chats": len(chats),
        "handled_by_aira": len(handled),
        "handed_over": len(handed),
        "unanswered": len(chats - handed - handled),
        "window_days": WINDOW_DAYS,
        "asked_for_human": top_kinds.count(handover_kinds.KIND_ASKED_FOR_HUMAN),
        "knowledge_gaps": top_kinds.count(handover_kinds.KIND_KNOWLEDGE_GAP),
    }


def build_headline(db, tenant_id: str, *, now: datetime | None = None) -> dict:
    """The headline, recomputed at most once per CACHE_TTL_SECONDS per tenant."""
    cached = _cache.get(tenant_id)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return dict(cached[1])
    result = _compute_headline(db, tenant_id, now)
    _cache[tenant_id] = (time.monotonic(), result)
    return dict(result)


def _compute_headline(db, tenant_id: str, now: datetime | None) -> dict:
    since = window_start(now).isoformat()
    messages = fetch_bounded(
        lambda: db.table("messages")
        .select("lead_id,direction,is_ai_generated,reply_source")
        .eq("tenant_id", tenant_id)
        .gte("created_at", since)
        .order("created_at")
        .order("id"),  # unique tiebreaker: equal timestamps must not shuffle across pages
        "headline messages",
    )
    opened = fetch_bounded(
        lambda: db.table("chat_handovers")
        .select("lead_id,reason")
        .eq("tenant_id", tenant_id)
        .gte("opened_at", since)
        .order("opened_at")
        .order("id"),
        "headline handovers",
    )
    return aggregate(messages, opened)
