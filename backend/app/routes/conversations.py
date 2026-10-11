import logging
from fastapi import APIRouter, Depends, Query
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission

logger = logging.getLogger(__name__)
router = APIRouter()
require_conversations_view = require_permission("conversations.view")


@router.get("")
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    folder: str = Query(default="chats", pattern="^(chats|archived|blocked)$"),
    q: str | None = Query(default=None, max_length=100),
    ctx: dict = Depends(require_conversations_view),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]

    rpc_params = {"p_tenant_id": tenant_id, "p_limit": limit, "p_offset": offset}
    search = q.strip() if q else None
    if search:
        rpc_params["p_search"] = search

    rpc_rows = db.rpc("get_conversation_leads", rpc_params).execute()

    rows = rpc_rows.data or []
    if not rows:
        return {"leads": [], "total": 0}

    total = int(rows[0].get("total", 0)) if rows else 0
    lead_ids = [r["lead_id"] for r in rows if r.get("lead_id")]
    last_reply_map = {r["lead_id"]: r["last_reply_at"] for r in rows if r.get("lead_id")}
    last_message_map = {r["lead_id"]: r.get("last_message_content") for r in rows if r.get("lead_id")}

    if not lead_ids:
        return {"leads": [], "total": 0}

    # Opted-out leads who actually reply must stay visible — the RPC only returns
    # leads with real conversation activity (an inbound reply or a non-template
    # outbound), so we keep them here and let the UI badge them as opted-out.
    # Excluding them silently dropped re-engaged opt-outs from the inbox.
    lead_query = (
        db.table("leads")
        .select("*")
        .in_("id", lead_ids)
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
    )

    # Inbox folders. Default "chats" hides archived + blocked; the folder views
    # surface exactly one of them.
    if folder == "archived":
        lead_query = lead_query.not_.is_("archived_at", "null")
    elif folder == "blocked":
        lead_query = lead_query.not_.is_("blocked_at", "null")
    else:
        lead_query = lead_query.is_("archived_at", "null").is_("blocked_at", "null")

    # Callers see their assigned leads PLUS any lead in the shared escalation
    # pool (a pending handover sets needs_human_attention) so they can resolve it.
    if ctx.get("role") == "caller" and ctx.get("caller_id"):
        lead_query = lead_query.or_(
            f"assigned_to.eq.{ctx['caller_id']},needs_human_attention.eq.true"
        )

    lead_rows = lead_query.execute()

    lead_map = {l["id"]: l for l in (lead_rows.data or [])}
    last_sender = _last_message_senders(db, tenant_id, last_reply_map)
    leads = []
    for lid in lead_ids:
        if lid in lead_map:
            lead = dict(lead_map[lid])
            lead["last_reply_at"] = last_reply_map.get(lid)
            lead["last_message_content"] = last_message_map.get(lid)
            # Who sent the last message: lets the inbox say "AI replied" only when it did.
            sender = last_sender.get(lid)
            lead["last_message_direction"] = sender["direction"] if sender else None
            lead["last_message_is_ai"] = bool(sender and sender.get("is_ai_generated")) if sender else None
            leads.append(lead)

    return {"leads": leads, "total": total}


def _last_message_senders(db, tenant_id: str, last_reply_map: dict) -> dict:
    """lead_id -> {direction, is_ai_generated} of that lead's latest message.

    One query for the whole page: messages newer than the page's oldest activity,
    newest first, keeping the first row seen per lead. A lead whose last message
    falls outside the window is simply left out (the inbox then shows no sender tag)."""
    times = [t for t in last_reply_map.values() if t]
    if not times:
        return {}
    try:
        rows = (
            db.table("messages")
            .select("lead_id,direction,is_ai_generated,created_at")
            .eq("tenant_id", tenant_id)
            .in_("lead_id", list(last_reply_map.keys()))
            .gte("created_at", min(times))
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        ).data or []
    except Exception as e:
        logger.warning(f"last message sender lookup failed: {e}")
        return {}
    senders: dict = {}
    for r in rows:
        senders.setdefault(r["lead_id"], r)
    return senders
