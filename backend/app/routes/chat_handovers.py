import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()
require_conversations_view = require_permission("conversations.view")
require_conversations_reply = require_permission("conversations.reply")


@router.get("/")
def list_handovers(ctx: dict = Depends(require_conversations_view)):
    db = get_supabase()
    query = (
        db.table("chat_handovers")
        .select("id, lead_id, assigned_to, reason, status, opened_at, leads(name, phone, segment, source, tg_username, ig_user_id, fb_user_id)")
        .eq("tenant_id", ctx["tenant_id"])
        .eq("status", "pending")
        .order("opened_at", desc=True)
        .limit(50)
    )
    # Shared escalation pool: all tenant users (admin + every telecaller) see all
    # pending handovers, so whoever is free can pick one up and resolve it.
    try:
        rows = query.execute()
    except Exception as e:
        logger.warning(f"chat_handovers list failed (transient?): {e}")
        return {"data": []}

    handovers = rows.data or []

    # Attach caller names in one batch lookup
    caller_ids = list({h["assigned_to"] for h in handovers if h.get("assigned_to")})
    caller_map: dict = {}
    if caller_ids:
        try:
            callers = db.table("callers").select("id, name").in_("id", caller_ids).execute()
            caller_map = {c["id"]: c["name"] for c in (callers.data or [])}
        except Exception:
            pass
    for h in handovers:
        h["caller_name"] = caller_map.get(h.get("assigned_to")) if h.get("assigned_to") else None

    return {"data": handovers}


@router.get("/count")
def handover_count(ctx: dict = Depends(require_conversations_view)):
    """Sidebar badge polls this every 60s. Swallow transient Supabase
    HTTP/2 disconnects (RemoteProtocolError) so a flaky connection doesn't
    spam 500s into the UI — the next poll will succeed."""
    db = get_supabase()
    query = (
        db.table("chat_handovers")
        .select("id", count="exact")
        .eq("tenant_id", ctx["tenant_id"])
        .eq("status", "pending")
    )
    # Shared escalation pool: all tenant users (admin + every telecaller) see all
    # pending handovers, so whoever is free can pick one up and resolve it.
    try:
        result = query.execute()
    except Exception as e:
        logger.warning(f"chat_handovers count failed (transient?): {e}")
        return {"count": 0}
    return {"count": result.count or 0}


class AssignBody(BaseModel):
    caller_id: str


@router.patch("/{handover_id}/assign")
def assign_handover(handover_id: str, body: AssignBody, ctx: dict = Depends(require_conversations_reply)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    caller = (
        db.table("callers")
        .select("id")
        .eq("id", body.caller_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not caller.data:
        raise HTTPException(status_code=404, detail="Caller not found")
    result = (
        db.table("chat_handovers")
        .update({"assigned_to": body.caller_id})
        .eq("id", handover_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Handover not found")
    try:
        from app.services.notify import clear_pool_notifications_for_lead
        lead_id = result.data[0].get("lead_id")
        if lead_id:
            clear_pool_notifications_for_lead(tenant_id, lead_id, db=db)
    except Exception:
        pass
    return {"assigned": True}


@router.patch("/{handover_id}/resolve")
def resolve_handover(handover_id: str, ctx: dict = Depends(require_conversations_reply)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    result = db.table("chat_handovers").update({
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", handover_id).eq("tenant_id", tenant_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Handover not found")

    lead_id = result.data[0].get("lead_id")
    if lead_id:
        try:
            from app.services.notify import clear_pool_notifications_for_lead
            clear_pool_notifications_for_lead(tenant_id, lead_id, db=db)
        except Exception:
            pass
        remaining = (
            db.table("chat_handovers")
            .select("id", count="exact")
            .eq("lead_id", lead_id)
            .eq("status", "pending")
            .execute()
        )
        if not (remaining.count or 0):
            db.table("leads").update({
                "needs_human_attention": False,
                "escalation_reason": None,
                "ai_enabled": True,
            }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()

    return {"resolved": True}
