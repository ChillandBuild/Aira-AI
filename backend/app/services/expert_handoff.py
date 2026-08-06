"""Generic, per-tenant paid expert handoff: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging
import uuid

from app.services.gemini_client import gemini_chat_completion_json
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


_ACTIVE_STATUSES = ("offer_pending", "collecting", "awaiting_confirmation", "awaiting_payment")


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


def confirm_expert_handoff_payment(session_id: str, razorpay_payment_id: str, db=None) -> tuple[str, str, str, str] | None:
    """Mark a session paid and mute the AI for its lead. Returns
    (phone, tenant_id, lead_id, customer_name) on success, None if the session
    doesn't exist or was already paid (idempotent — Razorpay may retry webhooks)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    from datetime import datetime, timezone

    existing = (
        db.table("expert_handoff_sessions")
        .select("id,status,lead_id,tenant_id,collected_data")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data or existing.data.get("status") == "paid":
        return None

    session = existing.data
    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("expert_handoff_sessions").update({
        "status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
        "paid_at": now_iso,
    }).eq("id", session_id).execute()

    lead_id = session["lead_id"]
    tenant_id = session["tenant_id"]
    db.table("leads").update({"ai_enabled": False}).eq("id", lead_id).execute()

    lead_row = (
        db.table("leads")
        .select("phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"
    return (phone, tenant_id, lead_id, customer_name)
