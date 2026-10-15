import logging
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

QUALITY_MAP = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}


async def handle_quality_red(phone_number_id: str) -> None:
    db = get_supabase()

    old_row = db.table("phone_numbers").select("*").eq("id", phone_number_id).limit(1).execute()
    if not old_row.data:
        logger.warning(f"handle_quality_red: no phone_number row found for id={phone_number_id}")
        return

    old_number = old_row.data[0]
    tenant_id = old_number.get("tenant_id")
    if not tenant_id:
        logger.warning(f"handle_quality_red: missing tenant_id for phone_number id={phone_number_id}")
        db.table("incidents").insert({
            "type": "quality_red",
            "phone_number_id": phone_number_id,
            "detail": {"phone_number_id": phone_number_id, "message": "missing_tenant_id"},
        }).execute()
        return

    standby = (
        db.table("phone_numbers")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .eq("role", "standby")
        .neq("id", phone_number_id)
        .gte("warm_up_day", 14)
        .order("warm_up_day", desc=True)
        .limit(1)
        .execute()
    )

    if not standby.data:
        logger.warning(f"handle_quality_red: no standby available for number={phone_number_id}")
        db.table("incidents").insert({
            "type": "quality_red",
            "tenant_id": tenant_id,
            "phone_number_id": phone_number_id,
            "detail": {"phone_number_id": phone_number_id, "message": "no_standby_available"},
        }).execute()
        return

    new_number = standby.data[0]
    new_number_id = new_number["id"]

    db.table("phone_numbers").update({"role": "primary"}).eq("id", new_number_id).execute()
    logger.info(f"handle_quality_red: promoted standby id={new_number_id} to primary")

    db.table("phone_numbers").update({"role": "standby", "status": "restricted"}).eq("id", phone_number_id).execute()
    logger.info(f"handle_quality_red: demoted old primary id={phone_number_id} to standby/restricted")

    # ── Update the "sticky note" so the AI sends from the new number ──
    new_meta_id = new_number.get("meta_phone_number_id")
    if new_meta_id:
        db.table("app_settings").upsert(
            {"key": "meta_phone_number_id", "value": new_meta_id, "tenant_id": tenant_id, "is_secret": False},
            on_conflict="tenant_id,key",
        ).execute()
        logger.info(f"handle_quality_red: updated app_settings meta_phone_number_id to {new_meta_id}")

        # Clear the in-memory cache so the new value is used immediately
        from app.config_dynamic import invalidate_cache
        invalidate_cache("meta_phone_number_id")

    db.table("incidents").insert({
        "type": "failover",
        "tenant_id": tenant_id,
        "phone_number_id": phone_number_id,
        "detail": {"old_number_id": phone_number_id, "new_number_id": new_number_id},
    }).execute()

    db.table("incidents").insert({
        "type": "standby_promoted",
        "tenant_id": tenant_id,
        "phone_number_id": new_number_id,
        "detail": {"old_number_id": phone_number_id, "new_number_id": new_number_id},
    }).execute()

    await send_migration_notice(new_number, tenant_id)


async def handle_quality_yellow(phone_number_id: str) -> None:
    db = get_supabase()

    existing = db.table("phone_numbers").select("tenant_id").eq("id", phone_number_id).limit(1).execute()
    tenant_id = (existing.data or [{}])[0].get("tenant_id")

    db.table("phone_numbers").update({"quality_rating": "yellow"}).eq("id", phone_number_id).execute()
    logger.info(f"handle_quality_yellow: marked number id={phone_number_id} as yellow")

    incident_payload = {
        "type": "quality_yellow",
        "phone_number_id": phone_number_id,
        "detail": {},
    }
    if tenant_id:
        incident_payload["tenant_id"] = tenant_id
    db.table("incidents").insert(incident_payload).execute()


async def send_migration_notice(new_number_row: dict, tenant_id: str) -> int:
    from datetime import datetime, timedelta, timezone
    from app.services.meta_cloud import send_text_message
    from app.config import settings

    db = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    if not tenant_id:
        logger.warning("Cannot send migration notice: missing tenant_id")
        return 0

    recent_lead_ids = list({
        r["lead_id"] for r in
        (
            db.table("messages")
            .select("lead_id")
            .eq("tenant_id", tenant_id)
            .gte("created_at", cutoff)
            .execute()
            .data
            or []
        )
        if r.get("lead_id")
    })
    if not recent_lead_ids:
        return 0

    leads = (
        db.table("leads")
        .select("phone")
        .eq("tenant_id", tenant_id)
        .in_("id", recent_lead_ids)
        .execute()
        .data
        or []
    )

    phone_number_id = new_number_row.get("meta_phone_number_id")
    access_token = settings.meta_access_token
    if not phone_number_id or not access_token:
        logger.warning("Cannot send migration notice: missing meta credentials")
        return 0

    sent = 0
    for lead in leads:
        try:
            await send_text_message(
                to_number=lead["phone"],
                text="Hi! We've moved to a new WhatsApp number. Please save this contact and reply here to continue our conversation.",
                phone_number_id=phone_number_id,
                access_token=access_token,
            )
            sent += 1
        except Exception as e:
            logger.error(f"Migration notice failed for {lead['phone']}: {e}")

    db.table("incidents").insert({
        "type": "migration_sent",
        "tenant_id": tenant_id,
        "phone_number_id": new_number_row["id"],
        "detail": {"leads_notified": sent},
    }).execute()

    return sent


async def update_number_quality(
    meta_phone_number_id: str,
    quality_rating: str,
    messaging_tier: int | None = None,
) -> str | None:
    db = get_supabase()

    existing = (
        db.table("phone_numbers")
        .select("id")
        .eq("meta_phone_number_id", meta_phone_number_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        logger.warning(f"update_number_quality: no row for meta_phone_number_id={meta_phone_number_id}")
        return None

    row_id = existing.data[0]["id"]
    updates: dict = {"quality_rating": QUALITY_MAP.get(quality_rating, quality_rating.lower())}
    if messaging_tier is not None:
        updates["messaging_tier"] = messaging_tier

    db.table("phone_numbers").update(updates).eq("id", row_id).execute()
    logger.info(f"update_number_quality: id={row_id} quality={quality_rating} tier={messaging_tier}")
    return row_id
