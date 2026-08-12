import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.meta_cloud import get_number_quality, list_waba_phone_numbers
from app.services.numbers_pool import (
    get_unlocked_number_ids,
    normalize_phone_number,
    numbers_pool_limit,
)

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


_numbers_pool_limit = numbers_pool_limit

# Must match phone_numbers_status_check in supabase/migrations/009_phone_numbers_incidents.sql
_VALID_PHONE_NUMBER_STATUSES = frozenset({"active", "warming", "restricted", "archived"})


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
    rows = result.data or []
    numbers_limit = numbers_pool_limit(db, tenant_id)
    unlocked_ids = get_unlocked_number_ids(db, tenant_id)
    data = [
        {**row, "locked": row.get("status") != "archived" and row["id"] not in unlocked_ids}
        for row in rows
    ]
    return {
        "data": data,
        "numbers_pool": {"limit": numbers_limit, "used": len(rows)},
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

    number_limit = _numbers_pool_limit(db, tenant_id)
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


@router.post("/sync-from-meta")
async def sync_all_numbers_from_meta(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    """Pull every number registered on the tenant's Meta WABA into
    phone_numbers -- regardless of numbers_pool quota. Numbers beyond quota
    land locked (role=standby, never auto-primary), not rejected."""
    db = get_supabase()
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        raise HTTPException(status_code=400, detail="Connect Meta WhatsApp (meta_waba_id) in Settings first")

    meta_numbers = await list_waba_phone_numbers(waba_id=waba_id, tenant_id=tenant_id)

    existing_rows = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .execute()
        .data
        or []
    )
    by_meta_id = {r["meta_phone_number_id"]: r for r in existing_rows if r.get("meta_phone_number_id")}
    by_number = {r["number"]: r for r in existing_rows if r.get("number")}

    # Snapshot lock state *before* this sync's inserts/updates -- used only to
    # decide whether an existing row's warm-up may promote it to "active".
    # Newly-inserted rows never attempt promotion (they start at day 0), so
    # this snapshot doesn't need to account for numbers this same sync adds.
    unlocked_before = get_unlocked_number_ids(db, tenant_id)

    now = datetime.now(timezone.utc)
    synced = 0
    failed = 0

    for meta_num in meta_numbers:
        try:
            meta_pid = meta_num.get("id")
            if not meta_pid:
                failed += 1
                continue

            raw_quality = (meta_num.get("quality_rating") or "").upper()
            # Meta's phone_numbers list edge returns GREEN/YELLOW/RED (same
            # format webhook.py's phone_number_quality_update handler and
            # failover.py's QUALITY_MAP already rely on) -- not the HIGH/
            # MEDIUM/LOW values _QUALITY_MAP below maps, which belongs to
            # the older single-number sync_number_from_meta path only.
            quality = _WABA_QUALITY_MAP.get(raw_quality)
            tier = _TIER_MAP.get(meta_num.get("messaging_limit_tier") or "")
            display_number = normalize_phone_number(meta_num.get("display_phone_number") or "")

            row = by_meta_id.get(meta_pid) or (by_number.get(display_number) if display_number else None)

            if row is None:
                insert_data: dict = {
                    "provider": "meta_cloud",
                    "number": display_number or meta_pid,
                    "display_name": meta_num.get("verified_name") or display_number or meta_pid,
                    "role": "standby",
                    "status": "warming",
                    "warm_up_day": 0,
                    "paused_outbound": False,
                    "meta_phone_number_id": meta_pid,
                    "tenant_id": tenant_id,
                }
                if quality:
                    insert_data["quality_rating"] = quality
                if tier:
                    insert_data["messaging_tier"] = tier
                inserted = db.table("phone_numbers").insert(insert_data).execute()
                new_row = inserted.data[0]
                existing_rows.append(new_row)
                by_meta_id[meta_pid] = new_row
                if display_number:
                    by_number[display_number] = new_row
                synced += 1
                continue

            updates: dict = {"daily_send_count": 0, "last_reset_at": now.isoformat()}
            if quality:
                updates["quality_rating"] = quality
            if tier:
                updates["messaging_tier"] = tier
            if not row.get("meta_phone_number_id"):
                updates["meta_phone_number_id"] = meta_pid

            last_reset_raw = row.get("last_reset_at")
            days_elapsed = 0
            if last_reset_raw:
                last_reset = datetime.fromisoformat(last_reset_raw.replace("Z", "+00:00"))
                days_elapsed = max(0, (now - last_reset).days)

            locked = row["id"] not in unlocked_before
            if row["status"] == "warming" and days_elapsed > 0:
                new_day = min(row["warm_up_day"] + days_elapsed, _WARM_UP_MAX)
                updates["warm_up_day"] = new_day
                if new_day >= _WARM_UP_MAX and not locked:
                    updates["status"] = "active"

            db.table("phone_numbers").update(updates).eq("id", row["id"]).eq("tenant_id", tenant_id).execute()

            old_quality = row.get("quality_rating", "green")
            new_quality = updates.get("quality_rating", old_quality)
            if new_quality != old_quality:
                incident_type = "quality_yellow" if new_quality == "yellow" else "quality_red" if new_quality == "red" else None
                if incident_type:
                    db.table("incidents").insert({
                        "type": incident_type,
                        "phone_number_id": row["id"],
                        "tenant_id": tenant_id,
                        "detail": {
                            "number": row.get("number"),
                            "display_name": row.get("display_name"),
                            "old_quality": old_quality,
                            "new_quality": new_quality,
                            "source": "bulk_meta_sync",
                        },
                    }).execute()
            synced += 1
        except Exception:
            logger.exception("sync-from-meta: failed to process one Meta number for tenant %s", tenant_id)
            failed += 1

    result = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("role")
        .order("quality_rating")
        .execute()
    )
    rows = result.data or []
    numbers_limit = numbers_pool_limit(db, tenant_id)
    unlocked_after = get_unlocked_number_ids(db, tenant_id)
    data = [
        {**r, "locked": r.get("status") != "archived" and r["id"] not in unlocked_after}
        for r in rows
    ]
    return {
        "data": data,
        "numbers_pool": {"limit": numbers_limit, "used": len(rows)},
        "synced": synced,
        "failed": failed,
    }


@router.patch("/{number_id}")
async def update_phone_number(
    number_id: UUID,
    payload: UpdatePhoneNumber,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_numbers_manage),
):
    if payload.status is not None and payload.status not in _VALID_PHONE_NUMBER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.status}'. Must be one of: {', '.join(sorted(_VALID_PHONE_NUMBER_STATUSES))}.",
        )

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

    # Setting role="primary" is always allowed -- it's the unlock mechanism
    # itself (the primary slot is always guaranteed). Any other attempt to
    # activate a currently-locked number (flip to active, or resume outbound)
    # is blocked until the client either sets it primary or upgrades.
    attempting_activation = payload.status == "active" or payload.paused_outbound is False
    if attempting_activation and payload.role != "primary":
        unlocked_ids = get_unlocked_number_ids(db, tenant_id)
        if str(number_id) not in unlocked_ids:
            raise HTTPException(
                status_code=400,
                detail="This number is locked by your numbers pool quota. Set it as primary or upgrade in Subscriptions to activate it.",
            )

    if payload.role == "primary":
        # Ensure exclusive primary logic: demote all other primary numbers to standby
        db.table("phone_numbers").update({"role": "standby"}).eq("tenant_id", tenant_id).eq("role", "primary").execute()
        
    result = db.table("phone_numbers").update(updates).eq("id", str(number_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Phone number not found")
    return result.data[0]


_QUALITY_MAP = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}
_WABA_QUALITY_MAP = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}
_TIER_MAP = {"TIER_1000": 1000, "TIER_10000": 10000, "TIER_100000": 100000}
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
