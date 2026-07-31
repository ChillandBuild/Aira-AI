import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, Response
from app.db.supabase import get_supabase
from app.config_dynamic import get_setting
from app.services.growth import record_stage_event
from app.services.ai_reply import generate_reply
from app.services.segmentation import new_lead_score_and_segment

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{tenant_id}")
async def telegram_webhook(tenant_id: str, request: Request, background_tasks: BackgroundTasks):
    """Clean, robust webhook handler for Telegram inbound updates."""
    # Verify Telegram secret token header (set via setWebhook)
    expected_secret = get_setting("telegram_webhook_secret", tenant_id=tenant_id)
    if not expected_secret:
        logger.warning(f"Telegram webhook secret not configured for tenant {tenant_id} — re-save the Telegram bot token in Settings to generate it")
        return Response(content="Forbidden", status_code=403)

    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if received_secret != expected_secret:
        logger.warning(f"Telegram webhook secret mismatch for tenant {tenant_id}")
        return Response(content="Forbidden", status_code=403)

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Telegram webhook request JSON: {e}")
        return {"status": "ok", "detail": "invalid_json"}

    # Telegram send updates on messages, edited messages, channel posts, etc. We only handle direct chat messages.
    message = payload.get("message")
    if not message:
        logger.debug("Received non-message Telegram update (e.g. status, callback query, or edit)")
        return {"status": "ok", "detail": "no_message"}

    message_id = message.get("message_id")
    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = (message.get("text") or "").strip()

    tg_user_id = str(from_user.get("id") or "")
    if not tg_user_id:
        logger.warning("Telegram update has no sender user ID")
        return {"status": "ok", "detail": "no_user_id"}

    if not text:
        logger.debug(f"Received non-text message (e.g., photo, document, sticker) from tg_user_id {tg_user_id}")
        return {"status": "ok", "detail": "no_text"}

    first_name = from_user.get("first_name") or ""
    last_name = from_user.get("last_name") or ""
    name = f"{first_name} {last_name}".strip() or f"Telegram User {tg_user_id[:6]}"
    username = from_user.get("username")

    db = get_supabase()

    # Step 1: Check if lead exists by tg_user_id and tenant_id
    try:
        existing = (
            db.table("leads")
            .select("id,score,segment,deleted_at,ai_enabled")
            .eq("tg_user_id", tg_user_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
    except Exception as db_err:
        logger.error(f"Failed to query database for existing Telegram lead {tg_user_id}: {db_err}")
        return {"status": "ok", "detail": "db_error"}

    if existing.data:
        lead_id = existing.data[0]["id"]
        if existing.data[0].get("deleted_at"):
            try:
                db.table("leads").update({
                    "deleted_at": None,
                    "ai_enabled": True,
                    "needs_human_intervention": False,
                }).eq("id", lead_id).execute()
                logger.info(f"Restored soft-deleted Telegram lead {lead_id}")
            except Exception as restore_err:
                logger.error(f"Failed to restore soft-deleted lead {lead_id}: {restore_err}")
    else:
        try:
            initial_score, initial_segment = new_lead_score_and_segment(tenant_id)
            new_lead = db.table("leads").insert({
                "name": name,
                "tg_user_id": tg_user_id,
                "tg_username": username,
                "source": "telegram",
                "score": initial_score,
                "segment": initial_segment,
                "tenant_id": tenant_id,
                "opt_in_source": "telegram",
            }).execute()
            
            if not new_lead.data:
                logger.error(f"Failed to create lead for Telegram user {tg_user_id} - empty result")
                return {"status": "ok", "detail": "lead_create_failed"}
                
            lead_id = new_lead.data[0]["id"]
            record_stage_event(
                lead_id,
                to_segment=initial_segment,
                event_type="created",
                metadata={"source": "telegram"},
                tenant_id=tenant_id,
                db=db
            )
            
            # Auto-assign lead to caller
            try:
                from app.services.assignment import maybe_assign_lead
                maybe_assign_lead(lead_id, tenant_id, initial_segment, "telegram", reason="created")
            except Exception as assign_err:
                logger.warning(f"Auto-assign failed for lead {lead_id}: {assign_err}")
                
        except Exception as insert_err:
            logger.error(f"Failed to insert new Telegram lead for {tg_user_id}: {insert_err}")
            return {"status": "ok", "detail": "lead_create_failed"}

    # Step 2: Avoid processing duplicate updates
    if message_id:
        try:
            already = (
                db.table("messages")
                .select("id")
                .eq("tg_message_id", str(message_id))
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            if already.data:
                logger.debug(f"Received duplicate Telegram message_id: {message_id}, skipping")
                return {"status": "ok", "detail": "duplicate"}
        except Exception as dup_err:
            logger.warning(f"Failed to check duplicate Telegram messages: {dup_err}")

    # Step 3: Insert inbound message
    insert_row = {
        "lead_id": lead_id,
        "direction": "inbound",
        "channel": "telegram",
        "content": text,
        "is_ai_generated": False,
        "tg_message_id": str(message_id) if message_id else None,
        "tenant_id": tenant_id,
    }
    try:
        db.table("messages").insert(insert_row).execute()
    except Exception as msg_err:
        logger.error(f"Failed to insert Telegram message for lead {lead_id}: {msg_err}")
        return {"status": "ok", "detail": "message_insert_failed"}

    # Step 4: Notify assigned caller
    try:
        from app.services.notify import notify_assigned_caller_of_reply
        notify_assigned_caller_of_reply(lead_id, tenant_id, db=db)
    except Exception as notify_err:
        logger.warning(f"Failed to notify caller of Telegram reply: {notify_err}")

    # Step 5: Update conversation state counters
    try:
        from app.services.conversation_state import get_or_create_state
        conv_state = get_or_create_state(lead_id, tenant_id, db)
        new_count = (conv_state.get("message_count") or 0) + 1
        db.table("lead_conversation_state").update({
            "message_count": new_count,
            "last_activity_at": datetime.now(timezone.utc).isoformat(),
        }).eq("lead_id", lead_id).execute()
    except Exception as state_err:
        logger.warning(f"Failed to update Telegram lead conversation state: {state_err}")

    # Step 6: Queue AI Reply in background tasks
    try:
        from app.services.context_builder import build_scorer_context
        context_block = build_scorer_context(lead_id, db)
        background_tasks.add_task(
            generate_reply,
            lead_id=lead_id,
            message=text,
            channel="telegram",
            context_block=context_block,
            tg_user_id=tg_user_id
        )
        logger.info(f"Queued generate_reply task for Telegram lead {lead_id}")
    except Exception as reply_err:
        logger.error(f"Failed to queue generate_reply task for Telegram lead {lead_id}: {reply_err}")

    return {"status": "ok"}
