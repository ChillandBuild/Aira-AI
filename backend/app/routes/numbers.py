import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.entitlements import get_purchased_quantity
from app.services.meta_cloud import get_number_quality

logger = logging.getLogger(__name__)
require_numbers_read = require_permission("numbers.view")
require_numbers_manage = require_permission("numbers.manage")

router = APIRouter(dependencies=[Depends(require_numbers_read)])


class CreatePhoneNumber(BaseModel):
    provider: str = "meta_cloud"
    number: str
    display_name: str
    meta_phone_number_id: str | None = None


class UpdatePhoneNumber(BaseModel):
    role: str | None = None
    status: str | None = None
    display_name: str | None = None
    paused_outbound: bool | None = None
    warm_up_day: int | None = None


@router.get("/")
async def list_phone_numbers(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("role")
        .order("quality_rating")
        .execute()
    )
    numbers_limit = get_purchased_quantity(db, tenant_id, "numbers_pool")
    return {
        "data": result.data or [],
        "numbers_pool": {"limit": numbers_limit, "used": len(result.data or [])},
    }


@router.post("/")
async def create_phone_number(
    payload: CreatePhoneNumber,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    if payload.provider != "meta_cloud":
        raise HTTPException(status_code=400, detail="Only meta_cloud provider is supported")
    db = get_supabase()

    number_limit = get_purchased_quantity(db, tenant_id, "numbers_pool")
    current = db.table("phone_numbers").select("id", count="exact").eq("tenant_id", tenant_id).execute().count or 0
    if current >= number_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Phone number limit reached ({current}/{number_limit}). Request more numbers from Subscriptions.",
        )

    insert_data = {
        "provider": payload.provider,
        "number": payload.number.strip(),
        "display_name": payload.display_name.strip(),
        "role": "standby",
        "status": "warming",
        "warm_up_day": 0,
        "paused_outbound": False,
        "tenant_id": tenant_id,
    }
    if payload.meta_phone_number_id is not None:
        insert_data["meta_phone_number_id"] = payload.meta_phone_number_id
    result = db.table("phone_numbers").insert(insert_data).execute()
    return result.data[0]


@router.patch("/{number_id}")
async def update_phone_number(
    number_id: UUID,
    payload: UpdatePhoneNumber,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    db = get_supabase()
    updates = {}
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.status is not None:
        updates["status"] = payload.status
    if payload.display_name is not None:
        updates["display_name"] = payload.display_name.strip()
    if payload.paused_outbound is not None:
        updates["paused_outbound"] = payload.paused_outbound
    if payload.warm_up_day is not None:
        updates["warm_up_day"] = payload.warm_up_day
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
        
    if payload.role == "primary":
        # Ensure exclusive primary logic: demote all other primary numbers to standby
        db.table("phone_numbers").update({"role": "standby"}).eq("tenant_id", tenant_id).eq("role", "primary").execute()
        
    result = db.table("phone_numbers").update(updates).eq("id", str(number_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Phone number not found")
    return result.data[0]


_QUALITY_MAP = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}
_WARM_UP_MAX = 14


@router.post("/{number_id}/sync-meta")
async def sync_number_from_meta(
    number_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    db = get_supabase()
    row_result = (
        db.table("phone_numbers")
        .select("*")
        .eq("id", str(number_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not row_result.data:
        raise HTTPException(status_code=404, detail="Phone number not found")
    row = row_result.data[0]

    meta_pid = row.get("meta_phone_number_id")
    if not meta_pid:
        raise HTTPException(status_code=400, detail="No Meta phone number ID set for this number")

    meta_data = await get_number_quality(phone_number_id=meta_pid, tenant_id=tenant_id)

    raw_quality = meta_data.get("quality_rating", "")
    quality = _QUALITY_MAP.get(raw_quality.upper(), row["quality_rating"])
    tier = meta_data.get("messaging_tier") or row["messaging_tier"]

    now = datetime.now(timezone.utc)
    last_reset_raw = row.get("last_reset_at")
    days_elapsed = 0
    if last_reset_raw:
        last_reset = datetime.fromisoformat(last_reset_raw.replace("Z", "+00:00"))
        days_elapsed = max(0, (now - last_reset).days)

    updates: dict = {
        "quality_rating": quality,
        "messaging_tier": tier,
        "daily_send_count": 0,
        "last_reset_at": now.isoformat(),
    }

    if row["status"] == "warming" and days_elapsed > 0:
        new_day = min(row["warm_up_day"] + days_elapsed, _WARM_UP_MAX)
        updates["warm_up_day"] = new_day
        if new_day >= _WARM_UP_MAX:
            updates["status"] = "active"

    result = (
        db.table("phone_numbers")
        .update(updates)
        .eq("id", str(number_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )

    # Always record a quality snapshot so Activity Log has something to show
    db.table("phone_number_quality_history").insert({
        "phone_number_id": str(number_id),
        "tenant_id": tenant_id,
        "quality_rating": quality,
        "messaging_tier": tier,
    }).execute()

    # Also write an incident if quality degraded
    old_quality = row.get("quality_rating", "green")
    if quality != old_quality:
        incident_type = "quality_yellow" if quality == "yellow" else "quality_red" if quality == "red" else None
        if incident_type:
            db.table("incidents").insert({
                "type": incident_type,
                "phone_number_id": str(number_id),
                "tenant_id": tenant_id,
                "detail": {
                    "number": row["number"],
                    "display_name": row["display_name"],
                    "old_quality": old_quality,
                    "new_quality": quality,
                    "source": "manual_sync",
                },
            }).execute()

    return result.data[0]


@router.delete("/{number_id}")
async def delete_phone_number(
    number_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    """Hard delete a phone number. FK on incidents.phone_number_id is ON
    DELETE SET NULL so historical incidents stay intact, just lose the ref."""
    db = get_supabase()
    active_result = (
        db.table("phone_numbers")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .execute()
    )
    active_ids = [row["id"] for row in (active_result.data or [])]
    if len(active_ids) == 1 and active_ids[0] == str(number_id):
        raise HTTPException(status_code=400, detail="Cannot delete last active number")
    result = (
        db.table("phone_numbers")
        .delete()
        .eq("id", str(number_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Phone number not found")
    return {"deleted": True}
