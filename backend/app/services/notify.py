import logging
import re

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def notify_user(
    tenant_id: str,
    user_id: str,
    type: str,
    title: str,
    message: str,
    *,
    db=None,
    dedupe_lead_id: str | None = None,
    push_url: str | None = None,
) -> None:
    """Insert a single notification for one user. Best-effort: never raises."""
    if not user_id:
        return
    db = db or get_supabase()
    try:
        if dedupe_lead_id:
            existing = (
                db.table("app_notifications")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("user_id", user_id)
                .eq("type", type)
                .eq("is_read", False)
                .limit(50)
                .execute()
            )
            if existing.data:
                return
        db.table("app_notifications").insert({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "type": type,
            "title": title,
            "message": message,
        }).execute()
        try:
            from app.services.web_push import send_user_push
            push_body = re.sub(r"\s*\[(lead_id|handover_id):.*?\]", "", message)
            send_user_push(
                tenant_id,
                user_id,
                title=title,
                body=push_body,
                url=push_url or "/dashboard",
                tag=f"{type}:{dedupe_lead_id}" if dedupe_lead_id else type,
                data={"type": type, "lead_id": dedupe_lead_id},
                db=db,
            )
        except Exception as push_err:
            logger.warning("notify_user push failed (type=%s user=%s): %s", type, user_id, push_err)
    except Exception as e:
        logger.warning(f"notify_user failed (type={type} user={user_id}): {e}")


def notify_assigned_caller_of_reply(lead_id: str, tenant_id: str, *, db=None) -> None:
    """Notify the caller who owns this lead that the lead replied. Best-effort."""
    if not lead_id:
        return
    db = db or get_supabase()
    try:
        lead = (
            db.table("leads")
            .select("assigned_to,name")
            .eq("id", lead_id)
            .maybe_single()
            .execute()
        )
        data = lead.data if lead else None
        if not data or not data.get("assigned_to"):
            return
        caller = (
            db.table("callers")
            .select("user_id")
            .eq("id", data["assigned_to"])
            .eq("tenant_id", tenant_id)
            .maybe_single()
            .execute()
        )
        user_id = (caller.data or {}).get("user_id") if caller else None
        if not user_id:
            return
        notify_user(
            tenant_id,
            user_id,
            "lead_replied",
            "Lead replied",
            f"'{data.get('name') or 'Your lead'}' just replied.",
            db=db,
            dedupe_lead_id=lead_id,
            push_url=f"/dashboard/conversations?lead_id={lead_id}",
        )
    except Exception as e:
        logger.warning(f"notify_assigned_caller_of_reply failed (lead={lead_id}): {e}")


def _active_caller_user_ids(db, tenant_id: str) -> list[str]:
    callers = (
        db.table("callers")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("active", True)
        .eq("status", "active")
        .execute()
    )
    return [c["user_id"] for c in (callers.data or []) if c.get("user_id")]


def _owner_user_id(db, tenant_id: str) -> str | None:
    owner = (
        db.table("tenant_users")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("role", "owner")
        .limit(1)
        .execute()
    )
    return (owner.data[0] if owner.data else {}).get("user_id")


def notify_pool(
    tenant_id: str,
    type: str,
    title: str,
    message: str,
    *,
    db=None,
    segments: list | None = None,
    exclude_user_ids: list[str] | None = None,
) -> None:
    """Fan out one notification per active caller + owner. Best-effort: never raises.

    `segments` is accepted for future per-segment routing; the callers table has
    no segment column today, so it does not filter recipients yet.
    """
    db = db or get_supabase()
    exclude = set(exclude_user_ids or [])
    try:
        recipients = set(_active_caller_user_ids(db, tenant_id))
        owner = _owner_user_id(db, tenant_id)
        if owner:
            recipients.add(owner)
        for uid in recipients:
            if uid in exclude:
                continue
            db.table("app_notifications").insert({
                "tenant_id": tenant_id,
                "user_id": uid,
                "type": type,
                "title": title,
                "message": message,
            }).execute()
    except Exception as e:
        logger.warning(f"notify_pool failed (type={type}): {e}")


def clear_pool_notifications_for_lead(tenant_id: str, lead_id: str, *, db=None) -> None:
    """Mark handover/pool notifications for a lead as read for all users when claimed/resolved."""
    db = db or get_supabase()
    try:
        db.table("app_notifications").update({"is_read": True}).eq("tenant_id", tenant_id).in_("type", ["handover_new", "callback_claimable"]).like("message", f"%{lead_id}%").execute()
    except Exception as e:
        logger.warning(f"clear_pool_notifications_for_lead failed for lead {lead_id}: {e}")

