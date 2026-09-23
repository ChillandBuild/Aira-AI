import logging

from app.db.supabase import get_supabase
from app.routes.upload import _normalize_phone
from app.services.growth import record_stage_event, sync_follow_up_jobs
from app.services.segmentation import new_lead_score_and_segment

logger = logging.getLogger(__name__)


def create_inbound_lead(
    tenant_id: str,
    phone: str,
    source: str,
    *,
    name: str | None = None,
    collected_data: dict | None = None,
    opt_in_source: str | None = None,
    db=None,
) -> str | None:
    """Single-enquiry lead intake, for sources that arrive one at a time
    (marketplace webhooks). Mirrors the WhatsApp inbound path in webhook.py:
    normalise phone, find-or-revive on (tenant_id, phone), else score + insert,
    then record the creation event and try auto-assignment.

    NOT for bulk sources: CSV and telecalling upload insert in batches of 100
    with one dedupe query for the whole file, which this per-lead function
    would turn into a slow per-row loop. Those two stay on their own path.

    Returns the lead id, or None if the phone doesn't normalise to anything
    usable.
    """
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        logger.warning(f"create_inbound_lead: unusable phone {phone!r} for tenant {tenant_id}, source={source}")
        return None

    db = db or get_supabase()

    existing = (
        db.table("leads")
        .select("id, deleted_at")
        .eq("tenant_id", tenant_id)
        .eq("phone", normalized_phone)
        .limit(1)
        .execute()
    )
    if existing.data:
        lead_id = existing.data[0]["id"]
        if existing.data[0].get("deleted_at"):
            db.table("leads").update({
                "deleted_at": None,
                "ai_enabled": True,
                "needs_human_intervention": False,
            }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
            logger.info(f"Restored soft-deleted lead {lead_id} on {source} inbound")
        return lead_id

    initial_score, initial_segment = new_lead_score_and_segment(tenant_id)
    payload = {
        "phone": normalized_phone,
        "source": source,
        "score": initial_score,
        "segment": initial_segment,
        "tenant_id": tenant_id,
    }
    if name:
        payload["name"] = name
    if collected_data:
        payload["collected_data"] = collected_data
    if opt_in_source:
        payload["opt_in_source"] = opt_in_source

    inserted = db.table("leads").insert(payload).execute()
    lead_id = inserted.data[0]["id"]

    record_stage_event(
        lead_id,
        to_segment=initial_segment,
        event_type="created",
        metadata={"source": source},
        tenant_id=tenant_id,
        db=db,
    )

    try:
        from app.services.assignment import maybe_assign_lead
        maybe_assign_lead(lead_id, tenant_id, initial_segment, source, reason="created")
    except Exception as e:
        logger.warning(f"Auto-assign failed for lead {lead_id} (source={source}): {e}")

    try:
        sync_follow_up_jobs(
            lead_id,
            segment=initial_segment,
            phone=normalized_phone,
            converted_at=None,
            ai_enabled=True,
            reason=source,
            tenant_id=tenant_id,
            db=db,
        )
    except Exception as e:
        logger.warning(f"sync_follow_up_jobs failed for lead {lead_id} (source={source}): {e}")

    return lead_id
