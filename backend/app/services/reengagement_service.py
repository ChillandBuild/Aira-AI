import logging
from datetime import datetime, timezone, timedelta
from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.services.ai_reply import send_whatsapp
from app.services.meta_cloud import send_template_message

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _classify_source(lead: dict) -> str:
    """Map a lead to an acquisition-source bucket (ad referral wins over channel)."""
    if lead.get("ad_campaign_id"):
        return "meta_ads"
    src = (lead.get("source") or "").lower()
    if src == "upload":
        return "csv"
    if src in ("telegram", "instagram", "facebook"):
        return src
    return "organic"


def _lead_matches_sources(lead: dict, target_sources) -> bool:
    """NULL/empty target_sources = all sources."""
    if not target_sources:
        return True
    return _classify_source(lead) in target_sources


async def process_due_reengagements() -> int:
    """Query and process all pending re-engagement steps for all tenants."""
    db = get_supabase()
    
    # 1. Fetch all re-engagement steps
    steps_res = db.table("reengagement_steps").select("*").execute()
    steps = steps_res.data or []
    if not steps:
        return 0

    sent_count = 0
    now = utcnow()

    for step in steps:
        step_id = step["id"]
        tenant_id = step["tenant_id"]
        delay_hours = step["delay_hours"]
        target_segments = step["target_segments"] or []
        target_sources = step.get("target_sources") or []
        message_type = step["message_type"]
        
        if step["type"] == "broadcast":
            # A. Broadcast-specific re-engagement
            broadcast_id = step["broadcast_id"]
            if not broadcast_id:
                continue

            # Fetch recipients who received this broadcast
            recipients_res = (
                db.table("broadcast_recipients")
                .select("lead_id, created_at, phone, name")
                .eq("broadcast_id", broadcast_id)
                .eq("tenant_id", tenant_id)
                .eq("send_status", "sent")
                .execute()
            )
            recipients = recipients_res.data or []
            if not recipients:
                continue

            for rec in recipients:
                lead_id = rec["lead_id"]
                sent_at_str = rec["created_at"]
                
                try:
                    sent_at = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
                except Exception:
                    continue

                # Check if delay time has elapsed
                if now - sent_at < timedelta(hours=delay_hours):
                    continue

                # Check if already processed
                log_exists = (
                    db.table("reengagement_logs")
                    .select("id")
                    .eq("lead_id", lead_id)
                    .eq("step_id", step_id)
                    .limit(1)
                    .execute()
                )
                if log_exists.data:
                    continue

                # Fetch lead details to check current segment and last_inbound_at
                lead_res = (
                    db.table("leads")
                    .select("id, name, phone, segment, last_inbound_at, source, ad_campaign_id, whatsapp_undeliverable, opted_out")
                    .eq("id", lead_id)
                    .eq("tenant_id", tenant_id)
                    .maybe_single()
                    .execute()
                )
                lead = lead_res.data if lead_res else None
                if not lead or lead.get("segment") not in target_segments:
                    continue
                if not _lead_matches_sources(lead, target_sources):
                    continue

                # Process sending
                success = await _send_reengagement(db, tenant_id, lead, step)
                if success:
                    sent_count += 1

        elif step["type"] == "inbound":
            # B. Inbound lead-specific re-engagement (relative to last_inbound_at)
            # Find leads with last_inbound_at
            leads_res = (
                db.table("leads")
                .select("id, name, phone, segment, last_inbound_at, source, ad_campaign_id, whatsapp_undeliverable, opted_out")
                .eq("tenant_id", tenant_id)
                .not_.is_("last_inbound_at", "null")
                .execute()
            )
            leads = leads_res.data or []
            
            for lead in leads:
                lead_id = lead["id"]
                last_inbound_str = lead["last_inbound_at"]
                
                try:
                    last_inbound = datetime.fromisoformat(last_inbound_str.replace("Z", "+00:00"))
                except Exception:
                    continue

                # Check if delay time has elapsed
                if now - last_inbound < timedelta(hours=delay_hours):
                    continue

                # Check if already processed for this step
                log_exists = (
                    db.table("reengagement_logs")
                    .select("id")
                    .eq("lead_id", lead_id)
                    .eq("step_id", step_id)
                    .limit(1)
                    .execute()
                )
                if log_exists.data:
                    continue

                if lead.get("segment") not in target_segments:
                    continue
                if not _lead_matches_sources(lead, target_sources):
                    continue

                # Process sending
                success = await _send_reengagement(db, tenant_id, lead, step)
                if success:
                    sent_count += 1

    return sent_count


async def _send_step_template(
    db,
    tenant_id: str,
    lead: dict,
    step: dict,
    *,
    template_name: str,
    template_variables: list[str] | None,
    log_status: str,
) -> bool:
    """Send a template message for a step and write message + reengagement logs."""
    lead_id = lead["id"]
    phone = lead["phone"]
    step_id = step["id"]
    if not template_name:
        raise ValueError("Template name not configured")

    parameters = []
    for var_name in (template_variables or []):
        if var_name == "name":
            val = lead.get("name") or "there"
        elif var_name == "phone":
            val = lead.get("phone") or ""
        else:
            val = ""
        parameters.append({"type": "text", "text": str(val)})

    components = [{"type": "body", "parameters": parameters}] if parameters else []

    res = await send_template_message(
        to_number=phone,
        template_name=template_name,
        components=components,
        tenant_id=tenant_id,
    )
    sid = res.get("messages", [{}])[0].get("id") if res else None

    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": f"[Template Broadcast: {template_name}]",
        "is_ai_generated": True,
        "meta_message_id": sid or "",
        "reply_source": "reengagement",
    }).execute()

    db.table("reengagement_logs").insert({
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "step_id": step_id,
        "status": log_status,
    }).execute()
    logger.info(f"Re-engagement step {step_id} ({log_status}) sent to lead {lead_id}")
    return True


async def _send_reengagement(db, tenant_id: str, lead: dict, step: dict) -> bool:
    """Send the re-engagement message to a single lead and write a log entry.

    ai_auto_reply_enabled is the single master switch for every automated AI-authored
    outbound message, not just inbound replies -- when a client turns it off, re-engagement
    must stop too (no separate reengagement_enabled flag; that key existed but was never
    actually wired to any send path, so it was deleted rather than kept as dead config).
    No log row is written on this skip, matching the opted_out/undeliverable checks below --
    re-engagement should resume for this lead+step once the tenant re-enables, not be
    permanently marked processed."""
    lead_id = lead["id"]
    phone = lead["phone"]
    step_id = step["id"]
    if get_setting("ai_auto_reply_enabled", fallback="true", tenant_id=tenant_id) == "false":
        logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} (ai_auto_reply disabled for tenant {tenant_id})")
        return False
    message_type = step["message_type"]

    # If lead doesn't have a phone number, we can't send WhatsApp
    if not phone:
        return False

    # Never re-engage a lead WhatsApp can't deliver to. Meta marks these via the delivery
    # webhook (delivery_status=failed → leads.whatsapp_undeliverable=True). The original
    # template never reached them, so a follow-up can't either — skip silently, no log.
    if lead.get("whatsapp_undeliverable"):
        logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} (whatsapp_undeliverable)")
        return False

    # Never re-engage a lead who has opted out. Messaging an opted-out lead is a
    # compliance risk regardless of channel — skip silently, no log.
    if lead.get("opted_out"):
        logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} (opted_out)")
        return False

    # Check 24-hour WhatsApp session window for freeform messages
    is_window_active = False
    last_inbound_str = lead.get("last_inbound_at")
    if last_inbound_str:
        try:
            last_inbound = datetime.fromisoformat(last_inbound_str.replace("Z", "+00:00"))
            is_window_active = (utcnow() - last_inbound) <= timedelta(hours=24)
        except Exception:
            pass

    # Exception for non-whatsapp channels (e.g. Telegram where no 24h window applies)
    if lead.get("source") in ("telegram", "instagram", "facebook"):
        is_window_active = True

    if message_type == "freeform":
        if not is_window_active:
            fallback_name = step.get("fallback_template_name")
            if fallback_name:
                try:
                    return await _send_step_template(
                        db, tenant_id, lead, step,
                        template_name=fallback_name,
                        template_variables=step.get("fallback_template_variables"),
                        log_status="sent_fallback",
                    )
                except Exception as e:
                    logger.error(f"Re-engagement fallback template {step_id} failed for lead {lead_id}: {e}")
                    db.table("reengagement_logs").insert({
                        "tenant_id": tenant_id,
                        "lead_id": lead_id,
                        "step_id": step_id,
                        "status": "failed",
                    }).execute()
                    return False

            db.table("reengagement_logs").insert({
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "step_id": step_id,
                "status": "skipped_window",
            }).execute()
            logger.info(f"Re-engagement step {step_id} skipped for lead {lead_id} (outside 24h window, no fallback)")
            return False

        try:
            content = step["message_content"] or ""
            sid = await send_whatsapp(phone, content, tenant_id=tenant_id)
            if not sid:
                raise RuntimeError("Channel send returned empty SID")

            db.table("messages").insert({
                "lead_id": lead_id,
                "tenant_id": tenant_id,
                "direction": "outbound",
                "channel": "whatsapp",
                "content": content,
                "is_ai_generated": True,
                "meta_message_id": sid,
                "reply_source": "reengagement",
            }).execute()

            db.table("reengagement_logs").insert({
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "step_id": step_id,
                "status": "sent",
            }).execute()
            logger.info(f"Re-engagement step {step_id} (freeform) sent to lead {lead_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send re-engagement freeform step {step_id} to lead {lead_id}: {e}")
            db.table("reengagement_logs").insert({
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "step_id": step_id,
                "status": "failed",
            }).execute()
            return False

    elif message_type == "template":
        try:
            return await _send_step_template(
                db, tenant_id, lead, step,
                template_name=step.get("template_name"),
                template_variables=step.get("template_variables"),
                log_status="sent",
            )
        except Exception as e:
            logger.error(f"Failed to send re-engagement template step {step_id} to lead {lead_id}: {e}")
            db.table("reengagement_logs").insert({
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "step_id": step_id,
                "status": "failed",
            }).execute()
            return False

    return False
