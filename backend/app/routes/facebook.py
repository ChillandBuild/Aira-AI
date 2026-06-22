import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, Response
from app.db.supabase import get_supabase
from app.config_dynamic import get_setting
from app.services.growth import record_stage_event, get_or_create_campaign
from app.services.ai_reply import generate_reply
from app.services.meta_webhook_verify import verify_meta_signature, resolve_tenant_for_page

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{tenant_id}")
async def verify_facebook_webhook(tenant_id: str, request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verify_token = get_setting("meta_webhook_verify_token", tenant_id=tenant_id)

    if mode == "subscribe" and token == verify_token:
        logger.info(f"Facebook webhook verified successfully for tenant {tenant_id}")
        return Response(content=challenge, media_type="text/plain")

    logger.warning(f"Facebook webhook verification failed for tenant {tenant_id} — token mismatch. received={token}")
    return Response(content="Forbidden", status_code=403)


@router.post("/{tenant_id}")
async def facebook_webhook(tenant_id: str, request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body, signature, tenant_id):
        # Return 200 for echo messages (our own sent messages bounced back by Meta)
        # so Meta stops retrying them.
        try:
            import json as _json
            _payload = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
            _is_echo = any(
                event.get("message", {}).get("is_echo")
                for entry in _payload.get("entry", [])
                for event in entry.get("messaging", [])
            )
            if _is_echo:
                return {"status": "ok", "detail": "echo_ignored"}
        except Exception:
            pass
        logger.warning(f"Facebook webhook signature invalid for tenant {tenant_id}")
        return Response(content="Forbidden", status_code=403)

    try:
        import json as _json
        payload = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        logger.error("Failed to parse Facebook webhook request JSON")
        return {"status": "ok", "detail": "invalid_json"}

    # Meta Messenger payloads have "object": "page"
    if payload.get("object") != "page":
        return {"status": "ok", "detail": "not_page_object"}

    entries = payload.get("entry", [])
    db = get_supabase()

    for entry in entries:
        page_id = entry.get("id", "")
        # Validate that this page_id belongs to the tenant in the URL
        owner_tenant = resolve_tenant_for_page(page_id, "facebook")
        if owner_tenant and owner_tenant != tenant_id:
            logger.warning(
                f"Facebook page_id {page_id} belongs to tenant {owner_tenant}, "
                f"not {tenant_id} (URL) — skipping entry"
            )
            continue
        messaging = entry.get("messaging", [])
        for event in messaging:
            # Ignore echo messages (sent by our page)
            message = event.get("message", {})
            if not message or message.get("is_echo"):
                continue

            message_id = message.get("mid")
            text = (message.get("text") or "").strip()
            sender_id = event.get("sender", {}).get("id")

            # Skip non-text messages (images, stickers, etc.)
            if not sender_id or not text or not message_id:
                continue

            # Meta Ad referral — present when user clicks a Click-to-Messenger ad
            # Same referral object structure as WhatsApp CTWA
            referral = event.get("referral") or message.get("referral") or {}

            # Step 1: Look up or create lead by fb_user_id
            existing = (
                db.table("leads")
                .select("id,score,segment,deleted_at,ai_enabled")
                .eq("fb_user_id", sender_id)
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
                    logger.info(f"Restored soft-deleted Facebook lead {lead_id}")
            else:
                name = f"Facebook User {sender_id[:6]}"
                new_lead = db.table("leads").insert({
                    "name": name,
                    "fb_user_id": sender_id,
                    "fb_page_id": page_id,
                    "source": "facebook",
                    "score": 5,
                    "segment": "C",
                    "tenant_id": tenant_id,
                    "opt_in_source": "facebook",
                }).execute()

                if not new_lead.data:
                    logger.error(f"Failed to create new Facebook lead for sender {sender_id}")
                    continue

                lead_id = new_lead.data[0]["id"]
                record_stage_event(
                    lead_id,
                    to_segment="C",
                    event_type="created",
                    metadata={"source": "facebook"},
                    tenant_id=tenant_id,
                    db=db,
                )
                try:
                    from app.services.assignment import maybe_assign_lead
                    maybe_assign_lead(lead_id, tenant_id, "C", "facebook", reason="created")
                except Exception as e:
                    logger.warning(f"Auto-assign failed for Facebook lead {lead_id}: {e}")

            # ── Meta Ad attribution (Click-to-Messenger) ────────────────────
            # Only runs when referral.source_type == "ad" (user clicked a Messenger ad)
            # Links the lead to an ad_campaign row so it appears in Meta Ad Leads page
            if referral.get("source_type") == "ad":
                try:
                    ad_id    = referral.get("source_id", "")
                    ad_title = referral.get("headline") or referral.get("ad_title") or ad_id
                    campaign = get_or_create_campaign(
                        db,
                        tenant_id=tenant_id,
                        platform="facebook",
                        campaign_name=ad_title,
                        external_campaign_id=ad_id or None,
                    )
                    if campaign:
                        # Only set ad_campaign_id if not already attributed
                        current = (
                            db.table("leads").select("ad_campaign_id")
                            .eq("id", lead_id).limit(1).execute()
                        )
                        if current.data and not current.data[0].get("ad_campaign_id"):
                            db.table("leads").update(
                                {"ad_campaign_id": campaign["id"]}
                            ).eq("id", lead_id).execute()
                            logger.info(
                                f"Facebook Ad referral: lead {lead_id} linked to "
                                f"campaign {campaign['id']} (ad_id={ad_id})"
                            )
                except Exception as fb_ad_err:
                    logger.warning(f"Facebook ad referral tracking failed for lead {lead_id}: {fb_ad_err}")
            # ─────────────────────────────────────────────────────────────────

            # Step 2: Prevent duplicate message insertion
            already = (
                db.table("messages")
                .select("id")
                .eq("fb_message_id", str(message_id))
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            if already.data:
                continue

            # Step 3: Insert inbound message
            db.table("messages").insert({
                "lead_id": lead_id,
                "direction": "inbound",
                "channel": "facebook",
                "content": text,
                "is_ai_generated": False,
                "fb_message_id": str(message_id),
                "tenant_id": tenant_id,
            }).execute()

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
                    continue

            # Step 4: Update conversation activity state
            try:
                from app.services.booking_flow import get_or_create_state
                conv_state = get_or_create_state(lead_id, tenant_id, db)
                new_count = (conv_state.get("message_count") or 0) + 1
                db.table("lead_conversation_state").update({
                    "message_count": new_count,
                    "last_activity_at": datetime.now(timezone.utc).isoformat(),
                }).eq("lead_id", lead_id).execute()
            except Exception as state_err:
                logger.warning(f"Failed to update Facebook lead conversation state: {state_err}")

            # Step 5: Queue AI Auto-Reply
            try:
                from app.services.context_builder import build_scorer_context
                context_block = build_scorer_context(lead_id, db)
                background_tasks.add_task(
                    generate_reply,
                    lead_id=lead_id,
                    message=text,
                    channel="facebook",
                    context_block=context_block,
                    fb_user_id=sender_id,
                )
            except Exception as reply_err:
                logger.error(f"Failed to queue generate_reply for Facebook lead {lead_id}: {reply_err}")

    return {"status": "ok"}
