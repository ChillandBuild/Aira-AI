import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id
from app.dependencies.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/")
async def list_notifications(
    tenant_id: str = Depends(get_tenant_id),
    user: dict = Depends(get_current_user)
):
    """Fetch unread notifications for the current user."""
    db = get_supabase()

    rows = (
        db.table("app_notifications")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("user_id", user["user_id"])
        .eq("is_read", False)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    
    return {"data": rows.data or []}

@router.patch("/read")
async def mark_all_notifications_read(
    tenant_id: str = Depends(get_tenant_id),
    user: dict = Depends(get_current_user)
):
    """Mark all unread notifications as read for the current user."""
    db = get_supabase()
    db.table("app_notifications").update({"is_read": True}).eq("tenant_id", tenant_id).eq("user_id", user["user_id"]).eq("is_read", False).execute()
    return {"success": True}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    tenant_id: str = Depends(get_tenant_id),
    user: dict = Depends(get_current_user)
):
    """Mark a specific notification as read."""
    db = get_supabase()

    row = (
        db.table("app_notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("tenant_id", tenant_id)
        .eq("user_id", user["user_id"])
        .execute()
    )
    
    return {"success": True, "data": row.data[0] if row.data else None}

@router.get("/pool")
async def list_pool_items(
    tenant_id: str = Depends(get_tenant_id),
):
    """Currently-actionable shared-pool items for the claim banner.

    Reflects live state (not stale notifications): pending unassigned handovers.
    Returns at most 20.
    """
    db = get_supabase()
    items: list[dict] = []
    try:
        handovers = (
            db.table("chat_handovers")
            .select("id, lead_id, reason, opened_at, leads(name)")
            .eq("tenant_id", tenant_id)
            .eq("status", "pending")
            .is_("assigned_to", "null")
            .order("opened_at", desc=True)
            .limit(20)
            .execute()
        )
        for h in (handovers.data or []):
            lead = h.get("leads") or {}
            items.append({
                "kind": "handover",
                "id": h["id"],
                "lead_id": h["lead_id"],
                "lead_name": lead.get("name") if isinstance(lead, dict) else None,
                "reason": h.get("reason"),
                "created_at": h.get("opened_at"),
            })
    except Exception as e:
        logger.warning(f"pool handovers fetch failed (transient?): {e}")

    return {"data": items}
