import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Request, Response
from app.db.supabase import get_supabase
from app.config import settings
from app.services.growth import record_stage_event
from app.services.google_ads_attribution import parse_google_ref
from app.services.failover import update_number_quality, handle_quality_red, handle_quality_yellow
from app.services.meta_webhook_verify import verify_meta_signature
from app.services.entitlements import meter
from app.services.segmentation import new_lead_score_and_segment

logger = logging.getLogger(__name__)
router = APIRouter()

# Exact-match opt-out phrases. Matched only on a lead's first reply after a template
# send (see _is_first_in_broadcast) -- a "stop" later in a conversation falls through to
# scoring, which drops the lead to segment D and out of re-engagement targeting.
_STOP_WORDS = frozenset({"stop", "unsubscribe", "ஆர்வம் இல்லை"})


def _is_opt_out(body: str) -> bool:
    normalized = body.lower().strip()
    return normalized in _STOP_WORDS


# Meta delivery error codes that mean the RECIPIENT's number itself is the problem
# (invalid number / not on WhatsApp / blocked the business) — safe to permanently
# exclude that one lead. 131026 matches upload.py's own "undeliverable" mapping.
# Every other failure code (transient throttles like 131049/131048/131056/130472,
# and account-level failures like 131031 "Business Account locked") is NOT
# evidence this specific number is bad — flagging the lead for those would
# wrongly blacklist a healthy contact every time the account itself gets
# rate-limited or restricted.
PERMANENT_UNDELIVERABLE_ERROR_CODES = frozenset({131026})


def _is_recipient_undeliverable_error(code) -> bool:
    try:
        return int(code) in PERMANENT_UNDELIVERABLE_ERROR_CODES
    except (TypeError, ValueError):
        return False


def _get_tenant_id_for_meta_number(phone_number_id: str, db) -> str | None:
    try:
        result = db.table("phone_numbers").select("tenant_id").eq("meta_phone_number_id", phone_number_id).maybe_single().execute()
        return (result.data or {}).get("tenant_id") if result else None
    except Exception:
        return None


async def _handle_opt_out(phone: str, tenant_id: str, db) -> bool:
    try:
        lead = db.table("leads").select("id").eq("phone", phone).eq("tenant_id", tenant_id).maybe_single().execute()
        if not lead or not lead.data:
            return False
        lead_id = lead.data["id"]
        await _record_per_broadcast_opt_out(lead_id, phone, tenant_id, db)
        logger.info(f"Lead {lead_id} hard-opted out from {phone}")
        try:
            from app.services.meta_cloud import send_text_message
            await send_text_message(
                to_number=phone,
                text="நன்றி! உங்கள் விருப்பத்தை மதிக்கிறோம். இனிமேல் நாங்கள் உங்களை தொடர்பு கொள்ள மாட்டோம். 🙏\n\n(Thank you! We respect your preference and will not contact you further.)",
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(f"Opt-out reply failed for {phone}: {e}")
        return True
    except Exception as e:
        logger.error(f"opt-out DB update failed for {phone}: {e}")
        return False


async def _record_per_broadcast_opt_out(lead_id: str, phone: str, tenant_id: str, db) -> None:
    recipient_row: dict | None = None
    tag_id: str | None = None
    try:
        recent = (
            db.table("broadcast_recipients")
            .select("id, broadcast_id, tag_id, created_at")
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .eq("send_status", "sent")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        recipient_row = (recent.data or [None])[0] if recent.data else None
        tag_id = recipient_row.get("tag_id") if recipient_row else None
    except Exception as e:
        logger.error(f"Per-broadcast opt-out: recipient lookup failed for {phone}: {e}")

    if recipient_row:
        try:
            db.table("broadcast_recipients").update({
                "send_status": "opted_out_skip",
                "opted_out_at": datetime.now(timezone.utc).isoformat(),
                "fail_reason": "opted_out",
            }).eq("id", recipient_row["id"]).eq("tenant_id", tenant_id).execute()
        except Exception as e:
            logger.warning(f"Per-broadcast opt-out: opted_out_at update failed (migration 085?): {e}")
            try:
                db.table("broadcast_recipients").update({
                    "send_status": "opted_out_skip",
                    "fail_reason": "opted_out",
                }).eq("id", recipient_row["id"]).eq("tenant_id", tenant_id).execute()
                logger.info(f"Per-broadcast opt-out: fell back to send_status-only update for {phone}")
            except Exception as e2:
                logger.error(f"Per-broadcast opt-out: send_status update also failed for {phone}: {e2}")

    try:
        if tag_id:
            db.table("lead_tag_opt_outs").upsert({
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "tag_id": tag_id,
                "opted_out_at": datetime.now(timezone.utc).isoformat(),
                "source": "inbound",
            }, on_conflict="tenant_id,lead_id,tag_id").execute()
        else:
            tags = db.table("broadcast_tags").select("id").eq("tenant_id", tenant_id).execute()
            for t in (tags.data or []):
                db.table("lead_tag_opt_outs").upsert({
                    "tenant_id": tenant_id,
                    "lead_id": lead_id,
                    "tag_id": t["id"],
                    "opted_out_at": datetime.now(timezone.utc).isoformat(),
                    "source": "inbound",
                }, on_conflict="tenant_id,lead_id,tag_id").execute()
            try:
                db.table("lead_tag_opt_outs").insert({
                    "tenant_id": tenant_id,
                    "lead_id": lead_id,
                    "tag_id": None,
                    "opted_out_at": datetime.now(timezone.utc).isoformat(),
                    "source": "inbound",
                }).execute()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Per-broadcast opt-out: lead_tag_opt_outs insert failed (table missing?): {e}")

    try:
        db.table("leads").update({
            "opted_out": True,
            "opted_out_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
    except Exception as e:
        logger.error(f"Per-broadcast opt-out: leads.opted_out update failed for {phone}: {e}")

    logger.info(f"Per-broadcast opt-out recorded for {phone} (broadcast_recipient={recipient_row is not None}, tag_id={tag_id})")


def _has_prior_inbound_in_broadcast(lead_id: str, broadcast_sent_at: str | None, tenant_id: str, db, exclude_msg_id: str) -> bool:
    if not broadcast_sent_at:
        return False
    try:
        prior = (
            db.table("messages")
            .select("id")
            .eq("lead_id", lead_id)
            .eq("tenant_id", tenant_id)
            .eq("direction", "inbound")
            .gte("created_at", broadcast_sent_at)
            .neq("meta_message_id", exclude_msg_id)
            .limit(1)
            .execute()
        )
        return bool(prior.data)
    except Exception:
        return False


@router.get("")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    from app.config_dynamic import get_setting
    from app.db.supabase import get_supabase as _get_db

    # Check the incoming token against every tenant's configured verify token,
    # then fall back to the global env var. This supports multiple tenants all
    # sharing the single /webhook/whatsapp endpoint.
    if mode == "subscribe" and token:
        # Try each tenant's stored verify token
        try:
            _db = _get_db()
            rows = (
                _db.table("app_settings")
                .select("value")
                .eq("key", "meta_webhook_verify_token")
                .execute()
            )
            for row in (rows.data or []):
                if row.get("value") and row["value"] == token:
                    logger.info("WhatsApp webhook verified (tenant token match)")
                    return Response(content=challenge, media_type="text/plain")
        except Exception as _e:
            logger.warning(f"WhatsApp verify: tenant token lookup failed: {_e}")

        # Fall back to global env var
        global_token = settings.meta_verify_token or get_setting("meta_webhook_verify_token")
        if global_token and token == global_token:
            logger.info("WhatsApp webhook verified (global token)")
            return Response(content=challenge, media_type="text/plain")

    logger.warning(f"Webhook verification failed — token mismatch. received={token}")
    return Response(content="Forbidden", status_code=403)


def _resolve_tenant_from_payload(payload: dict, db) -> str | None:
    """Extract first phone_number_id from payload and look up its tenant."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_id = (
                value.get("metadata", {}).get("phone_number_id")
                or value.get("phone_number_id", "")
            )
            if phone_id:
                tenant = _get_tenant_id_for_meta_number(phone_id, db)
                if tenant:
                    return tenant
    return None


async def _transcribe_whatsapp_audio(media_id: str, tenant_id: str) -> tuple[str, str]:
    from app.services.meta_cloud import download_media_from_meta
    from app.services.gemini_client import gemini_speech_to_text

    audio_bytes, mime_type, _media_url = await download_media_from_meta(media_id, tenant_id=tenant_id)
    transcript = await gemini_speech_to_text(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        tenant_id=tenant_id,
    )
    return transcript, mime_type


async def _process_inbound_message_background(
    lead_id: str,
    tenant_id: str,
    phone: str,
    body: str,
    msg_type: str,
    meta_phone_number_id: str = "",
    meta_message_id: str = "",
    meta_media_id: str = "",
) -> None:
    from app.db.supabase import get_supabase
    db = get_supabase()
    try:
        if msg_type == "audio" and not body and meta_media_id:
            try:
                body, media_mime_type = await _transcribe_whatsapp_audio(meta_media_id, tenant_id)
                meter(db, tenant_id, "ai_speech_to_text")
            except Exception as audio_err:
                logger.error(f"Audio transcription failed for lead {lead_id} media {meta_media_id}: {audio_err}")
                return
            if not body:
                logger.info(f"Audio message {meta_media_id} produced empty transcript for lead {lead_id}")
                return
            db.table("messages").insert({
                "lead_id": lead_id,
                "direction": "inbound",
                "channel": "whatsapp",
                "content": body,
                "is_ai_generated": False,
                "meta_message_id": meta_message_id or meta_media_id,
                "tenant_id": tenant_id,
                "media_url": f"meta:{meta_media_id}",
                "media_type": "audio",
                "media_mime_type": media_mime_type,
            }).execute()
            try:
                from app.services.notify import notify_assigned_caller_of_reply
                notify_assigned_caller_of_reply(lead_id, tenant_id, db=db)
            except Exception:
                pass
            try:
                db.table("leads").update({"outbound_no_reply_count": 0}).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
            except Exception:
                pass

        # Update conversation state counters
        from app.services.conversation_state import get_or_create_state
        from datetime import datetime, timezone
        conv_state = get_or_create_state(lead_id, tenant_id, db)
        new_count = (conv_state.get("message_count") or 0) + 1

        db.table("lead_conversation_state").update({
            "message_count": new_count,
            "last_activity_at": datetime.now(timezone.utc).isoformat(),
        }).eq("lead_id", lead_id).eq("tenant_id", tenant_id).execute()

        # Check if compaction needed (threshold: 10)
        if new_count >= 10:
            try:
                from app.services.conversation_compactor import compact_conversation
                await compact_conversation(lead_id, tenant_id, db, mode="rolling")
            except Exception as compact_err:
                logger.error(f"Compaction failed for lead {lead_id}: {compact_err}")

        # Route text-like inbound content, including transcribed audio, into the reply engine.
        if msg_type in ("text", "button", "interactive", "audio") and body:
            try:
                from app.services.expert_handoff import route_expert_handoff
                consumed = await route_expert_handoff(lead_id=lead_id, tenant_id=tenant_id, phone=phone, body=body, db=db)
                if consumed:
                    return
            except Exception as e:
                logger.error(f"Expert handoff routing failed for lead {lead_id}: {e}")
            try:
                from app.services.context_builder import build_scorer_context
                context_block = build_scorer_context(lead_id, db)
                from app.services.ai_reply import generate_reply
                await generate_reply(
                    lead_id=lead_id,
                    message=body,
                    phone=phone,
                    context_block=context_block,
                    phone_number_id=meta_phone_number_id or None,
                    inbound_media_type=msg_type,
                )
            except Exception as e:
                logger.error(f"Reply routing failed for lead {lead_id}: {e}")
    except Exception as err:
        logger.error(f"Background inbound message processing failed for lead {lead_id}: {err}")


@router.post("")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except Exception:
        payload = {}

    # Verify Meta X-Hub-Signature-256 (fail-closed: missing or invalid signatures are ignored)
    signature = request.headers.get("x-hub-signature-256")
    if not signature:
        logger.warning("WhatsApp webhook: missing signature — dropping")
        return Response(content="OK", status_code=200)
    db_sig = get_supabase()
    tenant_for_sig = _resolve_tenant_from_payload(payload, db_sig)
    if not tenant_for_sig:
        logger.warning("WhatsApp webhook: no tenant for signed payload — dropping")
        return Response(content="OK", status_code=200)
    if not verify_meta_signature(raw_body, signature, tenant_for_sig):
        logger.warning(f"WhatsApp webhook: invalid signature for tenant={tenant_for_sig} — dropping")
        return Response(content="OK", status_code=200)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field")
            value = change.get("value", {})

            if field == "phone_number_quality_update":
                meta_phone_number_id = value.get("phone_number_id")
                quality_rating = value.get("quality_rating", "")
                current_limit = value.get("current_limit")
                messaging_tier = None
                if current_limit and current_limit.startswith("TIER_"):
                    try:
                        messaging_tier = int(current_limit.replace("TIER_", ""))
                    except ValueError:
                        pass
                logger.info(f"phone_number_quality_update: meta_id={meta_phone_number_id} quality={quality_rating} limit={current_limit}")
                row_id = await update_number_quality(meta_phone_number_id, quality_rating, messaging_tier)
                if row_id:
                    if quality_rating == "RED":
                        await handle_quality_red(row_id)
                    elif quality_rating == "YELLOW":
                        await handle_quality_yellow(row_id)

            elif field == "messages":
                meta_phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
                db = get_supabase()
                tenant_id = _get_tenant_id_for_meta_number(meta_phone_number_id, db) if meta_phone_number_id else None
                if not tenant_id:
                    logger.warning(f"No tenant for meta phone_number_id={meta_phone_number_id}, dropping WhatsApp payload")
                    continue
                for msg in value.get("messages", []):
                    msg_type = msg.get("type")
                    msg_id = msg.get("id", "")
                    if msg_type not in ("text", "button", "interactive", "audio"):
                        continue
                    wa_id = msg.get("from", "")
                    phone = f"+{wa_id}" if wa_id and not wa_id.startswith("+") else wa_id
                    media_id = ""
                    if msg_type == "text":
                        body = msg.get("text", {}).get("body", "").strip()
                    elif msg_type == "button":
                        body = msg.get("button", {}).get("text", "").strip()
                    elif msg_type == "interactive":
                        inter = msg.get("interactive", {})
                        body = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "").strip()
                    elif msg_type == "audio":
                        media_id = (msg.get("audio") or {}).get("id", "").strip()
                        body = ""
                    else:
                        body = ""

                    if not phone or (msg_type == "audio" and not media_id) or (msg_type != "audio" and not body):
                        continue

                    logger.info(f"Inbound Meta WhatsApp from {phone}: type={msg_type} body={body!r}")

                    existing = db.table("leads").select("id,score,segment,deleted_at,ai_enabled,whatsapp_undeliverable").eq("phone", phone).eq("tenant_id", tenant_id).limit(1).execute()
                    if existing.data:
                        lead_id = existing.data[0]["id"]
                        if existing.data[0].get("deleted_at"):
                            db.table("leads").update({
                                "deleted_at": None,
                                "ai_enabled": True,
                                "needs_human_intervention": False,
                            }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                            logger.info(f"Restored soft-deleted lead {lead_id} on inbound message")
                        if existing.data[0].get("whatsapp_undeliverable"):
                            try:
                                db.table("leads").update({"whatsapp_undeliverable": False}) \
                                    .eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                                logger.info(f"Cleared whatsapp_undeliverable for lead {lead_id} — inbound message proves reachable")
                            except Exception as e:
                                logger.warning(f"Failed to clear whatsapp_undeliverable for lead {lead_id}: {e}")
                    else:
                        initial_score, initial_segment = new_lead_score_and_segment(tenant_id)
                        new_lead = db.table("leads").insert({
                            "phone": phone,
                            "source": "whatsapp",
                            "score": initial_score,
                            "segment": initial_segment,
                            "tenant_id": tenant_id,
                            "opt_in_source": "whatsapp",
                        }).execute()
                        lead_id = new_lead.data[0]["id"]
                        record_stage_event(lead_id, to_segment=initial_segment, event_type="created", metadata={"source": "whatsapp"}, tenant_id=tenant_id, db=db)
                        try:
                            from app.services.assignment import maybe_assign_lead
                            maybe_assign_lead(lead_id, tenant_id, initial_segment, "whatsapp", reason="created")
                        except Exception as e:
                            logger.warning(f"Auto-assign failed for lead {lead_id}: {e}")

                    # Meta CTWA: count one lead once per ad. Meta's referral ad
                    # id is primary; the pre-filled [AIRA:...] code is fallback.
                    ad_attributed = False
                    # Which creative produced THIS message -- distinct from
                    # leads.attributed_ad_creative_id, which is intentionally not
                    # overwritten on repeat contacts and could point to a stale,
                    # different ad. scoring_engine.py needs the creative tied to
                    # this exact message to compare against its real pre-fill text.
                    attributed_creative_id_for_message = None
                    referral = msg.get("referral")
                    referral_ad_id = (
                        (referral or {}).get("source_id", "")
                        if (referral or {}).get("source_type") == "ad"
                        else ""
                    )
                    try:
                        from app.services.meta_ads_insights_sync import get_current_ads_account_id
                        from app.services.meta_ctwa_attribution import (
                            find_creative_for_message,
                            record_lead_ad_attribution,
                        )

                        account_id = get_current_ads_account_id(db, tenant_id)
                        creative_row = None
                        attribution_method = None
                        if account_id:
                            creative_row, attribution_method = find_creative_for_message(
                                db,
                                tenant_id=tenant_id,
                                meta_ad_account_id=account_id,
                                referral_ad_id=referral_ad_id or None,
                                body=body,
                            )

                        resolved_ad_id = (
                            referral_ad_id
                            if attribution_method == "meta_ad_id"
                            else (creative_row or {}).get("meta_ad_id")
                        )
                        if account_id and attribution_method and resolved_ad_id:
                            creative_id = (creative_row or {}).get("id")
                            attributed_creative_id_for_message = creative_id
                            is_new_ad_lead = record_lead_ad_attribution(
                                db,
                                tenant_id=tenant_id,
                                lead_id=lead_id,
                                meta_ad_account_id=account_id,
                                meta_ad_id=resolved_ad_id,
                                ad_creative_id=creative_id,
                                attribution_method=attribution_method,
                            )
                            ad_attributed = True

                            lead_updates: dict = {}
                            if creative_row and creative_row.get("campaign_id"):
                                lead_updates["ad_campaign_id"] = creative_row["campaign_id"]
                            elif referral_ad_id:
                                # Keep the existing campaign-level fallback for
                                # a brand-new ad that has not synced yet.
                                from app.services.growth import get_or_create_campaign

                                ads_ctx = (referral or {}).get("ads_context_data", {})
                                ad_title = (
                                    ads_ctx.get("ad_title")
                                    or (referral or {}).get("headline", "")
                                    or referral_ad_id
                                )
                                campaign = get_or_create_campaign(
                                    db=db,
                                    tenant_id=tenant_id,
                                    platform="whatsapp",
                                    campaign_name=ad_title,
                                    external_campaign_id=referral_ad_id,
                                )
                                if campaign:
                                    lead_updates["ad_campaign_id"] = campaign["id"]

                            if creative_id:
                                current = (
                                    db.table("leads")
                                    .select("attributed_ad_creative_id")
                                    .eq("id", lead_id)
                                    .eq("tenant_id", tenant_id)
                                    .limit(1)
                                    .execute()
                                )
                                if current.data and not current.data[0].get("attributed_ad_creative_id"):
                                    lead_updates["attributed_ad_creative_id"] = creative_id

                            if lead_updates:
                                (
                                    db.table("leads")
                                    .update(lead_updates)
                                    .eq("id", lead_id)
                                    .eq("tenant_id", tenant_id)
                                    .execute()
                                )
                            logger.info(
                                "CTWA attribution: lead %s -> ad %s via %s (%s)",
                                lead_id,
                                resolved_ad_id,
                                attribution_method,
                                "new" if is_new_ad_lead else "repeat",
                            )
                    except Exception as ctwa_err:
                        logger.warning(f"CTWA attribution failed for lead {lead_id}: {ctwa_err}")

                    # Google Ads: attribute via a [GADS:...] tag in the pre-filled
                    # click-to-chat message. Google can't inject Meta's referral
                    # object, so the tag in the first inbound message is our signal.
                    # Only runs when Meta CTWA didn't already claim this lead.
                    if body and not ad_attributed:
                        google_ref = parse_google_ref(body)
                        if google_ref:
                            try:
                                from app.services.growth import get_or_create_campaign
                                campaign = get_or_create_campaign(
                                    db=db,
                                    tenant_id=tenant_id,
                                    platform="google",
                                    campaign_name=google_ref.campaign,
                                    external_campaign_id=google_ref.external_campaign_id,
                                )
                                if campaign:
                                    # Don't clobber a prior attribution (e.g. repeat
                                    # contact) — only set when currently unattributed.
                                    current = (
                                        db.table("leads").select("ad_campaign_id")
                                        .eq("id", lead_id).eq("tenant_id", tenant_id)
                                        .limit(1).execute()
                                    )
                                    if current.data and not current.data[0].get("ad_campaign_id"):
                                        db.table("leads").update(
                                            {"ad_campaign_id": campaign["id"]}
                                        ).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                                        logger.info(
                                            f"Google Ads referral: lead {lead_id} linked to "
                                            f"campaign {campaign['id']} (tag={google_ref.campaign}, "
                                            f"gclid={google_ref.gclid})"
                                        )
                            except Exception as gads_err:
                                logger.warning(f"Google Ads attribution failed for lead {lead_id}: {gads_err}")

                    already = db.table("messages").select("id").eq("meta_message_id", msg_id).eq("tenant_id", tenant_id).limit(1).execute()
                    if already.data:
                        continue

                    _is_first = (
                        db.table("messages")
                        .select("id")
                        .eq("lead_id", lead_id)
                        .eq("direction", "inbound")
                        .limit(1)
                        .execute()
                    )
                    is_first_message = not bool(_is_first.data)

                    if body and _is_opt_out(body):
                        latest_br = (
                            db.table("broadcast_recipients")
                            .select("broadcast_id, created_at")
                            .eq("tenant_id", tenant_id)
                            .eq("lead_id", lead_id)
                            .eq("send_status", "sent")
                            .order("created_at", desc=True)
                            .limit(1)
                            .execute()
                        )
                        latest = (latest_br.data or [None])[0] if latest_br.data else None
                        broadcast_sent_at = latest.get("created_at") if latest else None
                        is_first_in_broadcast = not _has_prior_inbound_in_broadcast(
                            lead_id, broadcast_sent_at, tenant_id, db, msg_id
                        )
                        if is_first_in_broadcast:
                            await _handle_opt_out(phone, tenant_id, db)
                            continue

                    if msg_type != "audio":
                        insert_row: dict = {
                            "lead_id": lead_id,
                            "direction": "inbound",
                            "channel": "whatsapp",
                            "content": body,
                            "is_ai_generated": False,
                            "meta_message_id": msg_id,
                            "tenant_id": tenant_id,
                            "via_ad_referral": ad_attributed,
                            "attributed_ad_creative_id": attributed_creative_id_for_message,
                        }
                        db.table("messages").insert(insert_row).execute()

                        try:
                            from app.services.notify import notify_assigned_caller_of_reply
                            if lead_id:
                                notify_assigned_caller_of_reply(lead_id, tenant_id, db=db)
                        except Exception:
                            pass

                        # Reset engagement suppression counter on inbound reply
                        if lead_id:
                            try:
                                db.table("leads").update({"outbound_no_reply_count": 0}).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                            except Exception:
                                pass

                    # Delegate state tracking, compaction, and reply to background task to avoid Meta timeout
                    background_tasks.add_task(
                        _process_inbound_message_background,
                        lead_id=lead_id,
                        tenant_id=tenant_id,
                        phone=phone,
                        body=body,
                        msg_type=msg_type,
                        meta_phone_number_id=meta_phone_number_id,
                        meta_message_id=msg_id,
                        meta_media_id=media_id,
                    )

                # Handle message status updates (delivered, read, failed)
                for status_update in value.get("statuses", []):
                    message_id = status_update.get("id")
                    status = status_update.get("status")

                    if message_id and status in ("delivered", "read", "failed"):
                        try:
                            update_payload: dict = {"delivery_status": status}
                            err_code = None
                            # Capture Meta error code + title on failed status — surfaced in failed CSV
                            if status == "failed":
                                errs = status_update.get("errors") or []
                                if errs:
                                    first = errs[0] or {}
                                    err_code = first.get("code")
                                    err_title = first.get("title") or first.get("message")
                                    if err_code is not None:
                                        update_payload["delivery_error_code"] = err_code
                                    if err_title:
                                        update_payload["delivery_error_title"] = err_title[:200]
                                    logger.warning(
                                        f"Meta delivery failure msg={message_id} code={err_code} title={err_title!r}"
                                    )
                            try:
                                updated = db.table("messages") \
                                    .update(update_payload) \
                                    .eq("meta_message_id", message_id) \
                                    .eq("tenant_id", tenant_id) \
                                    .execute()
                            except Exception as col_err:
                                # Migration 061 may not be applied yet — retry without error columns
                                if "delivery_error_code" in str(col_err) or "delivery_error_title" in str(col_err):
                                    logger.warning(f"Migration 061 not applied — saving status only: {col_err}")
                                    updated = db.table("messages") \
                                        .update({"delivery_status": status}) \
                                        .eq("meta_message_id", message_id) \
                                        .eq("tenant_id", tenant_id) \
                                        .execute()
                                else:
                                    raise
                            logger.info(f"Message {message_id} status updated to {status}")
                            # Mark lead as undeliverable so it's hidden from active views
                            # Also flip broadcast_recipients row so failed leads are excluded
                            # from Segment CSVs, scoring, and all dashboard analytics.
                            # Only flag the LEAD for error codes that specifically mean this
                            # recipient's number is the problem (e.g. 131026 wrong number).
                            # Everything else — transient throttles AND account-level failures
                            # like 131031 "Business Account locked" — is not evidence this
                            # number is bad, and must not permanently blacklist the lead.
                            if status == "failed" and updated.data:
                                failed_lead_id = updated.data[0].get("lead_id")
                                if failed_lead_id:
                                    if _is_recipient_undeliverable_error(err_code):
                                        db.table("leads").update({"whatsapp_undeliverable": True}) \
                                            .eq("id", failed_lead_id).eq("tenant_id", tenant_id).execute()
                                    else:
                                        logger.info(f"Delivery error {err_code} for lead {failed_lead_id} is not recipient-specific — not flagging undeliverable")
                                    try:
                                        db.table("broadcast_recipients") \
                                            .update({"send_status": "delivery_failed"}) \
                                            .eq("meta_message_id", message_id) \
                                            .eq("tenant_id", tenant_id) \
                                            .execute()
                                    except Exception as _br_err:
                                        logger.warning(f"broadcast_recipients delivery_failed update failed: {_br_err}")
                            # Lead proved reachable again — clear any stale undeliverable flag.
                            if status in ("delivered", "read") and updated.data:
                                reachable_lead_id = updated.data[0].get("lead_id")
                                if reachable_lead_id:
                                    try:
                                        db.table("leads").update({"whatsapp_undeliverable": False}) \
                                            .eq("id", reachable_lead_id).eq("tenant_id", tenant_id) \
                                            .eq("whatsapp_undeliverable", True).execute()
                                    except Exception as _wu_err:
                                        logger.warning(f"Failed to clear whatsapp_undeliverable for lead {reachable_lead_id}: {_wu_err}")
                            # Bot Flow Builder per-node analytics: bump node delivered_count once
                            if status == "delivered" and updated.data:
                                step_id = updated.data[0].get("automation_step_id")
                                if step_id:
                                    try:
                                        db.rpc("bump_automation_step_counter", {
                                            "p_step_id": step_id,
                                            "p_field": "delivered_count",
                                            "p_delta": 1,
                                        }).execute()
                                    except Exception as e:
                                        logger.warning(f"Failed to bump delivered_count for step {step_id}: {e}")
                        except Exception as e:
                            logger.error(f"Failed to update message {message_id} status to {status}: {e}")

    return {"status": "ok"}
