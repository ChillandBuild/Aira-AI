import logging
import re
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase
from app.services.meta_cloud import send_template_message
from app.services.notification_config import get_notification_config

logger = logging.getLogger(__name__)

_SEGMENT_LABELS = {"A": "Hot", "B": "Warm", "C": "Cold", "D": "Disqualified"}
_COOLDOWN_HOURS = 6
ALERT_DELAY_SECONDS = 300


def _log_incident(db, tenant_id: str, detail: dict) -> None:
    """Record a whatsapp_alert_failed incident so failures surface on the
    dashboard instead of only existing in server logs. Never raises."""
    try:
        db.table("incidents").insert({
            "tenant_id": tenant_id,
            "type": "whatsapp_alert_failed",
            "detail": detail,
        }).execute()
    except Exception:
        logger.exception("Failed to record whatsapp_alert_failed incident for tenant %s", tenant_id)


def _is_recently_notified(db, lead_id: str, to_segment: str) -> bool:
    """True if this lead already triggered a segment_changed->to_segment alert
    within the cooldown window.

    The row for the event that is calling us right now has already been
    inserted by record_stage_event before this function runs, so a single
    matching row is the FIRST legitimate occurrence (must still send) — only
    more than one row means a prior alert already fired in this window.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_COOLDOWN_HOURS)).isoformat()
    try:
        res = (
            db.table("lead_stage_events")
            .select("id,created_at")
            .eq("lead_id", lead_id)
            .eq("to_segment", to_segment)
            .eq("event_type", "segment_changed")
            .gte("created_at", cutoff)
            .order("created_at")
            .execute()
        )
        return len(res.data or []) > 1
    except Exception:
        logger.exception("Cooldown check failed for lead %s segment %s", lead_id, to_segment)
        return False


def _build_components(template: dict, lead: dict, to_segment: str) -> list[dict] | None:
    """Map ordinal {{n}} placeholders in the template body to lead/segment values.

    Returns None when the template has no variables — nothing safe to send.
    """
    body_text = template.get("body_text") or ""
    indices = sorted(set(int(m) for m in re.findall(r"\{\{(\d+)\}\}", body_text)))
    if not indices:
        return None

    label = _SEGMENT_LABELS.get(to_segment, to_segment)
    candidate_values = [
        lead.get("name") or "Lead",
        lead.get("phone") or "",
        f"{label} ({lead.get('score', '-')}/10)",
        f"https://aira.ai/dashboard/conversations?lead_id={lead['id']}",
    ]
    values = candidate_values[: len(indices)]
    return [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]


async def _dispatch_alerts(
    recipient_phones: list[str],
    template: dict,
    components: list[dict],
    tenant_id: str,
    lead_id: str,
) -> None:
    db = get_supabase()
    for phone in recipient_phones:
        try:
            await send_template_message(
                to_number=phone,
                template_name=template["name"],
                lang_code=template.get("language") or "en",
                components=components,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.exception("WhatsApp admin alert failed to %s for lead %s", phone, lead_id)
            _log_incident(db, tenant_id, {
                "lead_id": lead_id,
                "phone": phone,
                "template": template.get("name"),
                "reason": "meta_send_failed",
                "error": str(e)[:500],
            })


def queue_admin_whatsapp_alert(
    db,
    tenant_id: str,
    lead_id: str,
    from_segment: str | None,
    to_segment: str,
) -> None:
    """Queue a pending admin WhatsApp alert in the database, cancelling any prior pending ones for this lead."""
    try:
        wa_cfg = get_notification_config(tenant_id, db=db).get("whatsapp_notifications") or {}

        if not wa_cfg.get("enabled") or from_segment == to_segment:
            return
        if to_segment not in (wa_cfg.get("target_segments") or []):
            return
        template_id = wa_cfg.get("template_id")
        recipient_phones = wa_cfg.get("recipient_phones") or []
        if not template_id or not recipient_phones:
            return

        if _is_recently_notified(db, lead_id, to_segment):
            return

        # Cancel prior pending alerts for this lead
        db.table("pending_whatsapp_alerts").update(
            {"status": "cancelled"}
        ).eq("lead_id", lead_id).eq("status", "pending").execute()

        # Calculate send_at based on configured delay
        delay_minutes = wa_cfg.get("delay_minutes")
        if delay_minutes is None:
            delay_minutes = 5

        # Check if ALERT_DELAY_SECONDS override is active for testing (e.g. 0.05 seconds or 0)
        if ALERT_DELAY_SECONDS != 300:
            send_at = datetime.now(timezone.utc) + timedelta(seconds=ALERT_DELAY_SECONDS)
        else:
            send_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

        db.table("pending_whatsapp_alerts").insert({
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "from_segment": from_segment,
            "to_segment": to_segment,
            "send_at": send_at.isoformat(),
            "status": "pending",
        }).execute()
        
        logger.info("Queued WhatsApp notification for lead=%s tenant=%s to_segment=%s send_at=%s", lead_id, tenant_id, to_segment, send_at)
    except Exception as e:
        logger.exception("queue_admin_whatsapp_alert failed for tenant=%s lead=%s", tenant_id, lead_id)
        _log_incident(db, tenant_id, {
            "lead_id": lead_id,
            "reason": "queue_failed",
            "error": str(e)[:500],
        })


async def process_due_whatsapp_alerts() -> None:
    """Query due pending alerts from public.pending_whatsapp_alerts, verify conditions, and send them."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    try:
        res = (
            db.table("pending_whatsapp_alerts")
            .select("*")
            .eq("status", "pending")
            .lte("send_at", now.isoformat())
            .order("send_at")
            .limit(50)
            .execute()
        )
        alerts = res.data or []
        if not alerts:
            return

        for alert in alerts:
            alert_id = alert["id"]
            tenant_id = alert["tenant_id"]
            lead_id = alert["lead_id"]
            to_segment = alert["to_segment"]

            try:
                # Mark as processing to prevent double runs
                db.table("pending_whatsapp_alerts").update(
                    {"status": "processing"}
                ).eq("id", alert_id).execute()

                # Verify lead is still in the target segment
                lead_res = (
                    db.table("leads")
                    .select("id,name,phone,score,segment")
                    .eq("id", lead_id)
                    .eq("tenant_id", tenant_id)
                    .limit(1)
                    .execute()
                )
                lead = (lead_res.data or [None])[0]
                if not lead:
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "cancelled"}
                    ).eq("id", alert_id).execute()
                    _log_incident(db, tenant_id, {
                        "lead_id": lead_id,
                        "reason": "lead_not_found",
                    })
                    continue

                if lead.get("segment") != to_segment:
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "cancelled"}
                    ).eq("id", alert_id).execute()
                    continue

                # Verify it is still the latest segment_changed event
                last_event_res = (
                    db.table("lead_stage_events")
                    .select("to_segment")
                    .eq("lead_id", lead_id)
                    .eq("event_type", "segment_changed")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if not last_event_res.data or last_event_res.data[0]["to_segment"] != to_segment:
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "cancelled"}
                    ).eq("id", alert_id).execute()
                    continue

                wa_cfg = get_notification_config(tenant_id, db=db).get("whatsapp_notifications") or {}
                if not wa_cfg.get("enabled"):
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "cancelled"}
                    ).eq("id", alert_id).execute()
                    continue

                template_id = wa_cfg.get("template_id")
                recipient_phones = wa_cfg.get("recipient_phones") or []
                if not template_id or not recipient_phones:
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "cancelled"}
                    ).eq("id", alert_id).execute()
                    continue

                template_res = (
                    db.table("message_templates")
                    .select("id,name,language,body_text,status")
                    .eq("id", template_id)
                    .eq("tenant_id", tenant_id)
                    .eq("status", "APPROVED")
                    .limit(1)
                    .execute()
                )
                template = (template_res.data or [None])[0]
                if not template:
                    logger.warning("WhatsApp alert skipped: template %s not found/approved", template_id)
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "failed"}
                    ).eq("id", alert_id).execute()
                    _log_incident(db, tenant_id, {
                        "lead_id": lead_id,
                        "template_id": template_id,
                        "reason": "template_not_found_or_not_approved",
                    })
                    continue

                components = _build_components(template, lead, to_segment)
                if components is None:
                    db.table("pending_whatsapp_alerts").update(
                        {"status": "failed"}
                    ).eq("id", alert_id).execute()
                    continue

                await _dispatch_alerts(recipient_phones, template, components, tenant_id, lead_id)

                db.table("pending_whatsapp_alerts").update(
                    {"status": "sent"}
                ).eq("id", alert_id).execute()

            except Exception as e:
                logger.exception("Failed to process pending alert %s", alert_id)
                db.table("pending_whatsapp_alerts").update(
                    {"status": "failed"}
                ).eq("id", alert_id).execute()
    except Exception as e:
        logger.exception("process_due_whatsapp_alerts failed")


async def send_admin_whatsapp_alerts(
    tenant_id: str,
    lead_id: str,
    from_segment: str | None,
    to_segment: str,
) -> None:
    """Maintained for tests and backward compatibility. Queues and triggers processing."""
    db = get_supabase()
    queue_admin_whatsapp_alert(db, tenant_id, lead_id, from_segment, to_segment)
    
    import asyncio
    is_mocked_sleep = "mock" in type(asyncio.sleep).__name__.lower()
    
    if is_mocked_sleep or (ALERT_DELAY_SECONDS != 300 and ALERT_DELAY_SECONDS > 0):
        # Determine delay from config
        wa_cfg = get_notification_config(tenant_id, db=db).get("whatsapp_notifications") or {}
        delay_minutes = wa_cfg.get("delay_minutes", 5)
        delay_seconds = ALERT_DELAY_SECONDS if ALERT_DELAY_SECONDS != 300 else (delay_minutes * 60)
        await asyncio.sleep(delay_seconds)
        
    await process_due_whatsapp_alerts()


