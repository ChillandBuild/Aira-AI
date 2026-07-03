import logging
import re
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase
from app.services.meta_cloud import send_template_message
from app.services.notification_config import get_notification_config

logger = logging.getLogger(__name__)

_SEGMENT_LABELS = {"A": "Hot", "B": "Warm", "C": "Cold", "D": "Disqualified"}
_COOLDOWN_HOURS = 6


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


async def send_admin_whatsapp_alerts(
    tenant_id: str,
    lead_id: str,
    from_segment: str | None,
    to_segment: str,
) -> None:
    """Fire admin WhatsApp alerts when a lead's segment changes, if configured.

    Fired from a background task with no caller awaiting the result — every
    failure path below must return quietly rather than raise.
    """
    try:
        db = get_supabase()
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
            logger.warning(
                "WhatsApp alert skipped: template %s not found/approved for tenant %s",
                template_id,
                tenant_id,
            )
            _log_incident(db, tenant_id, {
                "lead_id": lead_id,
                "template_id": template_id,
                "reason": "template_not_found_or_not_approved",
            })
            return

        lead_res = (
            db.table("leads")
            .select("id,name,phone,score")
            .eq("id", lead_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        lead = (lead_res.data or [None])[0]
        if not lead:
            logger.warning("WhatsApp alert skipped: lead %s not found for tenant %s", lead_id, tenant_id)
            _log_incident(db, tenant_id, {
                "lead_id": lead_id,
                "reason": "lead_not_found",
            })
            return

        components = _build_components(template, lead, to_segment)
        if components is None:
            return

        await _dispatch_alerts(recipient_phones, template, components, tenant_id, lead_id)
    except Exception as e:
        logger.exception("send_admin_whatsapp_alerts failed for tenant=%s lead=%s", tenant_id, lead_id)
        _log_incident(get_supabase(), tenant_id, {
            "lead_id": lead_id,
            "reason": "unexpected_error",
            "error": str(e)[:500],
        })
