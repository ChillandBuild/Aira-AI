import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Response
from app.db.supabase import get_supabase
from app.config_dynamic import get_setting
from app.services.growth import record_stage_event
from app.services.meta_ctwa_attribution import attribute_chat_to_ad, parse_ad_referral
from app.services.ai_reply import generate_reply
from app.services.meta_webhook_verify import (
    verify_meta_signature,
    resolve_tenant_for_page,
    resolve_tenants_from_payload,
    matches_any_tenant_verify_token,
)
from app.services.segmentation import new_lead_score_and_segment

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_or_create_instagram_lead(db, tenant_id: str, sender_id: str) -> str | None:
    """The tenant's lead for this Instagram user, created (and auto-assigned) on first
    contact; a soft-deleted lead is restored. None only if the insert failed."""
    existing = (
        db.table("leads")
        .select("id,score,segment,deleted_at,ai_enabled")
        .eq("ig_user_id", sender_id)
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
            logger.info(f"Restored soft-deleted Instagram lead {lead_id}")
        return lead_id

    name = f"Instagram User {sender_id[:6]}"
    initial_score, initial_segment = new_lead_score_and_segment(tenant_id)
    new_lead = db.table("leads").insert({
        "name": name,
        "ig_user_id": sender_id,
        "source": "instagram",
        "score": initial_score,
        "segment": initial_segment,
        "tenant_id": tenant_id,
        "opt_in_source": "instagram",
    }).execute()
    if not new_lead.data:
        logger.error(f"Failed to create new Instagram lead for sender {sender_id}")
        return None

    lead_id = new_lead.data[0]["id"]
    record_stage_event(
        lead_id,
        to_segment=initial_segment,
        event_type="created",
        metadata={"source": "instagram"},
        tenant_id=tenant_id,
        db=db
    )
    try:
        from app.services.assignment import maybe_assign_lead
        maybe_assign_lead(lead_id, tenant_id, initial_segment, "instagram", reason="created")
    except Exception as e:
        logger.warning(f"Auto-assign failed for Instagram lead {lead_id}: {e}")
    return lead_id


@router.get("/{tenant_id}")
async def verify_instagram_webhook(tenant_id: str, request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verify_token = get_setting("meta_webhook_verify_token", tenant_id=tenant_id)

    if mode == "subscribe" and token == verify_token:
        logger.info(f"Instagram webhook verified successfully for tenant {tenant_id}")
        return Response(content=challenge, media_type="text/plain")

    logger.warning(f"Instagram webhook verification failed for tenant {tenant_id} — token mismatch. received={token}")
    return Response(content="Forbidden", status_code=403)


@router.post("/{tenant_id}")
async def instagram_webhook(tenant_id: str, request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body, signature, tenant_id, secret_key="instagram_app_secret"):
        # Check if this is an echo of our own outbound message — Meta sends these back
        # signed by a different app. Return 200 so Meta stops retrying.
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
        logger.warning(f"Instagram webhook signature invalid for tenant {tenant_id}")
        return Response(content="Forbidden", status_code=403)

    try:
        import json as _json
        payload = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        logger.error("Failed to parse Instagram webhook request JSON")
        return {"status": "ok", "detail": "invalid_json"}

    # Meta webhook event payloads have "object": "instagram" and "entry" list
    if payload.get("object") != "instagram":
        # Diagnostic: every drop below this point used to be silent, so a verified
        # webhook that produced no lead was indistinguishable from one that worked.
        logger.info(
            f"Instagram webhook ignored for tenant {tenant_id}: "
            f"object={payload.get('object')!r} keys={sorted(payload.keys())}"
        )
        return {"status": "ok", "detail": "not_instagram_object"}

    entries = payload.get("entry", [])
    db = get_supabase()

    for entry in entries:
        ig_account_id = entry.get("id", "")
        owner_tenant = resolve_tenant_for_page(ig_account_id, "instagram")
        if owner_tenant and owner_tenant != tenant_id:
            logger.warning(
                f"Instagram account {ig_account_id} belongs to tenant {owner_tenant}, "
                f"not {tenant_id} (URL) — skipping entry"
            )
            continue

        messaging = entry.get("messaging", [])
        if not messaging:
            # Instagram-Login delivers some field types under entry[].changes[]
            # rather than entry[].messaging[]; those fall through here silently.
            logger.info(
                f"Instagram entry {ig_account_id} for tenant {tenant_id} has no "
                f"messaging events: keys={sorted(entry.keys())}"
            )
            continue

        for event in messaging:
            # We ignore echo messages (messages sent by our own application/page)
            message = event.get("message") or {}
            sender_id = event.get("sender", {}).get("id")
            # Meta Ad referral: {source: "ADS", type: "OPEN_THREAD", ad_id, ...}
            # on the message when a Click-to-Instagram-Direct ad opens the chat.
            referral = event.get("referral") or message.get("referral") or {}
            ad_id = parse_ad_referral(referral)

            if not message or message.get("is_echo"):
                if not message and ad_id and sender_id:
                    # Standalone referral event carrying an ad id: credit the ad.
                    lead_id = _get_or_create_instagram_lead(db, tenant_id, sender_id)
                    if lead_id:
                        attribute_chat_to_ad(
                            db, tenant_id=tenant_id, lead_id=lead_id, referral=referral,
                            channel="instagram", platform="instagram",
                        )
                    continue
                logger.info(
                    f"Instagram event skipped for tenant {tenant_id}: "
                    f"has_message={bool(message)} is_echo={bool(message.get('is_echo'))} "
                    f"event_keys={sorted(event.keys())}"
                )
                continue

            message_id = message.get("mid")
            text = (message.get("text") or "").strip()

            if not sender_id or not text or not message_id:
                # Meta's documented ad-click message can carry only the referral,
                # no text. Still credit the ad; there is nothing to store or reply to.
                if ad_id and sender_id:
                    lead_id = _get_or_create_instagram_lead(db, tenant_id, sender_id)
                    if lead_id:
                        attribute_chat_to_ad(
                            db, tenant_id=tenant_id, lead_id=lead_id, referral=referral,
                            channel="instagram", platform="instagram",
                        )
                # Attachments, stickers and reactions land here — no text to reply to.
                logger.info(
                    f"Instagram message skipped for tenant {tenant_id}: "
                    f"has_sender={bool(sender_id)} has_text={bool(text)} "
                    f"has_mid={bool(message_id)} message_keys={sorted(message.keys())}"
                )
                continue

            # Step 1: Look up or create the lead by ig_user_id
            lead_id = _get_or_create_instagram_lead(db, tenant_id, sender_id)
            if not lead_id:
                continue

            # Meta Ad attribution (Click-to-Instagram-Direct)
            if ad_id:
                attribute_chat_to_ad(
                    db, tenant_id=tenant_id, lead_id=lead_id, referral=referral,
                    channel="instagram", platform="instagram",
                )

            # Step 2: Prevent duplicate message insertion
            already = (
                db.table("messages")
                .select("id")
                .eq("meta_message_id", str(message_id))
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            if already.data:
                continue

            # Step 3: Insert inbound message
            insert_row = {
                "lead_id": lead_id,
                "direction": "inbound",
                "channel": "instagram",
                "content": text,
                "is_ai_generated": False,
                "meta_message_id": str(message_id),
                "tenant_id": tenant_id,
                # Stamp the ad flag on the message, not just the lead: the
                # lead's ad_campaign_id is deliberately left alone on repeat
                # contacts, so it can't tell us "this particular message came
                # from an ad". /analytics/overview reads this column to count
                # returning leads an ad brought back.
                "via_ad_referral": bool(ad_id),
            }
            db.table("messages").insert(insert_row).execute()
            logger.info(f"Instagram message stored for tenant {tenant_id}: lead={lead_id} mid={message_id}")

            try:
                from app.services.notify import notify_assigned_caller_of_reply
                if lead_id:
                    notify_assigned_caller_of_reply(lead_id, tenant_id, db=db)
            except Exception:
                pass

            # Step 4: Update conversation activity state
            try:
                from app.services.conversation_state import get_or_create_state
                conv_state = get_or_create_state(lead_id, tenant_id, db)
                new_count = (conv_state.get("message_count") or 0) + 1
                db.table("lead_conversation_state").update({
                    "message_count": new_count,
                    "last_activity_at": datetime.now(timezone.utc).isoformat(),
                }).eq("lead_id", lead_id).execute()
            except Exception as state_err:
                logger.warning(f"Failed to update Instagram lead conversation state: {state_err}")

            # Step 5: Queue AI Auto-Reply
            try:
                from app.services.context_builder import build_scorer_context
                context_block = build_scorer_context(lead_id, db)
                background_tasks.add_task(
                    generate_reply,
                    lead_id=lead_id,
                    message=text,
                    channel="instagram",
                    context_block=context_block,
                    ig_user_id=sender_id
                )
            except Exception as reply_err:
                logger.error(f"Failed to queue generate_reply task for Instagram lead {lead_id}: {reply_err}")

    return {"status": "ok"}


# ── Shared, tenant-agnostic endpoint ────────────────────────────────────────
# Meta allows exactly one callback URL per app per webhook object, so the
# /{tenant_id} routes above can only ever serve a single tenant per Meta app.
# These routes take no tenant and derive it from entry[].id instead — the same
# approach /webhook/whatsapp has always used. The per-tenant routes stay for the
# URLs already configured in Meta.

@router.get("")
async def verify_instagram_webhook_shared(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and matches_any_tenant_verify_token(token):
        logger.info("Instagram webhook verified on the shared endpoint")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Instagram shared webhook verification failed — token matched no tenant")
    return Response(content="Forbidden", status_code=403)


@router.post("")
async def instagram_webhook_shared(request: Request, background_tasks: BackgroundTasks):
    """Route each entry to its owning tenant, then reuse the per-tenant handler.

    The signature is checked inside that handler, against the resolved tenant's
    secret — resolving from an unverified body only picks which secret to verify
    against, it never grants trust. Entries owned by another tenant are skipped by
    the handler's own ownership check, so calling it once per distinct tenant
    processes every entry exactly once.
    """
    raw_body = await request.body()
    try:
        import json as _json
        payload = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        logger.error("Failed to parse Instagram shared webhook request JSON")
        return {"status": "ok", "detail": "invalid_json"}

    tenants = resolve_tenants_from_payload(payload, "instagram")
    if not tenants:
        entry_ids = [e.get("id") for e in payload.get("entry", []) or []]
        logger.warning(
            f"Instagram shared webhook: no tenant owns entries {entry_ids} — "
            f"is instagram_page_id set to the IG business account id for this account?"
        )
        return {"status": "ok", "detail": "no_tenant_for_entries"}

    for tenant_id in tenants:
        await instagram_webhook(tenant_id, request, background_tasks)
    return {"status": "ok", "tenants": len(tenants)}
