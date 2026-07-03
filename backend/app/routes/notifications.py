import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_owner
from app.dependencies.auth import get_current_user
from app.services.notification_config import (
    get_notification_config,
    save_notification_config,
    _NOTIFICATION_CONFIG_DEFAULT,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_AUDIENCE = {"telecallers_and_admin", "telecallers_only", "admin_only", "specific"}
_VALID_SEGMENTS = {"A", "B", "C", "D"}


class QuietHours(BaseModel):
    enabled: bool = False
    start_hour: int = Field(22, ge=0, le=23)
    end_hour: int = Field(8, ge=0, le=23)


class WhatsAppNotificationConfig(BaseModel):
    enabled: bool = False
    recipient_phones: list[str] = []
    template_id: str | None = None
    target_segments: list[str] = ["A"]

    @field_validator("recipient_phones")
    @classmethod
    def _validate_phones(cls, v: list[str]) -> list[str]:
        pattern = re.compile(r"^\+[1-9]\d{6,14}$")
        for phone in v:
            if not pattern.match(phone):
                raise ValueError(f"Invalid E.164 phone number: {phone}")
        return v

    @field_validator("target_segments")
    @classmethod
    def _validate_segments(cls, v: list[str]) -> list[str]:
        invalid = set(v) - _VALID_SEGMENTS
        if invalid:
            raise ValueError(f"Invalid segment(s): {sorted(invalid)}")
        return v


class NotificationConfigIn(BaseModel):
    push_enabled: bool = True
    events: dict[str, bool] = {}
    claimable_threshold_minutes: int = Field(15, ge=1, le=120)
    claimable_audience: str = "telecallers_and_admin"
    claimable_caller_ids: list[str] = []
    quiet_hours: QuietHours = QuietHours()
    whatsapp_notifications: WhatsAppNotificationConfig = WhatsAppNotificationConfig()

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


@router.get("/config")
async def get_config(ctx: dict = Depends(require_owner)):
    return get_notification_config(ctx["tenant_id"])


@router.put("/config")
async def update_config(payload: NotificationConfigIn, ctx: dict = Depends(require_owner)):
    if payload.claimable_audience not in _VALID_AUDIENCE:
        raise HTTPException(status_code=422, detail="Invalid claimable_audience")
    # Whitelist event keys to the known set; ignore unknown keys.
    allowed_events = set(_NOTIFICATION_CONFIG_DEFAULT["events"].keys())
    events = {k: bool(v) for k, v in payload.events.items() if k in allowed_events}
    # caller_ids only meaningful for the "specific" audience; store [] otherwise.
    caller_ids = (
        [str(c) for c in payload.claimable_caller_ids]
        if payload.claimable_audience == "specific" else []
    )
    config = {
        "push_enabled": payload.push_enabled,
        "events": {**_NOTIFICATION_CONFIG_DEFAULT["events"], **events},
        "claimable_threshold_minutes": payload.claimable_threshold_minutes,
        "claimable_audience": payload.claimable_audience,
        "claimable_caller_ids": caller_ids,
        "quiet_hours": payload.quiet_hours.model_dump(),
        "whatsapp_notifications": payload.whatsapp_notifications.model_dump(),
    }
    save_notification_config(ctx["tenant_id"], config)
    return config
