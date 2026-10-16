"""Pull the numbers pool's health from Meta and act on it.

Used by POST /numbers/sync-from-meta, POST /numbers/{id}/sync-meta, the
12-hourly full pool sync and the 4-hourly quality check. Every field written
comes from Meta (see number_health.meta_snapshot); Anril only adds its own
clocks (warm-up, rest) on top.
"""
import logging
from datetime import datetime, timezone

from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.services.failover import ensure_healthy_primary, handle_quality_red
from app.services.meta_cloud import get_number_quality, list_waba_phone_numbers
from app.services.number_health import is_resting, lifecycle_updates, meta_snapshot
from app.services.numbers_pool import get_unlocked_number_ids, normalize_phone_number

logger = logging.getLogger(__name__)


async def apply_meta_snapshot(db, tenant_id: str, row: dict, meta: dict, unlocked_ids: set[str], source: str) -> dict:
    """Write Meta's view of one number onto its row, advance warm-up/rest,
    and start a failover if Meta now reports it Red. Returns the merged row."""
    now = datetime.now(timezone.utc)
    row = {**row, "tenant_id": tenant_id}
    updates = meta_snapshot(meta)

    # Meta owns the display name -- it's the Meta-approved `verified_name`
    # customers see, changeable only in WhatsApp Manager (a rename there goes
    # through Meta's review), so sync mirrors it verbatim.
    verified_name = (meta.get("verified_name") or "").strip()
    if verified_name and verified_name != row.get("display_name"):
        updates["display_name"] = verified_name

    merged = {**row, **updates}
    updates.update(lifecycle_updates(merged, now, row["id"] in unlocked_ids))
    merged = {**row, **updates}

    db.table("phone_numbers").update(updates).eq("id", row["id"]).eq("tenant_id", tenant_id).execute()

    new_quality = updates.get("quality_rating")
    if new_quality:
        try:
            db.table("phone_number_quality_history").insert({
                "phone_number_id": row["id"],
                "tenant_id": tenant_id,
                "quality_rating": new_quality,
                "messaging_tier": merged.get("messaging_tier"),
            }).execute()
        except Exception as e:
            logger.warning(f"quality history insert failed for {row['id']}: {e}")

    if row.get("status") == "warming" and updates.get("status") == "active":
        _incident(db, "warm_up_complete", row, {"source": source})
    if row.get("status") == "restricted" and updates.get("status") in ("active", "warming"):
        _incident(db, "number_recovered", row, {"source": source})
    if new_quality == "yellow" and row.get("quality_rating") != "yellow":
        _incident(db, "quality_yellow", row, {
            "old_quality": row.get("quality_rating"), "new_quality": new_quality, "source": source,
        })

    if new_quality == "red" and not is_resting(merged):
        await handle_quality_red(row["id"], source=source)
        refreshed = db.table("phone_numbers").select("*").eq("id", row["id"]).limit(1).execute().data
        if refreshed:
            merged = refreshed[0]
    return merged


def _incident(db, kind: str, row: dict, detail: dict) -> None:
    try:
        db.table("incidents").insert({
            "type": kind,
            "tenant_id": row["tenant_id"],
            "phone_number_id": row["id"],
            "detail": {"number": row.get("number"), "display_name": row.get("display_name"), **detail},
        }).execute()
    except Exception as e:
        logger.warning(f"number_sync: incident insert failed ({kind}): {e}")


async def sync_one_number(db, row: dict, source: str) -> dict:
    meta = await get_number_quality(phone_number_id=row["meta_phone_number_id"], tenant_id=row["tenant_id"])
    unlocked = get_unlocked_number_ids(db, row["tenant_id"])
    merged = await apply_meta_snapshot(db, row["tenant_id"], row, meta, unlocked, source)
    await ensure_healthy_primary(row["tenant_id"])
    return merged


async def sync_tenant_numbers(db, tenant_id: str, source: str) -> tuple[int, int]:
    """Discover every number on the tenant's WABA and refresh all of them.
    New numbers land as standby/warming (never auto-primary). Returns
    (synced, failed). Raises ValueError when no WABA is connected."""
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        raise ValueError("no_waba")

    meta_numbers = await list_waba_phone_numbers(waba_id=waba_id, tenant_id=tenant_id)
    existing_rows = db.table("phone_numbers").select("*").eq("tenant_id", tenant_id).execute().data or []
    by_meta_id = {r["meta_phone_number_id"]: r for r in existing_rows if r.get("meta_phone_number_id")}
    by_number = {r["number"]: r for r in existing_rows if r.get("number")}

    synced = failed = 0
    for meta_num in meta_numbers:
        try:
            meta_pid = meta_num.get("id")
            if not meta_pid:
                failed += 1
                continue
            display_number = normalize_phone_number(meta_num.get("display_phone_number") or "")
            row = by_meta_id.get(meta_pid) or (by_number.get(display_number) if display_number else None)

            if row is None:
                inserted = db.table("phone_numbers").insert({
                    "provider": "meta_cloud",
                    "number": display_number or meta_pid,
                    "display_name": meta_num.get("verified_name") or display_number or meta_pid,
                    "role": "standby",
                    "status": "warming",
                    "warm_up_day": 0,
                    "paused_outbound": False,
                    "meta_phone_number_id": meta_pid,
                    "tenant_id": tenant_id,
                }).execute()
                row = inserted.data[0]
                by_meta_id[meta_pid] = row
            elif not row.get("meta_phone_number_id"):
                db.table("phone_numbers").update({"meta_phone_number_id": meta_pid}).eq("id", row["id"]).eq("tenant_id", tenant_id).execute()
                row = {**row, "meta_phone_number_id": meta_pid}

            if row.get("status") == "archived":
                # Meta still lists it, so it's back in the pool.
                db.table("phone_numbers").update({"status": "warming", "paused_outbound": False}).eq("id", row["id"]).eq("tenant_id", tenant_id).execute()
                row = {**row, "status": "warming", "paused_outbound": False}

            # Recomputed per number: an insert above can shift who's unlocked.
            unlocked = get_unlocked_number_ids(db, tenant_id)
            await apply_meta_snapshot(db, tenant_id, row, meta_num, unlocked, source)
            synced += 1
        except Exception:
            logger.exception("number sync: failed to process one Meta number for tenant %s", tenant_id)
            failed += 1

    await ensure_healthy_primary(tenant_id)
    return synced, failed


async def sync_all_tenants_pool() -> None:
    """12-hourly: full pool sync for every tenant with a connected WABA."""
    db = get_supabase()
    tenant_ids = {
        r["tenant_id"] for r in (
            db.table("app_settings").select("tenant_id").eq("key", "meta_waba_id")
            .not_.is_("value", "null").execute().data or []
        ) if r.get("tenant_id")
    }
    for tenant_id in tenant_ids:
        try:
            synced, failed = await sync_tenant_numbers(db, tenant_id, source="scheduled_pool_sync")
            logger.info(f"Pool sync tenant {tenant_id}: synced={synced} failed={failed}")
        except ValueError:
            continue
        except Exception as e:
            logger.warning(f"Pool sync failed for tenant {tenant_id}: {e}")


async def sync_all_number_quality() -> None:
    """4-hourly: refresh each known number from Meta so a Red is caught fast."""
    db = get_supabase()
    rows = (
        db.table("phone_numbers").select("*")
        .not_.is_("meta_phone_number_id", "null").neq("status", "archived")
        .execute().data or []
    )
    synced = 0
    for row in rows:
        try:
            await sync_one_number(db, row, source="scheduled_quality_check")
            synced += 1
        except Exception as e:
            logger.warning(f"Quality check failed for number {row['id']}: {e}")
    logger.info(f"Number quality check complete: {synced}/{len(rows)} number(s)")
