# backend/app/services/booking_flow.py
import logging
import re
import uuid
from typing import Any

from app.db.supabase import get_supabase

try:
    from app.services.payment_razorpay import create_payment_link
except ImportError:
    create_payment_link = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_FLOW_STEPS = [
    ("collecting_name",        "🙏 Wonderful! Please share the *full name* as it should appear in the booking."),
    ("collecting_rasi",        "Thank you! Please share your *Rasi* (zodiac sign) — e.g. Mesham, Rishabam, Mithunam..."),
    ("collecting_nakshatram",  "Please share your *Nakshatram* (birth star) — e.g. Ashwini, Bharani, Karthigai..."),
    ("collecting_gotram",      "Please share your *Gotram* (lineage/clan name). If unknown, reply 'Not known'."),
    ("collecting_address",     "Please share your *full delivery address* for prasadam — include street, city, state, and PIN code."),
]

_STATE_TO_FIELD = {
    "collecting_name":       "devotee_name",
    "collecting_rasi":       "rasi",
    "collecting_nakshatram": "nakshatram",
    "collecting_gotram":     "gotram",
    "collecting_address":    "delivery_address",
}

_INTENT_KEYWORDS = frozenset({
    "book", "booking", "register", "enroll",
    "புக்", "வேணும்", "பதிவு",
})

_BOOKING_DEFAULTS = {
    "event_name": "Booking",
    "ref_prefix": "BK",
    "amount_paise": 50000,
}


def _get_booking_settings(tenant_id: str | None) -> dict:
    if not tenant_id:
        return dict(_BOOKING_DEFAULTS)
    try:
        from app.services.config_dynamic import get_setting
        event_name = get_setting("booking_event_name", _BOOKING_DEFAULTS["event_name"], tenant_id=tenant_id)
        ref_prefix = (get_setting("booking_ref_prefix", _BOOKING_DEFAULTS["ref_prefix"], tenant_id=tenant_id) or "").upper() or "BK"
        amount_raw = get_setting("booking_amount_paise", str(_BOOKING_DEFAULTS["amount_paise"]), tenant_id=tenant_id)
        amount = int(amount_raw) if amount_raw else _BOOKING_DEFAULTS["amount_paise"]
        return {"event_name": event_name, "ref_prefix": ref_prefix, "amount_paise": amount}
    except Exception as e:
        logger.warning(f"Failed to read booking settings for tenant {tenant_id}: {e}")
        return dict(_BOOKING_DEFAULTS)


def _generate_booking_ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


async def detect_booking_intent(message: str) -> bool:
    text = message.strip().lower()
    # Use token split to avoid substring matches (e.g. "book" in "facebook")
    tokens = set(re.findall(r"[\w஀-௿]+", text))
    return bool(tokens & _INTENT_KEYWORDS)


_QUESTION_TOKENS = frozenset({
    "what", "when", "where", "how", "why", "which", "who",
    "is", "are", "can", "will", "do", "does", "should", "would", "could",
    # Tamil question markers
    "என்ன", "எப்போது", "எங்கே", "எப்படி", "ஏன்", "யார்",
    # Hindi question markers
    "क्या", "कब", "कहाँ", "कैसे", "क्यों", "कौन",
})


def _is_booking_question(message: str) -> bool:
    text = message.strip()
    if "?" in text or "？" in text:
        return True
    tokens = set(re.findall(r"[\w஀-௿ऀ-ॿ]+", text.lower()))
    return bool(tokens & _QUESTION_TOKENS)

from app.services.groq_client import get_groq_client

def _get_groq_client(tenant_id: str | None = None):
    try:
        return get_groq_client(tenant_id, is_async=True)
    except Exception as e:
        logger.warning(f"Failed to initialize Groq client in booking_flow: {e}")
        return None


async def _validate_collect_input(current_state: str, message: str, tenant_id: str | None = None) -> bool:
    client = _get_groq_client(tenant_id)
    if not client:
        return True

    step_descriptions = {
        "collecting_name": "providing their name or devotee's name for booking registration",
        "collecting_rasi": "providing their Rasi (zodiac sign, e.g., Mesham, Rishabam, Mithunam, Simha, Leo)",
        "collecting_nakshatram": "providing their Nakshatram (birth star, e.g., Ashwini, Bharani, Karthigai, Rohini)",
        "collecting_gotram": "providing their Gotram (clan/lineage, or 'unknown', 'not known', 'dont know')",
        "collecting_address": "providing their full delivery address for prasadam delivery"
    }

    desc = step_descriptions.get(current_state, "providing the requested details")

    prompt = (
        "You are a validation assistant. A user is currently in a booking flow step where they are asked to provide specific information.\n\n"
        f"Expected Information: {desc}\n"
        f"User Message: \"{message}\"\n\n"
        "Determine if the User Message is actually attempting to provide the expected information (or saying 'not known' / 'unknown' for Gotram/Rasi/Nakshatram/Address).\n"
        "If the user is asking a question, saying they don't know (except for Gotram/Rasi/Nakshatram where 'unknown' is acceptable), expressing hesitation, saying 'no', rejecting the offer, or talking about something completely unrelated, they are NOT providing the information.\n\n"
        "Reply with ONLY \"YES\" if they are providing the expected information.\n"
        "Reply with ONLY \"NO\" if they are NOT providing the expected information (e.g., asking questions, rejecting, or off-topic).\n"
        "Do not include any explanation or extra text."
    )

    try:
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4,
        )
        val = resp.choices[0].message.content.strip().upper()
        return "YES" in val
    except Exception as e:
        logger.error(f"Booking input validation failed: {e}")
        return True


async def route_booking_intent(
    lead_id: str,
    tenant_id: str,
    phone: str,
    body: str,
    db,
) -> bool:
    """Webhook-level routing for the 5-step booking state machine.

    Returns True if the inbound message was consumed by the booking flow
    (caller must skip bot trigger fan-out + AI reply for this message).

    Priority:
      1. Active booking state (collecting_*) → advance_state (saves the field,
         sends next prompt, or fires payment link on the last step).
      2. No state + booking intent detected → start_booking_flow (sends first
         prompt: "share your name").
      3. Otherwise → False (caller continues to bot + AI).
    """
    if not body:
        return False
    try:
        conv_state = get_or_create_state(lead_id, tenant_id, db)
        current_state = conv_state.get("state", "idle")
        if current_state in _BOOKING_COLLECT_STATES:
            if _is_booking_question(body):
                # Off-topic question mid-flow: let AI answer it, don't consume the message.
                # ai_reply will append the pending step prompt so the lead knows where they left off.
                return False
            # Check rejection patterns
            try:
                from app.services.scoring_engine import _REJECTION_PATTERNS
                for pat in _REJECTION_PATTERNS:
                    if re.search(pat, body, re.IGNORECASE):
                        logger.info(f"Rejection pattern matched in booking flow for lead {lead_id}: {body}")
                        return False
            except Exception as re_err:
                logger.warning(f"Rejection patterns check failed: {re_err}")

            # Validate input using LLM
            is_valid = await _validate_collect_input(current_state, body, tenant_id=tenant_id)
            if not is_valid:
                logger.info(f"Booking flow input validation failed for state {current_state}, message: {body}")
                return False

            await advance_state(state=conv_state, message=body, phone=phone, db=db)
            return True
        if current_state == "idle" and await detect_booking_intent(body):
            await start_booking_flow(lead_id, tenant_id, phone, db=db, existing_state=conv_state)
            return True
    except Exception as e:
        logger.error(f"route_booking_intent failed for lead {lead_id}: {e}")
    return False


_BOOKING_COLLECT_STATES = frozenset({
    "collecting_name", "collecting_rasi", "collecting_nakshatram",
    "collecting_gotram", "collecting_address",
})


def get_or_create_state(lead_id: str, tenant_id: str, db=None) -> dict:
    """Fetch the conversation state for a lead, or return a fresh idle state.

    Uses .limit(1) instead of .maybe_single() to avoid the HTTP 406 error
    that Supabase raises when no row exists and .single() / .maybe_single()
    is used on an empty result set.
    
    Also checks for inactivity gaps:
    - >1hr: triggers auto-compaction (fire-and-forget)
    - >6hr: session reset (flow state → idle, summary retained) + re-engagement message
    """
    from datetime import datetime, timezone, timedelta
    
    db = db or get_supabase()
    try:
        response = (
            db.table("lead_conversation_state")
            .select("*")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.warning(f"lead_conversation_state query failed for lead {lead_id}: {e}. Defaulting to idle state.")
        response = None

    # Guard: response may be None if the query itself raised, or data may be
    # an empty list when the lead has no state row yet — both are handled safely.
    if response and response.data:
        state = response.data[0]
        
        # Check inactivity gap
        last_activity = state.get("last_activity_at")
        if last_activity:
            try:
                last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                gap = now_dt - last_dt
                
                # Auto-compact if gap > 1 hour (fire-and-forget)
                if gap > timedelta(hours=1):
                    import asyncio
                    try:
                        from app.services.conversation_compactor import compact_conversation
                        asyncio.create_task(compact_conversation(lead_id, tenant_id, db, mode="rolling"))
                        logger.info(f"Auto-compaction triggered for lead {lead_id} after {gap} inactivity")
                    except Exception as compact_err:
                        logger.error(f"Auto-compaction failed for lead {lead_id}: {compact_err}")
                
                # Session reset if gap > 6 hours
                if gap > timedelta(hours=6):
                    state["state"] = "idle"
                    logger.info(f"Session reset for lead {lead_id} after {gap} inactivity — summary retained for context")

                    # Re-engagement message: only fires if BOTH ai_auto_reply_enabled AND
                    # reengagement_enabled are on. Reuses the same gate pattern as the
                    # auto-reply pipeline so operators get a single consistent kill switch.
                    try:
                        from app.services.config_dynamic import get_setting
                        ai_on = get_setting("ai_auto_reply_enabled", "true", tenant_id=tenant_id) == "true"
                        re_on = get_setting("reengagement_enabled", "true", tenant_id=tenant_id) == "true"
                    except Exception:
                        ai_on, re_on = True, True

                    if ai_on and re_on:
                        try:
                            phone = (
                                db.table("leads")
                                .select("phone")
                                .eq("id", lead_id)
                                .maybe_single()
                                .execute()
                            )
                            phone_number = (phone.data or {}).get("phone")
                            if phone_number:
                                reengagement_msg = "🙏 Welcome back! How can I help you continue?"
                                import asyncio
                                asyncio.create_task(send_whatsapp_text(phone=phone_number, text=reengagement_msg, tenant_id=tenant_id, lead_id=lead_id))
                                logger.info(f"Re-engagement message sent to lead {lead_id}")
                        except Exception as reeng_err:
                            logger.error(f"Re-engagement message failed for lead {lead_id}: {reeng_err}")
                    else:
                        logger.info(f"Re-engagement skipped for lead {lead_id} (ai_enabled={ai_on}, reengagement_enabled={re_on})")
            except Exception as parse_err:
                logger.warning(f"Failed to parse last_activity_at for lead {lead_id}: {parse_err}")
        
        return state

    # No existing state — return a fresh idle state dict (not persisted yet).
    logger.info(f"No conversation state found for lead {lead_id}. Initialising idle state.")
    return {
        "id": None,
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "flow_name": "booking",
        "state": "idle",
        "draft_data": {},
        "booking_id": None,
    }


def _upsert_state(state: dict, db) -> None:
    if state.get("id"):
        db.table("lead_conversation_state").update({
            "state": state["state"],
            "draft_data": state["draft_data"],
            "booking_id": state.get("booking_id"),
        }).eq("id", state["id"]).execute()
    else:
        result = db.table("lead_conversation_state").insert({
            "lead_id": state["lead_id"],
            "tenant_id": state["tenant_id"],
            "flow_name": state["flow_name"],
            "state": state["state"],
            "draft_data": state["draft_data"],
            "booking_id": state.get("booking_id"),
        }).execute()
        if result.data:
            state["id"] = result.data[0]["id"]


def _get_next_step(current_state: str) -> str | None:
    states = [s for s, _ in _FLOW_STEPS]
    try:
        idx = states.index(current_state)
        return states[idx + 1] if idx + 1 < len(states) else None
    except ValueError:
        return None


def _get_step_prompt(state_name: str) -> str:
    for s, prompt in _FLOW_STEPS:
        if s == state_name:
            return prompt
    return ""


def get_pending_step_prompt(state: dict | None) -> str | None:
    """Return the prompt for the current collection step, or None if not mid-flow."""
    if not state:
        return None
    current = state.get("state", "idle")
    if current not in _BOOKING_COLLECT_STATES:
        return None
    return _get_step_prompt(current) or None


async def send_whatsapp_text(phone: str, text: str, tenant_id: str | None = None, lead_id: str | None = None) -> None:
    from app.services.ai_reply import send_whatsapp
    mid = await send_whatsapp(phone, text, tenant_id=tenant_id)
    if lead_id:
        if not tenant_id:
            raise ValueError("tenant_id required when logging booking flow message")
        try:
            db = get_supabase()
            db.table("messages").insert({
                "lead_id": lead_id,
                "direction": "outbound",
                "channel": "whatsapp",
                "content": text,
                "is_ai_generated": True,
                "reply_source": "ai",
                "meta_message_id": mid,
                "tenant_id": tenant_id,
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log booking flow message for lead {lead_id}: {e}")


def _create_draft_booking(lead_id: str, tenant_id: str, db) -> dict:
    # Check for an existing non-cancelled booking to prevent duplicates on concurrent messages
    existing = (
        db.table("bookings")
        .select("id, booking_ref, amount_paise")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .neq("status", "cancelled")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]
    settings = _get_booking_settings(tenant_id)
    result = db.table("bookings").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "event_name": settings["event_name"],
        "booking_ref": _generate_booking_ref(settings["ref_prefix"]),
        "status": "draft",
        "amount_paise": settings["amount_paise"],
    }).execute()
    return result.data[0]


async def start_booking_flow(
    lead_id: str,
    tenant_id: str,
    phone: str,
    db=None,
    existing_state: dict | None = None,
) -> None:
    db = db or get_supabase()
    booking = _create_draft_booking(lead_id, tenant_id, db)
    state = {
        "id": (existing_state or {}).get("id"),
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "flow_name": "booking",
        "state": "collecting_name",
        "draft_data": {},
        "booking_id": booking["id"],
    }
    _upsert_state(state, db)
    await send_whatsapp_text(phone=phone, text=_get_step_prompt("collecting_name"), tenant_id=tenant_id, lead_id=lead_id)
    logger.info(f"Booking flow started for lead {lead_id}, booking {booking['id']}")


async def advance_state(state: dict, message: str, phone: str, db=None) -> None:
    db = db or get_supabase()
    current = state["state"]

    if current in ("idle", "awaiting_payment"):
        return

    field = _STATE_TO_FIELD.get(current)
    if field:
        state["draft_data"] = {**state["draft_data"], field: message.strip()}

    next_state = _get_next_step(current)

    if next_state:
        state["state"] = next_state
        _upsert_state(state, db)
        await send_whatsapp_text(phone=phone, text=_get_step_prompt(next_state), tenant_id=state.get("tenant_id"), lead_id=state.get("lead_id"))
    else:
        await _send_payment_link(state, phone, db)


async def _send_payment_link(state: dict, phone: str, db) -> None:
    booking_id = state["booking_id"]
    draft = state["draft_data"]
    settings = _get_booking_settings(state.get("tenant_id"))

    booking_row = (
        db.table("bookings")
        .select("booking_ref,amount_paise")
        .eq("id", booking_id)
        .maybe_single()
        .execute()
    )
    booking = booking_row.data or {}
    booking_ref = booking.get("booking_ref") or _generate_booking_ref(settings["ref_prefix"])
    amount_paise = booking.get("amount_paise") or settings["amount_paise"]

    db.table("bookings").update({
        "devotee_name":    draft.get("devotee_name"),
        "rasi":            draft.get("rasi"),
        "nakshatram":      draft.get("nakshatram"),
        "gotram":          draft.get("gotram"),
        "delivery_address": draft.get("delivery_address"),
        "status": "pending_payment",
    }).eq("id", booking_id).execute()

    try:
        result = await create_payment_link(
            booking_id=booking_id,
            booking_ref=booking_ref,
            amount_paise=amount_paise,
            customer_name=draft.get("devotee_name", "Devotee"),
            customer_phone=phone,
            description=f"Booking — {draft.get('devotee_name', 'Customer')} ({booking_ref})",
            tenant_id=state.get("tenant_id"),
        )

        payment_url = result["payment_link_url"]
        razorpay_id = result["razorpay_payment_link_id"]

        db.table("bookings").update({
            "payment_link": payment_url,
            "razorpay_payment_id": razorpay_id,
        }).eq("id", booking_id).execute()

        state["state"] = "awaiting_payment"
        _upsert_state(state, db)

        summary = (
            f"🙏 Here is your booking summary:\n\n"
            f"📋 *Reference:* {booking_ref}\n"
            f"👤 *Name:* {draft.get('devotee_name', '—')}\n"
            f"♈ *Rasi:* {draft.get('rasi', '—')}\n"
            f"⭐ *Nakshatram:* {draft.get('nakshatram', '—')}\n"
            f"🏛️ *Gotram:* {draft.get('gotram', '—')}\n"
            f"📦 *Prasadam address:* {draft.get('delivery_address', '—')}\n\n"
            f"💳 Click to pay and confirm your booking:\n{payment_url}\n\n"
            f"Reference: {booking_ref}"
        )
        await send_whatsapp_text(phone=phone, text=summary, tenant_id=state.get("tenant_id"), lead_id=state.get("lead_id"))
        logger.info(f"Payment link sent to {phone} for booking {booking_id}")

    except Exception as e:
        logger.error(f"Payment link generation failed for booking {booking_id}: {e}")
        state["state"] = "awaiting_payment"
        _upsert_state(state, db)
        await send_whatsapp_text(
            phone=phone,
            text="🙏 We have received your details! Our team will send you the payment link shortly.",
            tenant_id=state.get("tenant_id"),
            lead_id=state.get("lead_id"),
        )


def confirm_booking(
    booking_id: str,
    razorpay_payment_id: str,
    db=None,
) -> tuple[str | None, str | None, str | None, str | None] | None:
    """Mark booking confirmed. Returns (phone, booking_ref, devotee_name, tenant_id) or None."""
    db = db or get_supabase()
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        updated = (
            db.table("bookings")
            .update({
                "status": "confirmed",
                "razorpay_payment_id": razorpay_payment_id,
                "paid_at": now_iso,
                "confirmed_at": now_iso,
            })
            .eq("id", booking_id)
            .eq("status", "pending")
            .execute()
        )
        if not updated.data:
            return None
    except Exception as e:
        logger.error(f"Atomic confirm_booking update failed: {e}")
        return None

    db.table("lead_conversation_state").update({
        "state": "idle",
    }).eq("booking_id", booking_id).execute()

    booking_row = (
        db.table("bookings")
        .select("lead_id, booking_ref, devotee_name, tenant_id")
        .eq("id", booking_id)
        .maybe_single()
        .execute()
    )
    if not booking_row.data:
        return None

    lead_row = (
        db.table("leads")
        .select("phone")
        .eq("id", booking_row.data["lead_id"])
        .maybe_single()
        .execute()
    )
    phone = (lead_row.data or {}).get("phone")
    return (
        phone,
        booking_row.data.get("booking_ref"),
        booking_row.data.get("devotee_name"),
        booking_row.data.get("tenant_id"),
    )
