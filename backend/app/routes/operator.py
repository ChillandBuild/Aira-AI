import logging
import secrets
from datetime import datetime, timezone, timedelta
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
    service: ServiceTier


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
    features = _FEATURE_MAP[payload.service]
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
        metadata={"service": payload.service, "enabled_features": features},
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


class UpdatePageTogglesPayload(BaseModel):
    page_toggles: dict


@router.get("/clients/{tenant_id}/detail")
def get_client_detail(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("*").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    owner = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").maybe_single().execute()
    owner_email = None
    if owner.data:
        try:
            owner_user = db.auth.admin.get_user_by_id(owner.data["user_id"])
            owner_email = owner_user.user.email if hasattr(owner_user, 'user') else owner_user.get("user", {}).get("email")
        except Exception as e:
            logger.warning(f"Could not fetch email for user {owner.data['user_id']}: {e}")

    settings = db.table("app_settings").select("key, value, is_secret").eq("tenant_id", tenant_id).execute()
    settings_summary = []
    for s in (settings.data or []):
        settings_summary.append({
            "key": s["key"],
            "has_value": s["value"] is not None and s["value"] != "",
            "is_secret": s["is_secret"]
        })

    def count_table(table):
        try:
            res = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id).execute()
            return res.count or 0
        except:
            return 0

    counts = {
        "leads": count_table("leads"),
        "messages": count_table("messages"),
        "call_logs": count_table("call_logs"),
        "callers": count_table("callers")
    }

    return {
        "tenant": tenant.data,
        "owner_email": owner_email,
        "settings_summary": settings_summary,
        "counts": counts
    }


@router.get("/clients/{tenant_id}/data-counts")
def get_client_data_counts(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    def count_table(table):
        try:
            res = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id).execute()
            return res.count or 0
        except Exception as e:
            logger.warning(f"Error counting {table}: {e}")
            return 0

    return {
        "leads": count_table("leads"),
        "messages": count_table("messages"),
        "conversations": count_table("conversations"),
        "call_logs": count_table("call_logs"),
        "broadcast_recipients": count_table("broadcast_recipients"),
        "scheduled_broadcasts": count_table("scheduled_broadcasts"),
        "knowledge_documents": count_table("knowledge_docs"),
        "templates": count_table("message_templates"),
        "bookings": count_table("bookings"),
        "notes": count_table("lead_notes"),
        "todos": count_table("employee_todos"),
        "callers": count_table("callers"),
        "team_members": count_table("tenant_users")
    }


@router.get("/clients/{tenant_id}/page-toggles")
def get_page_toggles(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("page_toggles").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"page_toggles": tenant.data.get("page_toggles")}


@router.patch("/clients/{tenant_id}/page-toggles")
def update_page_toggles(tenant_id: str, payload: UpdatePageTogglesPayload, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    result = db.table("tenants").update({"page_toggles": payload.page_toggles}).eq("id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant not found")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action="operator.page_toggles_updated",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"page_toggles": payload.page_toggles},
    )
    return {"tenant_id": tenant_id, "page_toggles": payload.page_toggles}


@router.get("/clients/{tenant_id}/team")
def get_client_team(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    users = db.table("tenant_users").select("tenant_id, user_id, role, created_at").eq("tenant_id", tenant_id).execute()
    callers = db.table("callers").select("id, name, active, overall_score, created_at, user_id").eq("tenant_id", tenant_id).execute()
    return {"users": users.data or [], "callers": callers.data or []}


@router.get("/clients/{tenant_id}/activity")
def get_client_activity(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    now = datetime.now(timezone.utc)
    start_7d = (now - timedelta(days=7)).isoformat()
    start_30d = (now - timedelta(days=30)).isoformat()

    def count_since(table, since):
        try:
            res = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", since).execute()
            return res.count or 0
        except:
            return 0

    recent_leads = db.table("leads").select("id, name, phone, source, segment, score, created_at").eq("tenant_id", tenant_id).order("created_at", desc=True).limit(10).execute()

    return {
        "leads_7d": count_since("leads", start_7d),
        "messages_7d": count_since("messages", start_7d),
        "calls_7d": count_since("call_logs", start_7d),
        "leads_30d": count_since("leads", start_30d),
        "messages_30d": count_since("messages", start_30d),
        "calls_30d": count_since("call_logs", start_30d),
        "recent_leads": recent_leads.data or []
    }


@router.get("/clients/{tenant_id}/audit-log")
def get_client_audit_log(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    logs = db.table("app_audit_logs").select("id, tenant_id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at").eq("tenant_id", tenant_id).order("created_at", desc=True).limit(50).execute()
    return {"entries": logs.data or []}


@router.post("/clients/{tenant_id}/wipe-calls")
def wipe_calls(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    for table in ["call_logs", "caller_digests"]:
        try:
            res = db.table(table).delete().eq("tenant_id", tenant_id).execute()
            deleted_counts[table] = len(res.data or [])
        except Exception as e:
            logger.warning(f"wipe-calls: could not clear {table} for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.calls_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-broadcasts")
def wipe_broadcasts(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    for table in ["broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts", "broadcast_tags", "scheduled_broadcasts"]:
        try:
            res = db.table(table).delete().eq("tenant_id", tenant_id).execute()
            deleted_counts[table] = len(res.data or [])
        except Exception as e:
            logger.warning(f"wipe-broadcasts: could not clear {table} for {tenant_id}: {e}")
    try:
        db.table("app_settings").delete().eq("tenant_id", tenant_id).eq("key", "broadcast_history").execute()
    except Exception as e:
        logger.warning(f"wipe-broadcasts: could not clear broadcast_history setting for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.broadcasts_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-knowledge")
def wipe_knowledge(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    for table in ["knowledge_chunks", "knowledge_docs"]:
        try:
            res = db.table(table).delete().eq("tenant_id", tenant_id).execute()
            deleted_counts[table] = len(res.data or [])
        except Exception as e:
            logger.warning(f"wipe-knowledge: could not clear {table} for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.knowledge_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-templates")
def wipe_templates(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    try:
        res = db.table("message_templates").delete().eq("tenant_id", tenant_id).execute()
        deleted_counts["message_templates"] = len(res.data or [])
    except Exception as e:
        logger.warning(f"wipe-templates: could not clear message_templates for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.templates_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-bookings")
def wipe_bookings(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    try:
        res = db.table("bookings").delete().eq("tenant_id", tenant_id).execute()
        deleted_counts["bookings"] = len(res.data or [])
    except Exception as e:
        logger.warning(f"wipe-bookings: could not clear bookings for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.bookings_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-notes")
def wipe_notes(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    for table in ["lead_notes", "employee_todos"]:
        try:
            res = db.table(table).delete().eq("tenant_id", tenant_id).execute()
            deleted_counts[table] = len(res.data or [])
        except Exception as e:
            logger.warning(f"wipe-notes: could not clear {table} for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.notes_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-team")
def wipe_team(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data: raise HTTPException(status_code=404, detail="Tenant not found")
    deleted_counts = {}
    for table in ["caller_attendance", "callers"]:
        try:
            res = db.table(table).delete().eq("tenant_id", tenant_id).execute()
            deleted_counts[table] = len(res.data or [])
        except Exception as e:
            logger.warning(f"wipe-team: could not clear {table} for {tenant_id}: {e}")
    try:
        res = db.table("tenant_users").delete().eq("tenant_id", tenant_id).neq("role", "owner").execute()
        deleted_counts["tenant_users"] = len(res.data or [])
    except Exception as e:
        logger.warning(f"wipe-team: could not clear tenant_users for {tenant_id}: {e}")
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.team_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": deleted_counts, "tenant_id": tenant_id}


@router.post("/clients/{tenant_id}/wipe-all")
def wipe_all(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    # Call all the individual wipes
    results = {}
    results.update(wipe_calls(tenant_id, _admin)["deleted"])
    results.update(wipe_broadcasts(tenant_id, _admin)["deleted"])
    results.update(wipe_knowledge(tenant_id, _admin)["deleted"])
    results.update(wipe_templates(tenant_id, _admin)["deleted"])
    results.update(wipe_bookings(tenant_id, _admin)["deleted"])
    results.update(wipe_notes(tenant_id, _admin)["deleted"])
    results.update(wipe_team(tenant_id, _admin)["deleted"])
    
    # And leads
    leads_res = wipe_leads(tenant_id, _admin)
    results["leads"] = leads_res["deleted"]
    
    db = get_supabase()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=_admin.get("user_id"), actor_role="system_admin", action="operator.all_wiped", target_type="tenant", target_id=tenant_id)
    return {"deleted": results, "tenant_id": tenant_id}
