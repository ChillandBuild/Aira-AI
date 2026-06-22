import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.db.supabase import get_supabase
from app.dependencies.auth import get_current_user
from app.dependencies.system_admin import get_system_admin
from app.services.audit_log import record_audit_event

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me")
def operator_me(user: dict = Depends(get_current_user)):
    """Verify the caller is a system admin. No tenant required."""
    db = get_supabase()
    result = (
        db.table("system_admins")
        .select("user_id")
        .eq("user_id", user["user_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=403, detail="Access denied.")
    return {"is_system_admin": True, "user_id": user["user_id"]}

ServiceTier = Literal[
    "whatsapp_only", "telecalling_only", "combined",
    "whatsapp_instagram", "whatsapp_facebook", "whatsapp_telegram",
    "omnichannel", "omnichannel_telecalling",
]

_FEATURE_MAP: dict[str, list[str]] = {
    "whatsapp_only":         ["whatsapp"],
    "telecalling_only":      ["telecalling"],
    "combined":              ["whatsapp", "telecalling"],
    "whatsapp_instagram":    ["whatsapp", "instagram"],
    "whatsapp_facebook":     ["whatsapp", "facebook"],
    "whatsapp_telegram":     ["whatsapp", "telegram"],
    "omnichannel":           ["whatsapp", "instagram", "facebook", "telegram"],
    "omnichannel_telecalling": ["whatsapp", "instagram", "facebook", "telegram", "telecalling"],
}

_SETTING_KEYS: list[tuple[str, bool]] = [
    ("meta_phone_number_id", False), ("meta_access_token", True),
    ("meta_waba_id", False), ("meta_webhook_verify_token", True),
    ("meta_app_secret", True),
    ("telecmi_user_id", False), ("telecmi_secret", True),
    ("telecmi_callerid", False), ("telecmi_recording_base_url", False),
    ("groq_api_key", True),
    ("telegram_bot_token", True),
    ("instagram_page_id", False), ("instagram_access_token", True),
    ("facebook_page_id", False), ("facebook_access_token", True),
    ("ai_auto_reply_enabled", False),
    ("reengagement_enabled", False),
]


class CreateClientPayload(BaseModel):
    company_name: str
    email: EmailStr
    password: str
    service: ServiceTier = "combined"


class UpdateFeaturesPayload(BaseModel):
    service: ServiceTier | None = None
    features: list[str] | None = None


class UpdateStatusPayload(BaseModel):
    status: Literal["active", "suspended"]


@router.get("/clients")
def list_clients(_admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenants = (
        db.table("tenants")
        .select("id, name, enabled_features, status, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    tenant_ids = [t["id"] for t in (tenants.data or [])]
    owners_map: dict[str, str] = {}
    if tenant_ids:
        owners_rows = (
            db.table("tenant_users")
            .select("tenant_id, user_id")
            .in_("tenant_id", tenant_ids)
            .eq("role", "owner")
            .execute()
        )
        owners_map = {r["tenant_id"]: r["user_id"] for r in (owners_rows.data or [])}
    result = [{**t, "owner_user_id": owners_map.get(t["id"])} for t in (tenants.data or [])]
    return {"data": result}


@router.post("/clients", status_code=201)
async def create_client(payload: CreateClientPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    features = _FEATURE_MAP[payload.service]
    tc_subs = ["telecalling.dialer", "telecalling.scheduled", "telecalling.notes"]
    if "telecalling" in features:
        features = features + tc_subs
    has_channel = any(ch in features for ch in ("whatsapp", "instagram", "facebook", "telegram"))
    if has_channel:
        features = features + ["inbound_leads", "outbound_leads"]
    features = features + ["analytics"]

    try:
        result = db.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
        })
        user = result.user
        new_user_id = user.id if hasattr(user, "id") else user["id"]
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(status_code=400, detail="A user with this email already exists")
        raise HTTPException(status_code=400, detail=f"Failed to create user: {msg}")

    try:
        tenant_result = db.table("tenants").insert({
            "name": payload.company_name,
            "enabled_features": features,
            "status": "active",
        }).execute()
        tenant_id = tenant_result.data[0]["id"]

        db.table("app_settings").insert([
            {"tenant_id": tenant_id, "key": k, "value": None, "is_secret": s}
            for k, s in _SETTING_KEYS
        ]).execute()

        db.table("tenant_users").insert({
            "tenant_id": tenant_id,
            "user_id": new_user_id,
            "role": "owner",
        }).execute()

        db.table("callers").insert({
            "tenant_id": tenant_id,
            "user_id": new_user_id,
            "name": "Admin",
            "active": True,
            "overall_score": 7.0,
        }).execute()
    except Exception as e:
        logger.error(f"Tenant setup failed for new user {new_user_id}, cleaning up: {e}")
        try:
            db.auth.admin.delete_user(new_user_id)
        except Exception as cleanup_err:
            logger.error(f"Failed to delete orphaned auth user {new_user_id}: {cleanup_err}")
        raise HTTPException(status_code=500, detail="Client setup failed; user account cleaned up.")

    logger.info(f"Operator created client: {payload.company_name} ({tenant_id}), service={payload.service}")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.client_created",
        target_type="tenant",
        target_id=tenant_id,
        metadata={
            "company_name": payload.company_name,
            "email": payload.email,
            "service": payload.service,
            "enabled_features": features,
        },
    )
    return {
        "tenant_id": tenant_id,
        "company_name": payload.company_name,
        "email": payload.email,
        "service": payload.service,
        "enabled_features": features,
    }


@router.patch("/clients/{tenant_id}/features")
def update_features(tenant_id: str, payload: UpdateFeaturesPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    valid_features = {
        "whatsapp", "telecalling", "instagram", "facebook", "telegram",
        "telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes",
        "analytics", "inbound_leads", "outbound_leads",
    }

    if payload.features is not None:
        invalid = set(payload.features) - valid_features
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid features: {', '.join(invalid)}")
        features = list(payload.features)
        tc_subs = {"telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes"}
        tc_default_subs = ["telecalling.dialer", "telecalling.scheduled", "telecalling.notes"]
        if "telecalling" in features and not (set(features) & tc_subs):
            features.extend(tc_default_subs)
        if "telecalling" not in features:
            features = [f for f in features if f not in tc_subs]
    elif payload.service is not None:
        features = _FEATURE_MAP[payload.service]
    else:
        raise HTTPException(status_code=400, detail="Provide 'features' or 'service'")

    result = db.table("tenants").update({"enabled_features": features}).eq("id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.features_updated",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"features": features, "service": payload.service},
    )
    return {"tenant_id": tenant_id, "enabled_features": features}


@router.patch("/clients/{tenant_id}/status")
def update_status(tenant_id: str, payload: UpdateStatusPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    current = db.table("tenants").select("status").eq("id", tenant_id).maybe_single().execute()
    result = db.table("tenants").update({"status": payload.status}).eq("id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.status_updated",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"old_status": (current.data or {}).get("status"), "new_status": payload.status},
    )
    return {"tenant_id": tenant_id, "status": payload.status}


@router.post("/clients/{tenant_id}/wipe-leads")
def wipe_leads(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    """Delete all leads and lead-related data for a tenant. Irreversible."""
    db = get_supabase()
    tenant = db.table("tenants").select("id,name").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Clear dependent tables first (tenant-scoped) to avoid FK violations
    for table in (
        "messages", "lead_notes", "chat_handovers",
        "follow_up_jobs",
        # Broadcast history — fully wiped per operator request
        "broadcast_recipients", "broadcast_lead_scores",
        "broadcast_failed_contacts", "broadcast_tags", "scheduled_broadcasts",
    ):
        try:
            db.table(table).delete().eq("tenant_id", tenant_id).execute()
        except Exception as e:
            logger.warning("wipe-leads: could not clear %s for tenant %s: %s", table, tenant_id, e)

    # Broadcast history is stored as a JSON blob in app_settings — clear it too
    try:
        db.table("app_settings") \
            .delete() \
            .eq("tenant_id", tenant_id) \
            .eq("key", "broadcast_history") \
            .execute()
    except Exception as e:
        logger.warning("wipe-leads: could not clear broadcast_history for tenant %s: %s", tenant_id, e)

    result = db.table("leads").delete().eq("tenant_id", tenant_id).execute()
    deleted = len(result.data or [])
    logger.warning("OPERATOR WIPE: %d leads deleted for tenant %s (%s)", deleted, tenant_id, tenant.data["name"])
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.leads_wiped",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"tenant_name": tenant.data["name"], "deleted_leads": deleted},
    )
    return {"deleted": deleted, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/reset-password")
async def reset_password(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    owner = (
        db.table("tenant_users")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("role", "owner")
        .maybe_single()
        .execute()
    )
    if not owner.data:
        raise HTTPException(status_code=404, detail="No owner found for this tenant")
    temp_pw = "Aira@" + secrets.token_urlsafe(10)
    db.auth.admin.update_user_by_id(owner.data["user_id"], {"password": temp_pw})
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.password_reset",
        target_type="tenant_owner",
        target_id=owner.data["user_id"],
        metadata={"tenant_id": tenant_id},
    )
    return {"temp_password": temp_pw}


@router.get("/clients/{tenant_id}/overview")
def client_overview(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()

    tenant = db.table("tenants").select("id, name, status, enabled_features, created_at, plan").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    owner_row = (
        db.table("tenant_users")
        .select("user_id, created_at")
        .eq("tenant_id", tenant_id)
        .eq("role", "owner")
        .maybe_single()
        .execute()
    )
    owner_info: dict = {"user_id": None, "email": None, "created_at": None}
    if owner_row.data:
        owner_info["user_id"] = owner_row.data["user_id"]
        owner_info["created_at"] = owner_row.data["created_at"]
        try:
            user = db.auth.admin.get_user_by_id(owner_row.data["user_id"])
            owner_info["email"] = user.user.email if hasattr(user, "user") else None
        except Exception:
            pass

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_leads = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").execute()
    active_leads = (
        db.table("leads").select("id", count="exact")
        .eq("tenant_id", tenant_id).is_("deleted_at", "null")
        .in_("segment", ["A", "B"])
        .execute()
    )
    msgs_sent = (
        db.table("messages").select("id", count="exact")
        .eq("tenant_id", tenant_id).eq("direction", "outbound")
        .gte("created_at", thirty_days_ago)
        .execute()
    )
    msgs_recv = (
        db.table("messages").select("id", count="exact")
        .eq("tenant_id", tenant_id).eq("direction", "inbound")
        .gte("created_at", thirty_days_ago)
        .execute()
    )
    team_count = db.table("callers").select("id", count="exact").eq("tenant_id", tenant_id).execute()

    last_msg = (
        db.table("messages").select("created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True).limit(1).execute()
    )
    last_call = (
        db.table("call_logs").select("created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True).limit(1).execute()
    )
    last_msg_ts = (last_msg.data or [{}])[0].get("created_at")
    last_call_ts = (last_call.data or [{}])[0].get("created_at")
    last_activity = max(filter(None, [last_msg_ts, last_call_ts]), default=None)

    return {
        "tenant": tenant.data,
        "owner": owner_info,
        "stats": {
            "total_leads": total_leads.count or 0,
            "active_leads": active_leads.count or 0,
            "messages_sent_30d": msgs_sent.count or 0,
            "messages_received_30d": msgs_recv.count or 0,
            "team_members": team_count.count or 0,
            "last_activity": last_activity,
        },
    }


@router.get("/clients/{tenant_id}/config")
def client_config(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    settings_rows = (
        db.table("app_settings")
        .select("key, value")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    settings_map = {r["key"]: r["value"] for r in (settings_rows.data or [])}

    def cred_status(keys: list[str]) -> str:
        vals = [settings_map.get(k) for k in keys]
        non_null = [v for v in vals if v is not None and v != ""]
        if len(non_null) == len(keys):
            return "configured"
        if len(non_null) > 0:
            return "incomplete"
        return "not_configured"

    return {
        "enabled_features": tenant.data["enabled_features"],
        "credentials_status": {
            "whatsapp": cred_status(["meta_phone_number_id", "meta_access_token", "meta_waba_id", "meta_webhook_verify_token"]),
            "telecalling": cred_status(["telecmi_user_id", "telecmi_secret", "telecmi_callerid"]),
            "ai": cred_status(["groq_api_key"]),
            "payments": cred_status(["razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret"]),
        },
        "settings": {
            "ai_auto_reply_enabled": settings_map.get("ai_auto_reply_enabled") == "true",
            "reengagement_enabled": settings_map.get("reengagement_enabled") == "true",
        },
    }


@router.get("/clients/{tenant_id}/health")
def client_health(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()

    tenant = db.table("tenants").select("id, enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    channel_sources = {"whatsapp": "whatsapp", "instagram": "instagram", "facebook": "facebook", "telegram": "telegram"}
    channels: dict = {}
    for channel, source in channel_sources.items():
        last_inbound = (
            db.table("messages").select("created_at")
            .eq("tenant_id", tenant_id).eq("direction", "inbound").eq("channel", source)
            .order("created_at", desc=True).limit(1).execute()
        )
        last_ts = (last_inbound.data or [{}])[0].get("created_at")
        is_enabled = channel in (tenant.data.get("enabled_features") or [])
        channels[channel] = {
            "status": "healthy" if is_enabled and last_ts else ("not_configured" if not is_enabled else "unhealthy"),
            "last_inbound": last_ts,
        }

    token_incidents = (
        db.table("incidents").select("id")
        .eq("tenant_id", tenant_id).eq("type", "token_invalid")
        .order("created_at", desc=True).limit(1).execute()
    )
    settings_rows = db.table("app_settings").select("key, value").eq("tenant_id", tenant_id).in_("key", ["meta_access_token"]).execute()
    has_token = any(r["value"] for r in (settings_rows.data or []))
    token_status = "not_set"
    if has_token:
        token_status = "expired" if token_incidents.data else "valid"

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    sent_7d = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).eq("direction", "outbound").gte("created_at", seven_days_ago).execute()
    delivered_7d = (
        db.table("messages").select("id", count="exact")
        .eq("tenant_id", tenant_id).eq("direction", "outbound")
        .eq("delivery_status", "delivered")
        .gte("created_at", seven_days_ago).execute()
    )
    failed_7d = (
        db.table("messages").select("id", count="exact")
        .eq("tenant_id", tenant_id).eq("direction", "outbound")
        .eq("delivery_status", "failed")
        .gte("created_at", seven_days_ago).execute()
    )
    sent_count = sent_7d.count or 0
    delivered_count = delivered_7d.count or 0
    failed_count = failed_7d.count or 0
    success_rate = round((delivered_count / sent_count) * 100, 1) if sent_count > 0 else 0

    recent_errors = (
        db.table("messages").select("id, delivery_error_title, created_at")
        .eq("tenant_id", tenant_id).eq("delivery_status", "failed")
        .order("created_at", desc=True).limit(10).execute()
    )
    open_incidents = (
        db.table("incidents").select("id, type, detail, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True).limit(10).execute()
    )

    return {
        "channels": channels,
        "token_status": token_status,
        "delivery_7d": {
            "sent": sent_count,
            "delivered": delivered_count,
            "failed": failed_count,
            "success_rate": success_rate,
        },
        "recent_errors": [
            {"message_id": r["id"], "error": r.get("delivery_error_title"), "created_at": r["created_at"]}
            for r in (recent_errors.data or [])
        ],
        "open_incidents": [
            {
                "id": inc["id"],
                "type": inc.get("type", ""),
                "severity": (inc.get("detail") or {}).get("severity", "info"),
                "message": (inc.get("detail") or {}).get("message", inc.get("type", "")),
                "created_at": inc["created_at"],
            }
            for inc in (open_incidents.data or [])
        ],
    }


@router.get("/clients/{tenant_id}/team")
def client_team(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()

    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    owner_row = (
        db.table("tenant_users")
        .select("user_id, created_at")
        .eq("tenant_id", tenant_id)
        .eq("role", "owner")
        .maybe_single()
        .execute()
    )
    owner_info: dict = {"user_id": None, "email": None, "created_at": None}
    if owner_row.data:
        owner_info["user_id"] = owner_row.data["user_id"]
        owner_info["created_at"] = owner_row.data["created_at"]
        try:
            user = db.auth.admin.get_user_by_id(owner_row.data["user_id"])
            owner_info["email"] = user.user.email if hasattr(user, "user") else None
        except Exception:
            pass

    callers_rows = (
        db.table("callers")
        .select("id, name, active, overall_score, shift_start_hour, shift_end_hour, user_id")
        .eq("tenant_id", tenant_id)
        .order("name")
        .execute()
    )

    tenant_users = (
        db.table("tenant_users")
        .select("user_id, role")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    role_map = {r["user_id"]: r["role"] for r in (tenant_users.data or [])}

    callers = []
    for c in (callers_rows.data or []):
        callers.append({
            "id": c["id"],
            "name": c["name"],
            "active": c["active"],
            "overall_score": c["overall_score"],
            "shift_start_hour": c.get("shift_start_hour"),
            "shift_end_hour": c.get("shift_end_hour"),
            "role": role_map.get(c.get("user_id"), "caller"),
        })

    return {"owner": owner_info, "callers": callers}


@router.delete("/clients/{tenant_id}/team/{caller_id}")
def delete_team_member(tenant_id: str, caller_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    caller = (
        db.table("callers")
        .select("id, name, user_id")
        .eq("id", caller_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not caller.data:
        raise HTTPException(status_code=404, detail="Team member not found")

    db.table("callers").delete().eq("id", caller_id).eq("tenant_id", tenant_id).execute()

    if caller.data.get("user_id"):
        db.table("tenant_users").delete().eq("user_id", caller.data["user_id"]).eq("tenant_id", tenant_id).eq("role", "caller").execute()

    return {"deleted": True, "name": caller.data["name"]}


@router.get("/clients/{tenant_id}/dashboard/inbox")
def client_dashboard_inbox(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    handovers = db.table("chat_handovers").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "pending").execute()

    convos = (
        db.table("conversations")
        .select("id, lead_id, channel, opened_at")
        .eq("tenant_id", tenant_id)
        .order("opened_at", desc=True)
        .limit(20)
        .execute()
    )

    lead_ids = [c["lead_id"] for c in (convos.data or []) if c.get("lead_id")]
    leads_map: dict = {}
    last_msg_map: dict = {}
    if lead_ids:
        leads = db.table("leads").select("id, name, phone").in_("id", lead_ids).execute()
        leads_map = {l["id"]: l for l in (leads.data or [])}
        msgs = (
            db.table("messages")
            .select("lead_id, content, created_at")
            .in_("lead_id", lead_ids)
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .execute()
        )
        for m in (msgs.data or []):
            lid = m.get("lead_id")
            if lid and lid not in last_msg_map:
                last_msg_map[lid] = m

    conversations = []
    for c in (convos.data or []):
        lead = leads_map.get(c.get("lead_id"), {})
        msg = last_msg_map.get(c.get("lead_id"), {})
        conversations.append({
            "id": c["id"],
            "lead_name": lead.get("name", "Unknown"),
            "lead_phone": lead.get("phone"),
            "last_message": (msg.get("content") or "")[:80],
            "channel": c.get("channel", "whatsapp"),
            "last_message_at": msg.get("created_at") or c.get("opened_at"),
        })

    return {"handover_count": handovers.count or 0, "conversations": conversations}


@router.get("/clients/{tenant_id}/dashboard/leads")
def client_dashboard_leads(tenant_id: str, direction: str = "all", _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    base = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null")
    total = base.execute()
    seg_a = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "A").execute()
    seg_b = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "B").execute()
    seg_c = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "C").execute()
    seg_d = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "D").execute()

    q = db.table("leads").select("id, name, phone, segment, score, source, created_at, opt_in_source").eq("tenant_id", tenant_id).is_("deleted_at", "null")
    if direction == "inbound":
        q = q.in_("opt_in_source", ["organic", "meta_ads", "instagram", "facebook", "telegram"])
    elif direction == "outbound":
        q = q.eq("opt_in_source", "csv")
    recent = q.order("created_at", desc=True).limit(20).execute()

    return {
        "total": total.count or 0,
        "segments": {"A": seg_a.count or 0, "B": seg_b.count or 0, "C": seg_c.count or 0, "D": seg_d.count or 0},
        "recent": recent.data or [],
    }


@router.get("/clients/{tenant_id}/dashboard/templates")
def client_dashboard_templates(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    templates = (
        db.table("message_templates")
        .select("id, name, status, category, language, submitted_at")
        .eq("tenant_id", tenant_id)
        .order("submitted_at", desc=True)
        .execute()
    )
    raw = templates.data or []
    approved = sum(1 for t in raw if t.get("status") == "APPROVED")
    pending = sum(1 for t in raw if t.get("status") == "PENDING")
    data = [
        {**t, "updated_at": t.pop("submitted_at", None)}
        for t in raw
    ]

    return {"total": len(data), "approved": approved, "pending": pending, "templates": data}


@router.get("/clients/{tenant_id}/dashboard/numbers")
def client_dashboard_numbers(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    numbers = (
        db.table("phone_numbers")
        .select("id, number, display_name, quality_rating, status, messaging_tier")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    raw = numbers.data or []
    active = sum(1 for n in raw if n.get("status") == "active")
    data = [
        {
            "phone_number": n.get("number"),
            "display_name": n.get("display_name"),
            "quality_rating": (n.get("quality_rating") or "").upper() or None,
            "status": n.get("status"),
            "messaging_limit_tier": str(n.get("messaging_tier")) if n.get("messaging_tier") else None,
        }
        for n in raw
    ]

    return {"total": len(data), "active": active, "numbers": data}


@router.get("/clients/{tenant_id}/dashboard/knowledge")
def client_dashboard_knowledge(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    docs = (
        db.table("knowledge_documents")
        .select("id, name, file_type, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    total_chunks = db.table("knowledge_chunks").select("id", count="exact").eq("tenant_id", tenant_id).execute()

    doc_data = []
    for d in (docs.data or []):
        chunk_count = db.table("knowledge_chunks").select("id", count="exact").eq("document_id", d["id"]).execute()
        doc_data.append({"id": d["id"], "title": d.get("name", ""), "file_type": d.get("file_type", ""), "created_at": d.get("created_at"), "chunk_count": chunk_count.count or 0})

    return {"total_docs": len(docs.data or []), "total_chunks": total_chunks.count or 0, "documents": doc_data}


@router.get("/clients/{tenant_id}/dashboard/analytics")
def client_dashboard_analytics(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    tenant = db.table("tenants").select("id, enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_msgs = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", thirty_days_ago).execute()
    delivered = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).eq("direction", "outbound").eq("delivery_status", "delivered").gte("created_at", thirty_days_ago).execute()
    sent = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).eq("direction", "outbound").gte("created_at", thirty_days_ago).execute()
    avg_score_rows = db.table("leads").select("score").eq("tenant_id", tenant_id).is_("deleted_at", "null").not_.is_("score", "null").execute()

    sent_count = sent.count or 0
    delivered_count = delivered.count or 0
    delivery_rate = round((delivered_count / sent_count) * 100, 1) if sent_count > 0 else 0
    scores = [r["score"] for r in (avg_score_rows.data or []) if r.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    result: dict = {
        "messages_30d": total_msgs.count or 0,
        "delivery_rate": delivery_rate,
        "avg_score": avg_score,
    }

    if "telecalling" in (tenant.data.get("enabled_features") or []):
        calls = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", thirty_days_ago).execute()
        connected = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).eq("disposition", "answered").gte("created_at", thirty_days_ago).execute()
        call_count = calls.count or 0
        connect_count = connected.count or 0
        result["total_calls"] = call_count
        result["connect_rate"] = round((connect_count / call_count) * 100, 1) if call_count > 0 else 0

    return result


@router.get("/clients/{tenant_id}/dashboard/telecalling")
def client_dashboard_telecalling(tenant_id: str, section: str = "dialer", _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if section == "upload":
        raw_batches = (
            db.table("telecalling_upload_batches")
            .select("id, file_name, total_contacts, inserted, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        total = db.table("telecalling_upload_batches").select("id", count="exact").eq("tenant_id", tenant_id).execute()
        batches = [
            {
                "id": b["id"],
                "file_name": b.get("file_name"),
                "lead_count": b.get("total_contacts", 0),
                "created_at": b.get("created_at"),
                "status": "completed" if b.get("inserted") is not None else "processing",
            }
            for b in (raw_batches.data or [])
        ]
        return {"total_batches": total.count or 0, "batches": batches}

    elif section == "dialer":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        calls_today = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", today).execute()
        connected_today = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).eq("disposition", "answered").gte("created_at", today).execute()
        recent_calls = (
            db.table("call_logs")
            .select("id, lead_id, caller_id, duration_seconds, disposition, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        call_count = calls_today.count or 0
        connect_count = connected_today.count or 0
        return {
            "calls_today": call_count,
            "connect_rate": round((connect_count / call_count) * 100, 1) if call_count > 0 else 0,
            "recent_calls": recent_calls.data or [],
        }

    elif section == "scheduled":
        pending = (
            db.table("follow_up_jobs")
            .select("id, lead_id, scheduled_for, cadence, created_at")
            .eq("tenant_id", tenant_id)
            .eq("status", "pending")
            .order("scheduled_for")
            .limit(20)
            .execute()
        )
        total = db.table("follow_up_jobs").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "pending").execute()
        return {"pending_count": total.count or 0, "scheduled": pending.data or []}

    elif section == "notes":
        raw_notes = (
            db.table("lead_notes")
            .select("id, lead_id, caller_id, content, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        total = db.table("lead_notes").select("id", count="exact").eq("tenant_id", tenant_id).execute()
        caller_ids = list({n["caller_id"] for n in (raw_notes.data or []) if n.get("caller_id")})
        callers_map: dict = {}
        if caller_ids:
            callers = db.table("callers").select("id, name").in_("id", caller_ids).execute()
            callers_map = {c["id"]: c.get("name") for c in (callers.data or [])}
        notes = [
            {
                "id": n["id"],
                "lead_id": n.get("lead_id"),
                "author_name": callers_map.get(n.get("caller_id")) if n.get("caller_id") else None,
                "note": n.get("content", ""),
                "created_at": n.get("created_at"),
            }
            for n in (raw_notes.data or [])
        ]
        return {"total_notes": total.count or 0, "notes": notes}

    raise HTTPException(status_code=400, detail="Invalid section. Use: upload, dialer, scheduled, notes")


_CLEAR_TABLES: dict[str, list[str]] = {
    "broadcasts": ["broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts", "scheduled_broadcasts"],
    "messages": ["messages"],
    "call_logs": ["call_logs"],
    "leads": [],
    "knowledge": ["knowledge_chunks", "knowledge_documents"],
    "analytics": ["whatsapp_insights_snapshots"],
    "tags": ["lead_tag_opt_outs", "broadcast_tags"],
    "telecalling_uploads": ["telecalling_upload_batches"],
}


@router.get("/clients/{tenant_id}/clear/{data_type}/count")
def clear_count(tenant_id: str, data_type: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    if data_type not in _CLEAR_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid data type: {data_type}")
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data_type == "leads":
        count = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").execute()
        return {"count": count.count or 0, "detail": {"leads": count.count or 0}}

    detail: dict = {}
    total = 0
    for table in _CLEAR_TABLES[data_type]:
        c = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id).execute()
        detail[table] = c.count or 0
        total += c.count or 0
    return {"count": total, "detail": detail}


@router.post("/clients/{tenant_id}/clear/{data_type}")
def clear_data(tenant_id: str, data_type: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    if data_type not in _CLEAR_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid data type: {data_type}")
    tenant = db.table("tenants").select("id, name").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data_type == "leads":
        for table in ("messages", "lead_notes", "chat_handovers", "follow_up_jobs",
                       "broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts",
                       "broadcast_tags", "scheduled_broadcasts"):
            try:
                db.table(table).delete().eq("tenant_id", tenant_id).execute()
            except Exception as e:
                logger.warning("clear leads: could not clear %s: %s", table, e)
        result = db.table("leads").delete().eq("tenant_id", tenant_id).execute()
        deleted = len(result.data or [])
    else:
        deleted = 0
        tables = _CLEAR_TABLES[data_type]
        for table in tables:
            try:
                result = db.table(table).delete().eq("tenant_id", tenant_id).execute()
                deleted += len(result.data or [])
            except Exception as e:
                logger.warning("clear %s: could not clear %s: %s", data_type, table, e)

    logger.warning("OPERATOR CLEAR %s: %d records deleted for tenant %s", data_type, deleted, tenant_id)
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action=f"operator.data_cleared:{data_type}",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"data_type": data_type, "deleted_count": deleted, "tenant_name": tenant.data["name"]},
    )
    return {"deleted_count": deleted, "data_type": data_type}


@router.get("/scheduler-health")
def scheduler_health(_admin: dict = Depends(get_system_admin)):
    """System-wide APScheduler health: each global job's next run, last run
    status/lag, recent error count, plus recent failures. Operator-only —
    the jobs are platform-level (not per tenant)."""
    from datetime import datetime, timezone, timedelta
    from app.main import _scheduler

    db = get_supabase()
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    jobs_out = []
    for job in _scheduler.get_jobs():
        last = (
            db.table("scheduler_runs")
            .select("status, ran_at, lateness_ms, error")
            .eq("job_id", job.id)
            .order("ran_at", desc=True)
            .limit(1)
            .execute()
        )
        last_row = (last.data or [None])[0]
        errs = (
            db.table("scheduler_runs")
            .select("id", count="exact")
            .eq("job_id", job.id)
            .eq("status", "error")
            .gte("ran_at", day_ago)
            .execute()
        )
        jobs_out.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "paused": job.next_run_time is None,
            "last_status": last_row["status"] if last_row else None,
            "last_run": last_row["ran_at"] if last_row else None,
            "last_lateness_ms": last_row["lateness_ms"] if last_row else None,
            "last_error": last_row["error"] if last_row else None,
            "errors_24h": errs.count or 0,
        })

    recent_failures = (
        db.table("scheduler_runs")
        .select("job_id, status, ran_at, error")
        .in_("status", ["error", "missed"])
        .order("ran_at", desc=True)
        .limit(20)
        .execute()
    )
    return {
        "jobs": jobs_out,
        "recent_failures": recent_failures.data or [],
        "server_time": now.isoformat(),
    }


@router.post("/scheduler/{job_id}/toggle")
def toggle_scheduler_job(job_id: str, _admin: dict = Depends(get_system_admin)):
    """Pause a running job or resume a paused one. Operator-only."""
    from app.main import _scheduler

    job = _scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.next_run_time is None:
        _scheduler.resume_job(job_id)
        job = _scheduler.get_job(job_id)
        return {"id": job_id, "paused": False, "next_run": job.next_run_time.isoformat() if job.next_run_time else None}
    else:
        _scheduler.pause_job(job_id)
        return {"id": job_id, "paused": True, "next_run": None}


@router.get("/system-health")
def system_health(_admin: dict = Depends(get_system_admin)):
    """Platform-level health: uptime, memory, Python version, last keep-alive ping."""
    import psutil, platform
    from datetime import datetime, timezone
    from app.main import _startup_time

    now = datetime.now(timezone.utc)
    uptime_seconds = (now - _startup_time).total_seconds()
    process = psutil.Process()
    mem = process.memory_info()

    return {
        "status": "healthy",
        "uptime_seconds": int(uptime_seconds),
        "uptime_human": _format_uptime(uptime_seconds),
        "memory_mb": round(mem.rss / (1024 * 1024), 1),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "python_version": platform.python_version(),
        "server_time": now.isoformat(),
        "started_at": _startup_time.isoformat(),
    }


def _format_uptime(seconds: float) -> str:
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@router.get("/audit-logs")
def list_audit_logs(
    page: int = 1,
    limit: int = 50,
    tenant_id: str | None = None,
    action: str | None = None,
    _admin: dict = Depends(get_system_admin),
):
    db = get_supabase()
    q = db.table("app_audit_logs").select(
        "id, tenant_id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at",
        count="exact",
    )
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    if action:
        q = q.ilike("action", f"%{action}%")
    offset = (page - 1) * limit
    result = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    tenant_ids = list({r["tenant_id"] for r in (result.data or []) if r.get("tenant_id")})
    tenant_names: dict[str, str] = {}
    if tenant_ids:
        tenants = db.table("tenants").select("id, name").in_("id", tenant_ids).execute()
        tenant_names = {t["id"]: t["name"] for t in (tenants.data or [])}

    logs = []
    for r in (result.data or []):
        logs.append({
            **r,
            "tenant_name": tenant_names.get(r.get("tenant_id", ""), "—"),
        })

    return {"data": logs, "total": result.count or 0, "page": page, "limit": limit}


_ALL_TENANT_TABLES = [
    "messages", "lead_notes", "chat_handovers", "follow_up_jobs",
    "broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts",
    "broadcast_tags", "scheduled_broadcasts", "lead_stage_events", "lead_tag_opt_outs",
    "lead_tag_interest", "lead_conversation_state", "automation_flow_runs",
    "automation_logs", "automation_pending_executions", "automation_steps", "automations",
    "bot_flows", "call_logs", "call_scripts", "caller_attendance_overrides",
    "caller_digests", "caller_status_logs", "callers", "conversations",
    "incidents", "knowledge_chunks", "knowledge_documents", "message_templates",
    "meta_templates", "phone_number_quality_history", "phone_numbers",
    "reengagement_logs", "reengagement_steps", "segment_templates",
    "telecalling_upload_batches", "voice_numbers", "whatsapp_insights_snapshots",
    "ad_campaigns", "ai_prompts", "ai_tune_suggestions", "app_notifications",
    "app_audit_logs", "leads", "app_settings", "tenant_users",
]


@router.delete("/clients/{tenant_id}")
def delete_client(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id, name").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_name = tenant.data["name"]

    owner_row = (
        db.table("tenant_users").select("user_id")
        .eq("tenant_id", tenant_id).eq("role", "owner")
        .maybe_single().execute()
    )
    caller_users = (
        db.table("callers").select("user_id")
        .eq("tenant_id", tenant_id)
        .not_.is_("user_id", "null")
        .execute()
    )
    user_ids_to_delete = []
    if owner_row.data and owner_row.data.get("user_id"):
        user_ids_to_delete.append(owner_row.data["user_id"])
    for c in (caller_users.data or []):
        if c.get("user_id"):
            user_ids_to_delete.append(c["user_id"])

    for table in _ALL_TENANT_TABLES:
        try:
            db.table(table).delete().eq("tenant_id", tenant_id).execute()
        except Exception as e:
            logger.warning("delete_client: could not clear %s: %s", table, e)

    db.table("tenants").delete().eq("id", tenant_id).execute()

    for uid in user_ids_to_delete:
        try:
            db.auth.admin.delete_user(uid)
        except Exception as e:
            logger.warning("delete_client: could not delete auth user %s: %s", uid, e)

    logger.warning("OPERATOR DELETE CLIENT: %s (%s) — all data purged", tenant_name, tenant_id)
    return {"deleted": True, "tenant_name": tenant_name}


@router.get("/clients/{tenant_id}/audit-logs")
def client_audit_logs(
    tenant_id: str,
    page: int = 1,
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    _admin: dict = Depends(get_system_admin),
):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    q = db.table("app_audit_logs").select(
        "id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at",
        count="exact",
    ).eq("tenant_id", tenant_id)

    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to + "T23:59:59.999Z")

    offset = (page - 1) * limit
    result = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    return {"data": result.data or [], "total": result.count or 0, "page": page, "limit": limit}


@router.get("/clients/{tenant_id}/audit-logs/csv")
def client_audit_logs_csv(
    tenant_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _admin: dict = Depends(get_system_admin),
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    db = get_supabase()
    tenant = db.table("tenants").select("id, name").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    q = db.table("app_audit_logs").select(
        "id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at",
    ).eq("tenant_id", tenant_id)

    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to + "T23:59:59.999Z")

    result = q.order("created_at", desc=True).limit(5000).execute()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Time", "Action", "Actor Role", "Target Type", "Target ID", "Details"])
    for r in (result.data or []):
        meta = r.get("metadata") or {}
        details = "; ".join(f"{k}={v}" for k, v in meta.items() if v is not None and v != "********")
        writer.writerow([
            r.get("created_at", ""),
            r.get("action", ""),
            r.get("actor_role", ""),
            r.get("target_type", ""),
            r.get("target_id", ""),
            details,
        ])

    buf.seek(0)
    filename = f"audit-log-{tenant.data['name'].replace(' ', '_')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
