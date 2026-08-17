"""Generic, per-tenant paid expert handoff: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging
import re
import uuid

import httpx

from app.services.gemini_client import gemini_chat_completion_json
from app.services.notify import notify_pool
from app.services.payment_razorpay import create_payment_link

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "enabled": False,
    "trigger_description": "",
    "offer_message": "",
    "fields": [],  # list of {"key": str, "label": str, "type": "text"|"date"|"choice", "options": list[str]?}
    "amount_paise": 0,
}


def get_expert_handoff_config(tenant_id: str, db=None) -> dict:
    """Return expert_handoff_config from app_settings, merged with defaults."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "expert_handoff_config")
        .maybe_single()
        .execute()
    )
    if row and row.data:
        try:
            stored = json.loads(row.data["value"])
            return {**_DEFAULT_CONFIG, **stored}
        except Exception:
            logger.warning(f"Failed to parse expert_handoff_config for tenant {tenant_id}")
    return dict(_DEFAULT_CONFIG)


def save_expert_handoff_config(tenant_id: str, config: dict, db=None) -> None:
    """Persist expert_handoff_config to app_settings."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "expert_handoff_config",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


_DETECTION_SYSTEM_PROMPT = """You are a classifier. Given a business's description of what
kind of message should trigger a paid human-expert handoff, and one incoming customer
message, decide if THIS message matches that description.

Respond with JSON only: {"matches": true} or {"matches": false}. No other text."""


async def detect_expert_handoff_intent(message: str, trigger_description: str, tenant_id: str) -> bool:
    """Fail closed: any error, empty trigger_description, or unparseable response -> False.
    A missed offer is recoverable (the lead can ask again); a wrongly-triggered paid
    flow from a classifier hiccup is not."""
    if not trigger_description:
        return False
    user_prompt = f"Trigger description: {trigger_description}\n\nCustomer message: {message}"
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_DETECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=50,
            tenant_id=tenant_id,
            purpose="expert_handoff_detection",
        )
        return bool(data.get("matches") is True)
    except Exception as e:
        logger.warning(f"Expert handoff detection failed, defaulting to no-match: {e}")
        return False


def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]:
    return [f["label"] for f in fields if not collected_data.get(f["key"])]


_EXTRACTION_SYSTEM_PROMPT = """You extract structured field values from one customer chat
message. You are given a list of fields the business needs and the values already
collected from earlier turns. Read the new message and return ONLY the fields you can
confidently find IN THIS MESSAGE, as flat JSON: {"field_key": "value", ...}.

Rules:
- Only include a key if this message actually contains that value.
- Never guess or invent a value that isn't stated.
- Do not repeat values that weren't in this message, even if already collected.
- If this message contains none of the requested fields, return {}.
- JSON only, no other text."""


async def extract_fields(message: str, fields: list[dict], collected_data: dict, tenant_id: str) -> dict:
    """Never drops already-collected data: the LLM only ever contributes additions
    for THIS message, which are merged on top of (never replacing) collected_data."""
    field_list = "\n".join(f"- {f['key']}: {f['label']} ({f['type']})" for f in fields)
    already = ", ".join(f"{k}={v}" for k, v in collected_data.items()) or "(none yet)"
    user_prompt = (
        f"Fields needed:\n{field_list}\n\n"
        f"Already collected: {already}\n\n"
        f"New message: {message}"
    )
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=300,
            tenant_id=tenant_id,
            purpose="expert_handoff_extraction",
        )
    except Exception as e:
        logger.warning(f"Expert handoff extraction failed, keeping existing collected_data: {e}")
        return dict(collected_data)

    valid_keys = {f["key"] for f in fields}
    new_values = {k: v for k, v in data.items() if k in valid_keys and v}
    return {**collected_data, **new_values}


_ACTIVE_STATUSES = ("offer_pending", "collecting", "awaiting_confirmation", "awaiting_payment", "paid")


def _get_active_session(lead_id: str, tenant_id: str, db) -> dict | None:
    result = (
        db.table("expert_handoff_sessions")
        .select("*")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .neq("status", "resolved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    active = [r for r in rows if r["status"] in _ACTIVE_STATUSES]
    return active[0] if active else None


def _create_session(lead_id: str, tenant_id: str, db) -> dict:
    result = (
        db.table("expert_handoff_sessions")
        .insert({"lead_id": lead_id, "tenant_id": tenant_id, "status": "offer_pending", "collected_data": {}})
        .execute()
    )
    return result.data[0]


def _update_session(session_id: str, patch: dict, db) -> None:
    db.table("expert_handoff_sessions").update(patch).eq("id", session_id).execute()


async def _send_and_log(phone: str, text: str, tenant_id: str, lead_id: str, db) -> None:
    from app.services.ai_reply import send_whatsapp
    mid = await send_whatsapp(phone, text, tenant_id=tenant_id)
    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": text,
        "is_ai_generated": True,
        "meta_message_id": mid,
        "reply_source": "expert_handoff",
    }).execute()


_AFFIRMATIVE_RE_WORDS = frozenset({
    "yes", "yeah", "yep", "sure", "ok", "okay", "correct", "right",
    "ஆம்", "சரி",  # Tamil yes/okay
    "हाँ", "ठीक",   # Hindi yes/okay
})


def _is_affirmative(message: str) -> bool:
    import re
    tokens = set(re.findall(r"[\w஀-௿ऀ-ॿ]+", message.strip().lower()))
    return bool(tokens & _AFFIRMATIVE_RE_WORDS)


def _summary_text(fields: list[dict], collected_data: dict) -> str:
    lines = [f"{f['label']}: {collected_data.get(f['key'], '—')}" for f in fields]
    return "Here's what I've got:\n\n" + "\n".join(lines) + "\n\nIs that correct?"


async def route_expert_handoff(lead_id: str, tenant_id: str, phone: str, body: str, db=None) -> bool:
    """Webhook-level routing for the expert handoff session. Returns True if the
    inbound message was consumed (caller must skip generate_reply for this turn)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    if not body:
        return False

    try:
        config = get_expert_handoff_config(tenant_id, db=db)
        if not config.get("enabled"):
            return False

        session = _get_active_session(lead_id, tenant_id, db)

        if session is None:
            matched = await detect_expert_handoff_intent(body, config["trigger_description"], tenant_id)
            if not matched:
                return False
            new_session = _create_session(lead_id, tenant_id, db)
            await _send_and_log(phone, config["offer_message"], tenant_id, lead_id, db)
            _update_session(new_session["id"], {"trigger_reason": body[:500]}, db)
            return True

        status = session["status"]

        if status == "offer_pending":
            if not _is_affirmative(body):
                _update_session(session["id"], {"status": "cancelled"}, db)
                return False
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            if missing:
                _update_session(session["id"], {"status": "collecting", "collected_data": collected}, db)
                await _send_and_log(phone, f"Great! Could you share your {missing[0].lower()}?", tenant_id, lead_id, db)
            else:
                _update_session(session["id"], {"status": "awaiting_confirmation", "collected_data": collected}, db)
                await _send_and_log(phone, _summary_text(config["fields"], collected), tenant_id, lead_id, db)
            return True

        if status == "collecting":
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            if missing:
                _update_session(session["id"], {"collected_data": collected}, db)
                await _send_and_log(phone, f"Thanks! And your {missing[0].lower()}?", tenant_id, lead_id, db)
            else:
                _update_session(session["id"], {"status": "awaiting_confirmation", "collected_data": collected}, db)
                await _send_and_log(phone, _summary_text(config["fields"], collected), tenant_id, lead_id, db)
            return True

        if status == "awaiting_confirmation":
            if not _is_affirmative(body):
                # Let the AI/human sort out a correction request; stay put.
                return False
            ref = f"EH-{uuid.uuid4().hex[:8].upper()}"
            collected = session.get("collected_data") or {}
            customer_name = collected.get("name", "Customer")
            try:
                link = await create_payment_link(
                    booking_id=session["id"],
                    booking_ref=ref,
                    amount_paise=config["amount_paise"],
                    customer_name=customer_name,
                    customer_phone=phone,
                    description=f"Consultation — {customer_name} ({ref})",
                    tenant_id=tenant_id,
                )
                _update_session(session["id"], {
                    "status": "awaiting_payment",
                    "amount_paise": config["amount_paise"],
                    "payment_link": link["payment_link_url"],
                }, db)
                await _send_and_log(
                    phone,
                    f"Great, here's your payment link:\n{link['payment_link_url']}",
                    tenant_id, lead_id, db,
                )
            except Exception as e:
                logger.error(f"Expert handoff payment link creation failed for session {session['id']}: {e}")
                await _send_and_log(
                    phone,
                    "We've received your details — our team will send the payment link shortly.",
                    tenant_id, lead_id, db,
                )
            return True

        # awaiting_payment: nothing to do here, wait for the Razorpay webhook.
        return False
    except Exception as e:
        logger.error(f"route_expert_handoff failed for lead {lead_id}: {e}")
        return False


_FOLLOWUP_REF_RE = re.compile(r"^(?P<sid>.+?)::f\d+$")


def session_ref_to_id(external_ref: str) -> str | None:
    """Resolve a bridge external_ref to its session uuid, or None.

    A follow-up's ref is ``{session_id}::f{n}`` (see astro_bridge.push_followup);
    a consultation's ref is the bare session id. The column is uuid-typed, so a
    non-uuid must never reach the DB — PostgREST rejects it with an APIError
    that would surface as a 500 on a public route instead of the intended 401."""
    ref = str(external_ref or "").strip()
    m = _FOLLOWUP_REF_RE.match(ref)
    if m:
        ref = m.group("sid")
    try:
        return str(uuid.UUID(ref))
    except (ValueError, AttributeError, TypeError):
        return None


def get_session_tenant_id(session_id: str, db=None) -> str | None:
    """Look up which tenant owns a session, so the webhook route can verify the
    Razorpay signature against that tenant's own webhook secret rather than the
    default tenant's. Safe to call before the signature is verified: an attacker
    supplying a forged session_id just gets a lookup miss or another tenant's
    id, and the subsequent HMAC check against that tenant's real secret still
    fails without it. Accepts a follow-up ref ("{sid}::f{n}") and treats any
    malformed/non-uuid ref as a plain miss, never an exception."""
    resolved = session_ref_to_id(session_id)
    if not resolved:
        return None
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    try:
        row = (
            db.table("expert_handoff_sessions")
            .select("tenant_id")
            .eq("id", resolved)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.warning(f"Session tenant lookup failed for ref {session_id!r}: {e}")
        return None
    if not row or not row.data:
        return None
    return row.data.get("tenant_id")


def confirm_expert_handoff_payment(session_id: str, razorpay_payment_id: str, db=None) -> dict | None:
    """Mark a session paid. The AI stays live for the lead (see
    get_paid_unresolved_session / _expert_handoff_paid_prompt_block in
    ai_reply.py) so a lead asking "when will the expert contact me" isn't met
    with silence while waiting for staff to pick up the notification. Returns
    {phone, tenant_id, lead_id, customer_name, session, lead} on success, None if
    the session doesn't exist or was already paid (idempotent — Razorpay may
    retry webhooks, and two retries may land concurrently)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    from datetime import datetime, timezone

    existing = (
        db.table("expert_handoff_sessions")
        .select("id,status,lead_id,tenant_id,collected_data,amount_paise,trigger_reason")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data or existing.data.get("status") == "paid":
        return None

    session = existing.data
    now_iso = datetime.now(timezone.utc).isoformat()
    # The status filter is the whole point: it makes the read-then-write above a
    # single conditional UPDATE, so of two concurrent Razorpay retries exactly one
    # gets a row back and the other cannot bill/consult the lead twice.
    claimed = (
        db.table("expert_handoff_sessions")
        .update({
            "status": "paid",
            "razorpay_payment_id": razorpay_payment_id,
            "paid_at": now_iso,
        })
        .eq("id", session_id)
        .eq("status", "awaiting_payment")
        .execute()
    )
    if not claimed or not claimed.data:
        logger.info(f"Expert handoff session {session_id} already claimed by a concurrent confirm — skipping")
        return None

    session = {**session, **(claimed.data[0] or {})}
    lead_id = session["lead_id"]
    tenant_id = session["tenant_id"]

    lead_row = (
        db.table("leads")
        .select("id,phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"

    try:
        notify_pool(
            tenant_id,
            "expert_handoff_paid",
            "New paid consultation",
            f"Lead '{customer_name}' paid for a consultation — check Consultations.",
            db=db,
        )
    except Exception as e:
        logger.warning(f"expert_handoff_paid notify_pool failed for session {session_id}: {e}")

    return {
        "phone": phone,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "customer_name": customer_name,
        "session": session,
        "lead": lead,
    }


def record_astro_bridge_ids(session_id: str, tenant_id: str, bridge_response: dict, db=None) -> None:
    """Persist the ids Django created for a pushed session, so its reply callback maps back here."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    patch = {
        "astro_question_id": (bridge_response or {}).get("question_id"),
        "astro_horoscope_id": (bridge_response or {}).get("horoscope_id"),
        "astro_user_id": (bridge_response or {}).get("astro_user_id"),
    }
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        logger.warning(f"Astro bridge returned no ids for session {session_id} — nothing to persist")
        return
    (
        db.table("expert_handoff_sessions")
        .update(patch)
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )


async def reconcile_pending_astro_pushes(db=None) -> int:
    """Re-drive the Django consultation push for paid sessions it never reached.

    The confirm-time push is best-effort: if Django is down for the one webhook
    that flips a session to paid, the paid transition is idempotent and never
    re-fires, so without this sweep the customer has paid, been told "our expert
    will be in touch", and no astrologer ever sees the consultation. Django's
    side is idempotent on the session id (UNIQUE order id), so re-driving is
    always safe. Window: 3 days — older stuck sessions need a human anyway."""
    from datetime import datetime, timedelta, timezone

    from app.services import astro_bridge

    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    try:
        rows = (
            db.table("expert_handoff_sessions")
            .select("id,tenant_id,lead_id,collected_data,trigger_reason,amount_paise")
            .eq("status", "paid")
            .is_("astro_question_id", "null")
            .gte("created_at", cutoff)
            .limit(20)
            .execute()
        )
    except Exception as e:
        logger.error(f"Astro push reconcile query failed: {e}")
        return 0

    pushed = 0
    for session in rows.data or []:
        tenant_id = session.get("tenant_id")
        try:
            lead_row = (
                db.table("leads")
                .select("id,name,phone")
                .eq("id", session.get("lead_id"))
                .eq("tenant_id", tenant_id)
                .maybe_single()
                .execute()
            )
            lead = (lead_row.data if lead_row else None) or {}
            result = await astro_bridge.push_consultation(session, lead, tenant_id)
            if result:
                record_astro_bridge_ids(session["id"], tenant_id, result, db=db)
                pushed += 1
                logger.info(f"Astro push reconciled for session {session['id']} (tenant {tenant_id})")
        except Exception as e:
            logger.error(f"Astro push reconcile failed for session {session.get('id')}: {e}")
    return pushed


def get_paid_unresolved_session(lead_id: str, tenant_id: str, db=None) -> dict | None:
    """The lead's most recent paid-but-not-yet-resolved session, if any. Used by
    ai_reply.py to keep the AI reassuring the lead instead of going silent, and
    by route_expert_handoff/_get_active_session to stop a lead being offered a
    second paid consultation while the first is still unresolved."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    result = (
        db.table("expert_handoff_sessions")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "paid")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def resolve_expert_handoff_session(session_id: str, tenant_id: str, db=None) -> bool:
    """Staff marks a paid consultation as handled — the AI reassurance context
    (get_paid_unresolved_session) stops applying and the session leaves the
    Consultations "Paid" list. Only transitions from 'paid'; returns False if
    the session doesn't exist, belongs to another tenant, or isn't paid yet."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    from datetime import datetime, timezone

    result = (
        db.table("expert_handoff_sessions")
        .update({"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "paid")
        .execute()
    )
    return bool(result.data)


_WA_SESSION_WINDOW_HOURS = 24

_AUDIO_MIMES = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "amr": "audio/amr",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
}


def _within_whatsapp_window(last_inbound_at) -> bool:
    from datetime import datetime, timedelta, timezone

    if not last_inbound_at:
        return False
    try:
        last = datetime.fromisoformat(str(last_inbound_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last <= timedelta(hours=_WA_SESSION_WINDOW_HOURS)


def _astro_phone_number_id(tenant_id: str, db) -> str | None:
    """The tenant's inbound WhatsApp number, so the astrologer's reply lands in the lead's existing thread."""
    try:
        rows = (
            db.table("phone_numbers")
            .select("meta_phone_number_id")
            .eq("tenant_id", tenant_id)
            .eq("role", "primary")
            .limit(1)
            .execute()
        )
        return ((rows.data or [{}])[0] or {}).get("meta_phone_number_id")
    except Exception as e:
        logger.warning(f"Could not resolve primary phone_number_id for tenant {tenant_id}: {e}")
        return None


def _media_mime(url: str, wa_type: str) -> tuple[str, str]:
    import re

    found = re.search(r"\.([a-z0-9]{2,5})(?:\?|$)", str(url or "").lower())
    ext = found.group(1) if found else ""
    if wa_type == "image":
        return ("image/png", "reply.png") if ext == "png" else ("image/jpeg", "reply.jpg")
    return _AUDIO_MIMES.get(ext, "audio/mpeg"), f"reply.{ext or 'mp3'}"


def _log_astro_message(db, lead_id: str, tenant_id: str, content: str, mid: str | None) -> None:
    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": content,
        "is_ai_generated": False,
        "meta_message_id": mid,
        "reply_source": "expert_handoff",
    }).execute()


async def _send_astro_media(phone: str, url: str, wa_type: str, tenant_id: str, phone_number_id: str | None) -> str | None:
    from app.services.meta_cloud import send_media_message, upload_media_to_meta

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()

    mime_type, filename = _media_mime(url, wa_type)
    media_id = await upload_media_to_meta(
        file_bytes=resp.content,
        mime_type=mime_type,
        filename=filename,
        tenant_id=tenant_id,
        phone_number_id=phone_number_id,
    )
    data = await send_media_message(
        to_number=phone,
        media_id=media_id,
        wa_type=wa_type,
        tenant_id=tenant_id,
        phone_number_id=phone_number_id,
    )
    return (data.get("messages") or [{}])[0].get("id")


async def deliver_astro_reply(payload: dict, tenant_id: str, db=None) -> dict:
    """Deliver one astrologer reply from the Django bridge to the lead's WhatsApp thread."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    from app.services.ai_reply import send_whatsapp

    external_ref = str(payload.get("external_ref") or "")
    session_id = session_ref_to_id(external_ref)
    if not session_id:
        logger.warning(f"Astro reply with malformed external_ref {external_ref!r} (tenant {tenant_id})")
        return {"ok": True, "delivered": [], "reason": "unknown_session"}
    try:
        reply_id = int(payload.get("reply_id"))
    except (TypeError, ValueError):
        logger.error(f"Astro reply for session {external_ref} has no usable reply_id — cannot dedupe, dropping")
        return {"ok": True, "delivered": [], "reason": "missing_reply_id"}

    row = (
        db.table("expert_handoff_sessions")
        .select("id,lead_id,tenant_id,astro_last_reply_id")
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    session = (row.data if row else None) or {}
    if not session:
        logger.warning(f"Astro reply for unknown session {external_ref} (tenant {tenant_id})")
        return {"ok": True, "delivered": [], "reason": "unknown_session"}

    prior_reply_id = session.get("astro_last_reply_id")

    # Claim the reply id before sending, not after: a Django retry that overlaps
    # the first delivery must lose here rather than send the astrologer's answer
    # to the customer twice. Monotonic (.lt) rather than mere inequality, so a
    # replayed OLDER reply arriving after a newer one is also a duplicate.
    claimed = (
        db.table("expert_handoff_sessions")
        .update({"astro_last_reply_id": reply_id})
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .or_(f"astro_last_reply_id.is.null,astro_last_reply_id.lt.{reply_id}")
        .execute()
    )
    if not claimed or not claimed.data:
        logger.info(f"Astro reply {reply_id} for session {external_ref} already delivered — ignoring duplicate")
        return {"ok": True, "duplicate": True}

    lead_id = session.get("lead_id")
    lead_row = (
        db.table("leads")
        .select("id,phone,last_inbound_at")
        .eq("id", lead_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone") or ""
    if not phone:
        logger.error(f"Astro reply {reply_id} for session {external_ref} undeliverable: lead {lead_id} has no phone")
        return {"ok": True, "delivered": [], "reason": "no_phone"}

    if not _within_whatsapp_window(lead.get("last_inbound_at")):
        logger.error(
            f"Astro reply {reply_id} for session {external_ref} NOT delivered: the lead's 24h WhatsApp "
            f"window closed (last_inbound_at={lead.get('last_inbound_at')}). The astrologer believes "
            f"the customer has been answered — they have not."
        )
        try:
            notify_pool(
                tenant_id,
                "expert_handoff_paid",
                "Astrologer reply could not be delivered",
                f"The 24h WhatsApp window for this consultation has closed — reach {phone} another way.",
                db=db,
            )
        except Exception as e:
            logger.warning(f"Astro reply window notify_pool failed for session {external_ref}: {e}")
        return {"ok": True, "delivered": [], "outside_24h_window": True}

    phone_number_id = _astro_phone_number_id(tenant_id, db)
    delivered: list[str] = []
    failed: list[str] = []

    text = str(payload.get("reply_text") or "").strip()
    if text:
        try:
            mid = await send_whatsapp(phone, text, tenant_id=tenant_id, phone_number_id=phone_number_id)
        except Exception as e:
            logger.error(f"Astro reply {reply_id} text send failed for session {external_ref}: {e}")
            mid = None
        if mid:
            _log_astro_message(db, lead_id, tenant_id, text, mid)
            delivered.append("text")
        else:
            failed.append("text")

    for part, url, wa_type in (
        ("image", payload.get("reply_image_url"), "image"),
        ("voice", payload.get("reply_voice_url"), "audio"),
    ):
        if not url:
            continue
        try:
            mid = await _send_astro_media(phone, str(url), wa_type, tenant_id, phone_number_id)
            _log_astro_message(db, lead_id, tenant_id, str(url), mid)
            delivered.append(part)
        except Exception as e:
            logger.error(f"Astro reply {reply_id} {part} send failed for session {external_ref}: {e}")
            failed.append(part)

    if failed and not delivered:
        # Total in-window failure: every part the astrologer sent was attempted
        # and none went out. Returning bare success here would strand the reply
        # forever — the claim above blocks any retry, Django never retries on
        # 2xx, and the astrologer's UI already shows it as sent. Roll the claim
        # back so a re-push can re-drive it, and surface it to staff.
        logger.error(f"Astro reply {reply_id} for session {external_ref} delivered nothing (failed={failed})")
        try:
            (
                db.table("expert_handoff_sessions")
                .update({"astro_last_reply_id": prior_reply_id})
                .eq("id", session_id)
                .eq("tenant_id", tenant_id)
                .eq("astro_last_reply_id", reply_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"Astro reply {reply_id} claim rollback failed for session {external_ref}: {e}")
        try:
            notify_pool(
                tenant_id,
                "expert_handoff_paid",
                "Astrologer reply could not be delivered",
                f"WhatsApp delivery to {phone} failed for a paid consultation "
                f"(parts failed: {', '.join(failed)}) — reach the customer another way.",
                db=db,
            )
        except Exception as e:
            logger.warning(f"Astro reply failure notify_pool failed for session {external_ref}: {e}")
        return {"ok": True, "delivered": [], "failed": failed, "delivery_failed": True}

    return {"ok": True, "delivered": delivered, "failed": failed}
