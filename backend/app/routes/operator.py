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
    ("telecmi_user_id", False), ("telecmi_secret", True),
    ("telecmi_callerid", False), ("telecmi_recording_base_url", False),
    ("groq_api_key", True),
    ("ai_auto_reply_enabled", False),
    ("reengagement_enabled", False),
    ("booking_event_name", False), ("booking_ref_prefix", False), ("booking_amount_paise", False),
    ("razorpay_key_id", False), ("razorpay_key_secret", True),
    ("razorpay_webhook_secret", True),
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
    valid_features = {"whatsapp", "telecalling", "instagram", "facebook", "telegram"}

    if payload.features is not None:
        invalid = set(payload.features) - valid_features
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid features: {', '.join(invalid)}")
        features = payload.features
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
        "follow_up_jobs", "bookings",
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
            "booking_event_name": settings_map.get("booking_event_name"),
            "booking_ref_prefix": settings_map.get("booking_ref_prefix"),
            "booking_amount_paise": settings_map.get("booking_amount_paise"),
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
        db.table("messages").select("id, delivery_error, created_at")
        .eq("tenant_id", tenant_id).eq("delivery_status", "failed")
        .order("created_at", desc=True).limit(10).execute()
    )
    open_incidents = (
        db.table("incidents").select("id, type, severity, message, created_at")
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
            {"message_id": r["id"], "error": r.get("delivery_error"), "created_at": r["created_at"]}
            for r in (recent_errors.data or [])
        ],
        "open_incidents": open_incidents.data or [],
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
