"""The tenant's own business identity (legal name, address, GSTIN) and its GST
pricing convention. Printed on the monthly sales export so the auditor's file
belongs to the client, never to Aira.

Stored as one JSON blob in app_settings under key "business_details", same
shape as intake_config (services/intake.py get_intake_config). Not to be confused with services/business_profile.py, which is the AI prompt's description sections."""
import json
import logging
import re

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

SETTING_KEY = "business_details"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
TEXT_FIELDS = ("legal_name", "address", "city", "state", "pincode", "gstin", "email", "phone")


def _defaults(tenant_id: str, db) -> dict:
    """Seed from what onboarding already collected, so a tenant who never opens
    Business details still gets their own name on the export."""
    profile = {field: "" for field in TEXT_FIELDS}
    profile["prices_include_gst"] = True
    try:
        tenant = (
            db.table("tenants").select("name, contact_phone").eq("id", tenant_id).maybe_single().execute()
        )
        if tenant and tenant.data:
            profile["legal_name"] = tenant.data.get("name") or ""
            profile["phone"] = tenant.data.get("contact_phone") or ""
    except Exception as e:
        logger.warning(f"business_details: tenant lookup failed for {tenant_id}: {e}")
    return profile


def get_business_details(tenant_id: str, db=None) -> dict:
    db = db or get_supabase()
    profile = _defaults(tenant_id, db)
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", SETTING_KEY)
        .maybe_single()
        .execute()
    )
    if row and row.data and row.data.get("value"):
        try:
            stored = json.loads(row.data["value"])
            profile.update({k: v for k, v in stored.items() if k in profile and v is not None})
        except (TypeError, ValueError):
            logger.warning(f"business_details: unparseable value for tenant {tenant_id}")
    return profile


def save_business_details(tenant_id: str, profile: dict, db=None) -> dict:
    """Raises on write failure -- unlike config_dynamic.save_setting, which only
    logs, because the owner must know their auditor details weren't saved."""
    db = db or get_supabase()
    db.table("app_settings").upsert(
        {"key": SETTING_KEY, "value": json.dumps(profile), "tenant_id": tenant_id, "is_secret": False},
        on_conflict="tenant_id,key",
    ).execute()
    return profile


def prices_include_gst(tenant_id: str, db=None) -> bool:
    try:
        return bool(get_business_details(tenant_id, db).get("prices_include_gst", True))
    except Exception as e:
        logger.warning(f"business_details: defaulting prices_include_gst for {tenant_id}: {e}")
        return True
