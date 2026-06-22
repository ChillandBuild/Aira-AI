import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

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
    ("booking_event_name", False), ("booking_ref_prefix", False), ("booking_amount_paise", False),
    ("razorpay_key_id", False), ("razorpay_key_secret", True),
    ("razorpay_webhook_secret", True),
]


def _seed_app_settings(db, tenant_id: str) -> None:
    try:
        db.table("app_settings").insert([
            {"tenant_id": tenant_id, "key": k, "value": None, "is_secret": s}
            for k, s in _SETTING_KEYS
        ]).execute()
    except Exception as e:
        logger.warning(f"Failed to seed app_settings for tenant {tenant_id}: {e}")


class CreateTenantPayload(BaseModel):
    name: str


@router.post("/")
def create_tenant(payload: CreateTenantPayload, user: dict = Depends(get_current_user)):
    db = get_supabase()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tenant name is required")

    existing = (
        db.table("tenant_users")
        .select("tenant_id")
        .eq("user_id", user["user_id"])
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return {"tenant_id": existing.data["tenant_id"], "already_exists": True}

    tenant = db.table("tenants").insert({"name": name}).execute()
    tenant_id = tenant.data[0]["id"]

    db.table("tenant_users").insert({
        "tenant_id": tenant_id,
        "user_id": user["user_id"],
        "role": "owner",
    }).execute()

    _seed_app_settings(db, tenant_id)

    try:
        db.table("callers").insert({
            "tenant_id": tenant_id,
            "user_id": user["user_id"],
            "name": "Admin",
            "active": True,
            "status": "active",
            "overall_score": 10.0,
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to seed admin caller for tenant {tenant_id}: {e}")

    logger.info(f"Tenant created: {tenant_id} for user {user['user_id']}")
    return {"tenant_id": tenant_id, "already_exists": False}


@router.get("/status")
def tenant_status(user: dict = Depends(get_current_user)):
    db = get_supabase()
    result = (
        db.table("tenant_users")
        .select("tenant_id, role")
        .eq("user_id", user["user_id"])
        .maybe_single()
        .execute()
    )
    admin = (
        db.table("system_admins")
        .select("user_id")
        .eq("user_id", user["user_id"])
        .limit(1)
        .execute()
    )
    is_system_admin = bool(admin and admin.data)

    if not result or not result.data:
        return {"has_tenant": False, "is_system_admin": is_system_admin}
    return {
        "has_tenant": True,
        "tenant_id": result.data["tenant_id"],
        "role": result.data["role"],
        "is_system_admin": is_system_admin,
    }
