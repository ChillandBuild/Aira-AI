import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Response
from app.db.supabase import get_supabase
from app.config_dynamic import get_setting
from app.services.growth import record_stage_event
from app.services.ai_reply import generate_reply

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{tenant_id}")
async def telegram_webhook(tenant_id: str, request: Request, background_tasks: BackgroundTasks):
    # Verify Telegram secret token header (set via setWebhook) before doing anything
    expected_secret = get_setting("telegram_webhook_secret", tenant_id=tenant_id)
    if expected_secret:
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if received_secret != expected_secret:
            logger.warning(f"Telegram webhook secret mismatch for tenant {tenant_id}")
            return Response(content="Forbidden", status_code=403)
    else:
        logger.warning(f"Telegram webhook secret not configured for tenant {tenant_id} — rejecting")
        return Response(content="Forbidden", status_code=403)

    try:
        payload = await request.json()
    except Exception:
        logger.error("Failed to parse Telegram webhook request JSON")
        return {"status": "ok", "detail": "invalid_json"}

    # We only handle messages
    message = payload.get("message")
    if not message:
        return {"status": "ok", "detail": "no_message"}

    # Message details
    message_id = message.get("message_id")
    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = (message.get("text") or "").strip()

    tg_user_id = str(from_user.get("id") or "")
    if not tg_user_id:
        return {"status": "ok", "detail": "no_user_id"}

    # We only handle text messages for now
    if not text:
        return {"status": "ok", "detail": "no_text"}

    first_name = from_user.get("first_name") or ""
    last_name = from_user.get("last_name") or ""
    name = f"{first_name} {last_name}".strip() or f"Telegram User {tg_user_id[:6]}"
    username = from_user.get("username")

    db = get_supabase()

    # Step 1: Check if lead exists by tg_user_id and tenant_id
    existing = (
        db.table("leads")
        .select("id,score,segment,deleted_at,ai_enabled")
        .eq("tg_user_id", tg_user_id)
        .eq("tenant_id", tenant_id)
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
            }).eq("id", lead_id).execute()
            logger.info(f"Restored soft-deleted Telegram lead {lead_id}")
    else:
        new_lead = db.table("leads").insert({
            "name": name,
            "tg_user_id": tg_user_id,
            "tg_username": username,
            "source": "telegram",
            "score": 5,
            "segment": "C",
            "tenant_id": tenant_id,
            "opt_in_source": "telegram",
        }).execute()
        
        if not new_lead.data:
            logger.error(f"Failed to create lead for Telegram user {tg_user_id}")
            return {"status": "ok", "detail": "lead_create_failed"}
            
        lead_id = new_lead.data[0]["id"]
        record_stage_event(
            lead_id,
            to_segment="C",
            event_type="created",
            metadata={"source": "telegram"},
            tenant_id=tenant_id,
            db=db
        )
        try:
            from app.services.assignment import maybe_assign_lead
            maybe_assign_lead(lead_id, tenant_id, "C", "telegram", reason="created")
        except Exception as e:
            logger.warning(f"Auto-assign failed for lead {lead_id}: {e}")

    # Step 2: Avoid processing duplicate updates
    already = (
        db.table("messages")
        .select("id")
        .eq("tg_message_id", str(message_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if already.data:
        return {"status": "ok", "detail": "duplicate"}

    # Step 3: Insert inbound message
    _is_first = (
        db.table("messages").select("id").eq("lead_id", lead_id)
        .eq("direction", "inbound").limit(1).execute()
    )
    is_first_message = not bool(_is_first.data)
    insert_row = {
        "lead_id": lead_id,
        "direction": "inbound",
        "channel": "telegram",
        "content": text,
        "is_ai_generated": False,
        "tg_message_id": str(message_id),
        "tenant_id": tenant_id,
    }
    db.table("messages").insert(insert_row).execute()

    try:
        from app.services.notify import notify_assigned_caller_of_reply
        if lead_id:
            notify_assigned_caller_of_reply(lead_id, tenant_id, db=db)
    except Exception:
        pass

    # Booking state machine: takes priority over AI.
    if text:
        from app.services.booking_flow import route_booking_intent
        phone = (db.table("leads").select("phone").eq("id", lead_id).maybe_single().execute().data or {}).get("phone", "")
        if phone and await route_booking_intent(lead_id, tenant_id, phone, text, db):
            return {"status": "ok"}

    # Step 4: Update conversation state counters
    try:
        from app.services.booking_flow import get_or_create_state
        conv_state = get_or_create_state(lead_id, tenant_id, db)
        new_count = (conv_state.get("message_count") or 0) + 1
        db.table("lead_conversation_state").update({
            "message_count": new_count,
            "last_activity_at": datetime.now(timezone.utc).isoformat(),
        }).eq("lead_id", lead_id).execute()
    except Exception as state_err:
        logger.warning(f"Failed to update Telegram lead conversation state: {state_err}")

    # Step 5: Queue AI Reply in background tasks
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
    except Exception as reply_err:
        logger.error(f"Failed to queue generate_reply task for Telegram lead {lead_id}: {reply_err}")

    return {"status": "ok"}
