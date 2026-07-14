import json
import logging
import re
import time
import httpx
from app.db.supabase import get_supabase
from app.services.growth import record_stage_event, sync_follow_up_jobs
from app.services.segmentation import score_to_segment, parse_thresholds
from app.services.knowledge_service import get_knowledge_context
from app.services.catalog_retrieval import (
    contention_set,
    classify_gate,
    differing_attribute_directive,
    broad_browse_directive,
    match_catalog_items,
)
from app.services.assignment import (
    maybe_assign_lead,
    get_inbox_config,
    should_escalate_hot_lead,
    should_escalate_to_inbox,
)
from app.services.entitlements import meter, check_quota

logger = logging.getLogger(__name__)

from app.config_dynamic import get_setting, require_tenant_setting
from app.services.sarvam_client import sarvam_chat_completion, sarvam_chat_completion_with_tools
from app.services.gemini_client import gemini_chat_completion, gemini_chat_completion_with_tools
from app.services.openai_client import openai_chat_completion, openai_chat_completion_with_tools
from app.services.groq_client import groq_chat_completion, groq_chat_completion_with_tools

_DEFAULT_REPLY_MODEL = "sarvam-30b"

# Each entry: stored ai_reply_model prefix -> (provider name, native-model-id prefix to
# strip). Sarvam has no prefix since its native IDs ("sarvam-30b") are used directly.
_PROVIDER_PREFIXES: list[tuple[str, str]] = [
    ("google/", "gemini"),
    ("openai/", "openai"),
    ("groq/", "groq"),
]

def _resolve_reply_model(tenant_id: str | None) -> str:
    return get_setting("ai_reply_model", fallback=_DEFAULT_REPLY_MODEL, tenant_id=tenant_id) or _DEFAULT_REPLY_MODEL


def _provider_and_native_model(model: str) -> tuple[str, str]:
    if model.startswith("sarvam"):
        return "sarvam", model
    for prefix, provider in _PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return provider, model[len(prefix):]
    raise RuntimeError(f"Unrecognized reply model '{model}'")


def _resolve_provider(tenant_id: str | None) -> tuple[str, str]:
    """Resolves (provider, native_model) for this tenant's selected ai_reply_model, and
    enforces that the tenant has explicitly configured that provider's API key. No
    fallback to a platform-wide key for any provider, including Sarvam -- every client's
    keys are configured independently in the operator console (see decisions/log.md)."""
    provider, native_model = _provider_and_native_model(_resolve_reply_model(tenant_id))
    require_tenant_setting(f"{provider}_api_key", tenant_id)
    return provider, native_model


async def _llm_chat(messages: list[dict], max_tokens: int = 300, tenant_id: str | None = None) -> str:
    provider, native_model = _resolve_provider(tenant_id)
    kwargs = dict(messages=messages, model=native_model, temperature=0.4, max_tokens=max_tokens, tenant_id=tenant_id)
    if provider == "sarvam":
        return await sarvam_chat_completion(**kwargs)
    if provider == "gemini":
        return await gemini_chat_completion(**kwargs)
    if provider == "openai":
        return await openai_chat_completion(**kwargs)
    return await groq_chat_completion(**kwargs)


async def _llm_complete(prompt: str, max_tokens: int = 300, tenant_id: str | None = None) -> str:
    return await _llm_chat([{"role": "user", "content": prompt}], max_tokens=max_tokens, tenant_id=tenant_id)


async def _llm_chat_with_tools(
    messages: list[dict], tools: list[dict], max_tokens: int = 300, tenant_id: str | None = None
) -> tuple[str, list[dict]]:
    """Tool-calling counterpart to _llm_chat -- routes catalog-recommendation replies
    through the tenant's selected ai_reply_model instead of hardcoding Sarvam."""
    provider, native_model = _resolve_provider(tenant_id)
    if provider == "sarvam":
        return await sarvam_chat_completion_with_tools(messages, tools=tools, model=native_model, max_tokens=max_tokens, tenant_id=tenant_id)
    if provider == "gemini":
        return await gemini_chat_completion_with_tools(messages, tools=tools, model=native_model, max_tokens=max_tokens, tenant_id=tenant_id)
    if provider == "openai":
        return await openai_chat_completion_with_tools(messages, tools=tools, model=native_model, max_tokens=max_tokens, tenant_id=tenant_id)
    return await groq_chat_completion_with_tools(messages, tools=tools, model=native_model, max_tokens=max_tokens, tenant_id=tenant_id)


def _resolve_campaign(db, lead_id: str) -> tuple[str | None, str | None]:
    """Resolve the campaign this lead most recently belongs to, from lead_tag_interest
    (the populated lead↔tag table written on every tagged broadcast send). Returns
    (tag_id, tag_name) or (None, None) for cold/inbound-first leads. Fail-safe: any
    error → no campaign, which makes retrieval fall back to the full (unscoped) KB."""
    try:
        row = (
            db.table("lead_tag_interest")
            .select("tag_id")
            .eq("lead_id", str(lead_id))
            .order("last_seen", desc=True)
            .limit(1)
            .execute()
        )
        if not row.data:
            return None, None
        tag_id = row.data[0]["tag_id"]
        tag = (
            db.table("broadcast_tags")
            .select("name")
            .eq("id", tag_id)
            .limit(1)
            .execute()
        )
        if not tag.data:
            # Tag was deleted — treat as no campaign so retrieval stays unscoped
            # rather than collapsing to global-only chunks.
            return None, None
        return tag_id, tag.data[0]["name"]
    except Exception as e:
        logger.warning(f"Campaign resolve failed for lead {lead_id}: {e}")
        return None, None


def _fetch_conversation_summary(db, lead_id: str) -> str | None:
    """Fetch the compacted conversation_summary from lead_conversation_state.
    Returns None if no summary exists or on error."""
    try:
        row = (
            db.table("lead_conversation_state")
            .select("conversation_summary")
            .eq("lead_id", str(lead_id))
            .limit(1)
            .execute()
        )
        if row and row.data:
            summary = (row.data[0].get("conversation_summary") or "").strip()
            return summary or None
    except Exception as e:
        logger.warning(f"Conversation summary fetch failed for lead {lead_id}: {e}")
    return None

FALLBACK_PROMPT = """You are a helpful AI assistant for a business. Answer customer queries warmly and accurately.
Keep replies concise (2-3 sentences max).
Always guide the customer toward the next step: getting more information, making a purchase, or speaking with the team.
If you don't know a specific detail, say: "Let me connect you with our team who can help you right away."
If the customer asks to speak in a regional language, respond in that language.
"""
# NOTE: This is the generic fallback. Every tenant should configure their own prompt
# via the AI Tune page (Knowledge → AI Tune tab). The fallback is only used when no
# custom prompt exists for a given channel.

REENGAGEMENT_FALLBACKS = {}

_prompt_cache: dict[str, tuple[float, str]] = {}
_PROMPT_TTL = 60.0


def _get_prompt(name: str, tenant_id: str | None = None) -> str:
    cache_key = f"{tenant_id}:{name}" if tenant_id else name
    cached = _prompt_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _PROMPT_TTL:
        return cached[1]
    try:
        db = get_supabase()
        query = db.table("ai_prompts").select("content").eq("name", name)
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        row = query.limit(1).execute()
        content = (row.data[0].get("content") if row.data else None) or FALLBACK_PROMPT
    except Exception as e:
        logger.error(f"Failed to load prompt {name}: {e}")
        content = FALLBACK_PROMPT
    _prompt_cache[cache_key] = (now, content)
    return content


def invalidate_prompt_cache(name: str | None = None) -> None:
    if name:
        keys_to_remove = [k for k in _prompt_cache if k == name or k.endswith(f":{name}")]
        for k in keys_to_remove:
            _prompt_cache.pop(k, None)
    else:
        _prompt_cache.clear()


def _recent_thread(db, lead_id: str, limit: int = 6) -> list[dict]:
    # Fetch extra rows so we can filter out [Template] messages without falling short of the requested limit
    raw = (
        db.table("messages")
        .select("direction,content,created_at")
        .eq("lead_id", str(lead_id))
        .order("created_at", desc=True)
        .limit(limit + 10)
        .execute()
        .data
        or []
    )
    filtered = [
        r for r in raw
        if not (r.get("content") or "").strip().startswith("[Template")
    ]
    return filtered[:limit]

_FALLBACK_BY_LANG = {
    "ta": "நன்றி! உங்கள் விசாரணைக்கு விரைவில் பதிலளிப்போம்.",
    "hi": "धन्यवाद! हम जल्द ही आपसे संपर्क करेंगे।",
    "te": "ధన్యవాదాలు! మేము త్వరలో మీకు తిరిగి వస్తాము.",
    "kn": "ಧನ್ಯವಾದಗಳು! ನಾವು ಶೀಘ್ರದಲ್ಲೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತೇವೆ.",
    "ml": "നന്ദി! ഞങ്ങൾ ഉടൻ തന്നെ നിങ്ങളുമായി ബന്ധപ്പെടും.",
    "en": "Thank you for reaching out! We'll get back to you shortly.",
    "tanglish": "Nandri! Naanga seekiram ungale contact pandrom.",
}

# Common Tamil words/suffixes seen in Tanglish (Tamil written in Latin letters).
# Pure Unicode-block detection can't tell Tanglish apart from English since both
# use the Latin script - this closes that gap with a curated keyword heuristic.
_TANGLISH_MARKERS = frozenset({
    "nalla", "romba", "seri", "vanga", "vaanga", "sollunga", "solunga",
    "pannunga", "panren", "panniten", "pannitu", "pannanum", "panna",
    "venum", "vendum", "irukku", "irukka", "iruken", "illa", "illai",
    "epdi", "eppadi", "eppo", "yaaru", "yaru", "enna", "yenna", "kandippa",
    "unga", "ungal", "naanga", "namma", "kekkanum", "paakanum", "paakalam",
    "paathu", "poganum", "poyitu", "irundha", "vela", "jaadhagam",
    "jadhagam", "jothidam", "kalyanam", "thirumanam", "nanba", "nanban",
    "machi", "aiyo", "dhan", "thaan", "nu", "pa", "da",
})


def _dominant_script(text: str) -> str:
    """Return dominant script code based on Unicode block frequency alone
    (no keyword heuristics -- this half of the detection is deterministic
    and reliable, unlike the Tanglish-vs-English guess in _detect_lang)."""
    if not text:
        return "en"
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        if 0x0B80 <= cp <= 0x0BFF:
            counts["ta"] = counts.get("ta", 0) + 1
        elif 0x0C00 <= cp <= 0x0C7F:
            counts["te"] = counts.get("te", 0) + 1
        elif 0x0C80 <= cp <= 0x0CFF:
            counts["kn"] = counts.get("kn", 0) + 1
        elif 0x0D00 <= cp <= 0x0D7F:
            counts["ml"] = counts.get("ml", 0) + 1
        elif 0x0900 <= cp <= 0x097F:
            counts["hi"] = counts.get("hi", 0) + 1
        elif ch.isalpha() and cp < 128:
            counts["en"] = counts.get("en", 0) + 1
    return max(counts, key=counts.__getitem__) if counts else "en"


def _detect_lang(text: str) -> str:
    """Return dominant language code based on Unicode block frequency,
    falling back to a Tanglish keyword heuristic when the script is pure Latin."""
    dominant = _dominant_script(text)
    if dominant == "en":
        tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
        if tokens & _TANGLISH_MARKERS:
            return "tanglish"
    return dominant


_SCRIPT_NAMES = {"ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "hi": "Hindi"}


def _latest_message_script_note(text: str) -> str:
    """Per-turn instruction stating the customer's latest message script. Live-tested
    2026-07-13: does NOT fix silent script switches (0/6 across two prompt placements,
    see subsystem-notes.md) -- the model overrides this instruction in favor of its own
    prior reply style. Kept because it's harmless and doesn't regress the cases that
    already work (explicit switch requests, no-switch). The actual fix for silent
    switches is the post-reply check below (_reply_script_mismatch + regen)."""
    name = _SCRIPT_NAMES.get(_dominant_script(text))
    if name:
        return f"{name} script. Reply in {name} script."
    return "Latin/English script. Do not reply in Tamil script."


_LANGUAGE_SWITCH_REQUEST_RE = re.compile(
    r"\b(in\s+(english|tamil|hindi|telugu|kannada|malayalam)\b"
    r"|reply\s+in\s+(english|tamil|hindi|telugu|kannada|malayalam)\b"
    r"|(english|tamil|hindi|telugu|kannada|malayalam)[\s-]?la\s+(sollunga|solunga|solu))",
    re.IGNORECASE,
)


def _is_explicit_language_switch_request(text: str) -> bool:
    """Matches the same trigger phrasing already given to the model in the LANGUAGE
    RULE prompt (e.g. 'in English please', 'tamil-la sollunga', 'reply in tamil').
    Live-tested 3/3 reliable when the model handles this itself -- the mismatch check
    below must not second-guess it, or it would force a wrong regeneration."""
    return bool(_LANGUAGE_SWITCH_REQUEST_RE.search(text))


def _reply_script_mismatch(customer_message: str, reply_text: str) -> bool:
    """True if the reply's script bucket (Indic vs Latin) doesn't match the customer's
    latest message, and the customer wasn't explicitly requesting a different language
    (that case already works and must be left alone). This is the post-reply catch for
    the silent-switch bug that preemptive prompt instructions could not fix -- see
    subsystem-notes.md 2026-07-13."""
    if _is_explicit_language_switch_request(customer_message):
        return False
    customer_is_indic = _dominant_script(customer_message) != "en"
    reply_is_indic = _dominant_script(reply_text) != "en"
    return customer_is_indic != reply_is_indic


def _regen_target_instruction(customer_message: str) -> str:
    """Target-language phrasing for the isolated regen call below. Must name the
    actual language explicitly ('English or Tanglish') rather than 'Latin script' --
    live-tested 2026-07-13: a vague 'Latin/English script' instruction let the model
    drift into literal Latin (the dead language) once, since any Latin-alphabet
    output technically satisfies 'not Tamil script'."""
    name = _SCRIPT_NAMES.get(_dominant_script(customer_message))
    if name:
        return f"natural {name} script (the way a customer service agent in India would text)"
    return (
        "natural English or Tanglish (the way a customer service agent in India would "
        "text over WhatsApp) -- never a foreign or unrelated language"
    )


_LAST_SEND_ERROR: str | None = None


def get_last_send_error() -> str | None:
    return _LAST_SEND_ERROR


async def send_whatsapp_voice_reply(
    to_phone: str,
    message: str,
    tenant_id: str | None = None,
    phone_number_id: str | None = None,
    speaker: str | None = None,
    db=None,
) -> str | None:
    try:
        from app.services.gemini_client import gemini_text_to_speech, DEFAULT_GEMINI_VOICE
        from app.services.meta_cloud import upload_media_to_meta, send_media_message

        # Gemini's TTS is LLM-native and handles raw Roman-script Tanglish correctly with
        # no language hint (live-tested 2026-07-13/14, see subsystem-notes.md -- Sarvam
        # Bulbul mispronounced the same text as North-Indian-accented regardless of the
        # target_language_code it was given), so there's no pace or language param here --
        # only speaker/voice carries through, using Gemini's own voice names (e.g. "Kore").
        audio_bytes = await gemini_text_to_speech(text=message, voice=speaker or DEFAULT_GEMINI_VOICE)
        if db is not None and tenant_id:
            meter(db, tenant_id, "ai_text_to_speech")
        media_id = await upload_media_to_meta(
            file_bytes=audio_bytes,
            mime_type="audio/mpeg",
            filename="aira-reply.mp3",
            tenant_id=tenant_id,
            phone_number_id=phone_number_id,
        )
        data = await send_media_message(
            to_number=to_phone,
            media_id=media_id,
            wa_type="audio",
            tenant_id=tenant_id,
            phone_number_id=phone_number_id,
        )
        mid = (data.get("messages") or [{}])[0].get("id")
        logger.info(f"Meta voice reply sent to {to_phone}: id={mid}")
        return mid
    except Exception as e:
        logger.error(f"WhatsApp voice reply failed to {to_phone}: {e}")
        return None


async def send_whatsapp(
    to_phone: str,
    message: str,
    tenant_id: str | None = None,
    phone_number_id: str | None = None,
) -> str | None:
    """Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failure.

    phone_number_id pins the sending number to the one that received the inbound
    message; when None, meta_cloud falls back to the tenant's default.
    """
    global _LAST_SEND_ERROR
    try:
        from app.services.meta_cloud import send_text_message
        data = await send_text_message(
            to_number=to_phone, text=message, tenant_id=tenant_id, phone_number_id=phone_number_id
        )
        mid = (data.get("messages") or [{}])[0].get("id")
        logger.info(f"Meta sent to {to_phone}: id={mid}")
        _LAST_SEND_ERROR = None
        return mid
    except Exception as e:
        err_msg = str(e)
        # Surface Meta's actual error body so the UI can show it
        from fastapi import HTTPException as _HTTP
        if isinstance(e, _HTTP):
            err_msg = str(e.detail)[:500]
        _LAST_SEND_ERROR = err_msg
        logger.error(f"Meta send failed to {to_phone}: {err_msg}")
        if tenant_id:
            try:
                from app.services.notify import notify_user
                from app.db.supabase import get_supabase
                db = get_supabase()
                owner = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").limit(1).execute()
                owner_uid = (owner.data[0] if owner.data else {}).get("user_id")
                if owner_uid:
                    notify_user(
                        tenant_id,
                        owner_uid,
                        "system_error",
                        "System API Failure",
                        f"WhatsApp Cloud API send failed: {err_msg}",
                        db=db,
                        dedupe_lead_id="whatsapp_send_failed",
                    )
            except Exception as notify_err:
                logger.warning(f"Failed to notify owner of API failure: {notify_err}")
        return None

async def send_instagram(ig_user_id: str, message: str, tenant_id: str | None = None) -> str | None:
    """Send an Instagram DM via Facebook Graph API (Messenger Platform for Instagram).
    Uses Page Access Token — requires pages_messaging + instagram_manage_messages scope.
    """
    from app.config_dynamic import get_setting
    access_token = get_setting("instagram_access_token", tenant_id=tenant_id)
    if not access_token:
        logger.error(f"instagram_access_token not configured for tenant {tenant_id} — cannot send Instagram DM")
        return None
    try:
        url = "https://graph.facebook.com/v21.0/me/messages"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                params={"access_token": access_token},
                json={
                    "recipient": {"id": ig_user_id},
                    "message": {"text": message},
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            mid = data.get("message_id")
            logger.info(f"Instagram sent to {ig_user_id}: mid={mid}")
            return mid
    except httpx.HTTPStatusError as e:
        logger.error(f"Instagram send failed to {ig_user_id}: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Instagram send failed to {ig_user_id}: {e}")
        return None


async def send_telegram(tg_user_id: str, message: str, tenant_id: str | None = None) -> str | None:
    """Send a Telegram message via Bot API. Returns message ID (as string) or None on failure."""
    from app.config_dynamic import get_setting
    bot_token = get_setting("telegram_bot_token", tenant_id=tenant_id)
    if not bot_token:
        logger.error(f"telegram_bot_token not configured for tenant {tenant_id} — cannot send Telegram DM")
        return None
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": tg_user_id,
                    "text": message,
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                try:
                    desc = resp.json().get("description", resp.text)
                except Exception:
                    desc = resp.text
                logger.error(f"Telegram API send error ({resp.status_code}) to {tg_user_id}: {desc}")
                # 401 = the bot token itself is invalid/revoked → surface in Settings.
                # 403 ("bot was blocked by the user") is per-recipient, NOT a token problem — never flag it.
                if resp.status_code == 401 and tenant_id:
                    try:
                        from app.services.incidents import create_token_incident
                        create_token_incident(get_supabase(), tenant_id, "telegram", desc or "Telegram token invalid")
                    except Exception as inc_err:
                        logger.error(f"Failed to record Telegram token incident: {inc_err}")
                return None
            data = resp.json()
            mid = str(data.get("result", {}).get("message_id"))
            logger.info(f"Telegram sent to {tg_user_id}: mid={mid}")
            return mid
    except httpx.RequestError as req_err:
        logger.error(f"Telegram network send error to {tg_user_id}: {req_err}")
        return None
    except Exception as e:
        logger.error(f"Telegram send failed to {tg_user_id}: {e}")
        return None


async def send_facebook(fb_user_id: str, message: str, tenant_id: str | None = None) -> str | None:
    """Send a Facebook Messenger message via Graph API. Returns message id or None on failure."""
    from app.config_dynamic import get_setting
    access_token = get_setting("facebook_access_token", tenant_id=tenant_id)
    if not access_token:
        logger.error(f"facebook_access_token not configured for tenant {tenant_id} — cannot send Facebook DM")
        return None
    try:
        url = "https://graph.facebook.com/v21.0/me/messages"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                params={"access_token": access_token},
                json={
                    "recipient": {"id": fb_user_id},
                    "message": {"text": message},
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            mid = data.get("message_id")
            logger.info(f"Facebook sent to {fb_user_id}: mid={mid}")
            return mid
    except httpx.HTTPStatusError as e:
        logger.error(f"Facebook send failed to {fb_user_id}: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Facebook send failed to {fb_user_id}: {e}")
        return None


async def generate_reengagement_message(lead_id: str, cadence: str, db=None) -> str:
    db = db or get_supabase()
    lead = (
        db.table("leads")
        .select("name,segment,tenant_id")
        .eq("id", str(lead_id))
        .limit(1)
        .execute()
    )
    lead_data = lead.data[0] if lead.data else {}
    tenant_id = lead_data.get("tenant_id")
    history_rows = list(reversed(_recent_thread(db, lead_id, limit=6)))
    history = "\n".join(
        f"{row.get('direction', 'unknown')}: {row.get('content', '').strip()}"
        for row in history_rows
        if (row.get("content") or "").strip()
    ) or "No prior conversation history available."

    prompt = f"""You write proactive WhatsApp re-engagement messages for a business.

Cadence: {cadence}
Lead name: {lead_data.get("name") or "there"}
Current segment: {lead_data.get("segment") or "C"}
Recent conversation:
{history}

Write a single WhatsApp message under 280 characters.
Be warm, specific, and low-pressure.
Reference the lead's interest naturally and end with one clear next step.
Do not use markdown or quotes."""
    try:
        text = await _llm_complete(prompt, max_tokens=120, tenant_id=tenant_id)
        return text[:280] if len(text) > 280 else text
    except Exception as e:
        logger.error(f"Re-engagement copy failed for lead {lead_id}: {e}")
        return REENGAGEMENT_FALLBACKS.get(cadence, "Hi! Just checking in — happy to help if you have any questions.")


_AI_ESCALATION_RE = re.compile(
    r"""
    (
        # Group 1: Action/Verb followed by Noun (with verb tense suffix support)
        \b(connect|inform|ask|request|transfer|escalat|forward|assign|hand\s+over|refer|alert|confirm|check)\w*\s+(?:[^.?!]*?\s+)?(?:team|owner|admin|staff|human|person|agent|representative|expert|colleague)\b
        |
        # Group 2: Noun followed by action/verb
        \b(?:team|owner|admin|staff|human|person|agent|representative|expert|colleague)\s+(?:[^.?!]*?\s+)?(?:will|would|shall|can|should|is\s+going\s+to)\s+(?:[^.?!]*?\s+)?(?:contact|reach|get\s+back|assist|follow\s+up|connect|call|message|respond|help|take\s+over|write)\w*\b
        |
        # Group 3: Common phrases/actions
        \b(?:get\s+back\s+to\s+you|get\s+in\s+touch|reach\s+out\s+to\s+you|contact\s+you\s+shortly)\b
        |
        \b(?:escalat\w*\s+(?:[^.?!]*?\s+)?(?:query|request|ticket|issue|case))\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_HUMAN_REQUEST_RE = re.compile(
    r"""
    # 1. English Verb + Noun patterns (e.g. speak to owner, talk with team, contact support)
    \b(?:talk|speak|chat|connect|contact|call|get|find|meet|reach|confirm|check)\s+(?:(?:to|with|your|our|my|a|an|the|some|any|this|that|us|me)\s+){0,3}(?:human|person|agent|someone|representative|staff|team|owner|boss|admin|manager|support|caller|telecaller|executive|sir|maam)\b
    |
    # 2. English Pronoun + Action (e.g. connect me, call me, contact me)
    \b(?:call|contact|connect)\s+(?:me|us)\b
    |
    # 3. Romanized Indian / Tanglish / Hinglish / Tenglish noun + regional verb
    \b(?:human|person|agent|team|owner|boss|admin|manager|support|caller|telecaller|sir|maam|insan|aadmi|banda|officer|staff)
        [\s\-]+(?:(?:kitta|se|ku|sath|thru|through|to|with|your|our|my|a|an|the|some|any|ko)\s+){0,2}
        (?:pesa|pesu|baat|kar|karv|karn|call|contact|connect|matlad|mathad|samsar)\w*
    |
    # Standalone Romanized verbs / phrases
    \b(?:pesanum|pesunga|pesalaam|pesanom|pesala|pesu|pesa)\b
    |
    \b(?:matladali|matladandi|matladaali|matladu)\b
    |
    \b(?:mathadabeku|mathadi|mathadu)\b
    |
    \b(?:samsarikkanam|samsarikkoo)\b
    |
    # Direct common Hinglish/Tanglish phrases (e.g. call pannunga, contact karo)
    \b(?:call|contact|connect)\s+(?:pannu|pannunga|karo|karwao|chey|cheyandi|madi|cheyyoo)\b
    |
    \bbaat\s+(?:kar|karna|karvao|karwao|krni|karni|kro)\b
    |
    \bpesa\s+(?:mudiyuma|venum|num)\b
    |
    # 4. Short/Single Word Overrides (case-insensitive boundary checks)
    \b(?:human\s+agent|real\s+person|live\s+agent|customer\s+(?:care|support|service))\b
    |
    \b(?:agent|admin|support|representative|telecaller|caller)\b
    |
    # 5. Native regional scripts (Tamil, Hindi, Telugu, Kannada, Malayalam)
    # Tamil
    பேச\s+(?:வேண்டும்|வேணும்|முடியுமா)|பேசணும்|பேசுங்க|பேசலாமா|அழைக்கவும்|தொடர்பு\s+கொள்ளவும்
    |
    # Hindi
    बात\s+(?:करनी|करवाओ|करो|करना)|कॉल\s+करो|सम्पर्क\s+करो
    |
    # Telugu
    మాట్లాడాలి|మాట్లాడండి|కాల్\s+చేయండి
    |
    # Kannada
    ಮಾತನಾಡಬೇಕು|ಮಾತನಾಡಿ|ಕಾಲ್\s+ಮಾಡಿ
    |
    # Malayalam
    സംസാരിക്കണം|വിളിക്കൂ
    """,
    re.VERBOSE | re.IGNORECASE,
)

_GENERIC_FALLBACK_MARKERS = [
    "we'll get back to you shortly",
    "get back to you shortly",
    "team will get back to you",
]

_TRIGGER_PRIORITY = ["C", "B", "A", "D", "F"]
_TRIGGER_REASONS: dict[str, str] = {
    "C": "User requested a human agent",
    "B": "AI failed to generate a response",
    "A": "AI gave a generic fallback reply",
    "D": "User repeated the same question",
    "F": "AI indicated team will follow up",
}


def _is_similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """True if two messages share ≥threshold fraction of words (rough duplicate check)."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if len(wa) < 3 or len(wb) < 3:
        return False
    return len(wa & wb) / max(len(wa), len(wb)) >= threshold


def _is_generic_fallback(text: str) -> bool:
    t = text.lower()
    return any(marker in t for marker in _GENERIC_FALLBACK_MARKERS)


def _trigger_chat_escalation(
    lead_id: str, reason: str, tenant_id: str, assigned_to: str | None, db,
) -> None:
    """Create a pending chat handover into the shared escalation pool.

    The handover is NOT auto-assigned to a telecaller — it lands unassigned and
    is visible to the admin inbox + every telecaller inbox, so whoever is free
    picks it up. `assigned_to` only carries the lead's existing owner, if any.
    """
    existing = (
        db.table("chat_handovers")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if existing and existing.data:
        return  # already has an open handover

    db.table("leads").update({
        "needs_human_attention": True,
        "escalation_reason": reason,
        "ai_enabled": False,
    }).eq("id", lead_id).execute()

    handover_res = db.table("chat_handovers").insert({
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "assigned_to": assigned_to,
        "reason": reason,
        "status": "pending",
    }).execute()
    handover_id = handover_res.data[0]["id"] if (handover_res and handover_res.data) else "Unknown"
    logger.info(f"Chat handover created for lead {lead_id} — reason: {reason[:60]}")
    try:
        from app.services.notify import notify_pool
        lead_row = (
            db.table("leads").select("name").eq("id", lead_id).maybe_single().execute()
        )
        lead_name = (lead_row.data or {}).get("name") if lead_row else None
        notify_pool(
            tenant_id,
            "handover_new",
            "New handover in pool",
            f"Lead '{lead_name or 'Unknown'}' needs a human — unclaimed. [handover_id:{handover_id}] [lead_id:{lead_id}]",
            db=db,
        )
    except Exception:
        pass


_CATALOG_RECOMMEND_TOOL = {
    "type": "function",
    "function": {
        "name": "recommend_catalog_item",
        "description": (
            "Recommend a catalog item to the customer and send its image. "
            "Call this whenever you mention a specific product/service from the catalog in your reply "
            "— the system will automatically send the item's photo alongside your text. "
            "Only call for items the customer has shown genuine interest in. Do NOT call more than once per reply."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The UUID of the catalog item to recommend",
                }
            },
            "required": ["item_id"],
        },
    },
}


def _load_catalog_ai_rules(db, tenant_id: str) -> dict:
    """Read catalog_ai_rules (the client's own preferences, set via the catalog dashboard)
    merged with defaults, then apply the operator's controls on top: ai_media_recommendations_enabled
    is a hard master switch (client's can_recommend has no effect while it's off), and
    catalog_ai_max_images_ceiling caps max_images_per_reply regardless of what the client
    chose -- the client can pick anything under the ceiling, never over it."""
    defaults = {"can_recommend": True, "can_send_images": True, "max_images_per_reply": 3}
    rules = dict(defaults)
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "catalog_ai_rules")
            .limit(1)
            .execute()
        )
        if row.data:
            stored = json.loads(row.data[0]["value"])
            rules = {**defaults, **stored}
    except Exception:
        logger.warning(f"Failed to load catalog_ai_rules for tenant {tenant_id}")

    operator_enabled = get_setting("ai_media_recommendations_enabled", fallback="true", tenant_id=tenant_id) == "true"
    if not operator_enabled:
        rules["can_recommend"] = False

    ceiling_raw = get_setting("catalog_ai_max_images_ceiling", fallback="5", tenant_id=tenant_id) or "5"
    try:
        ceiling = max(0, int(float(ceiling_raw)))
    except (TypeError, ValueError):
        ceiling = 5
    try:
        client_max = int(rules.get("max_images_per_reply", 3))
    except (TypeError, ValueError):
        client_max = 3
    rules["max_images_per_reply"] = min(client_max, ceiling)

    return rules


async def _build_catalog_context(db, tenant_id: str, message: str) -> tuple[str, list[dict], dict[str, dict], int]:
    """Fetch relevant catalog items for this message and build the prompt context + tool
    definitions, gating disambiguation when multiple variants of one item are in contention.

    Returns (catalog_text_block, tool_definitions, items_by_id, max_images_per_reply).
    catalog_text_block is empty when no items exist or can_recommend is disabled. On any
    retrieval failure, when nothing matches, or when the tenant's ready items aren't fully
    embedded yet, falls back to listing every ready item -- today's original behavior --
    so a provider hiccup or a partially-migrated catalog never hides items from the AI.
    """
    rules = _load_catalog_ai_rules(db, tenant_id)
    if not rules.get("can_recommend"):
        return "", [], {}, 0

    candidates: list[dict] = []
    try:
        unembedded = (
            db.table("catalog_items")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("status", "ready")
            .is_("embedding", "null")
            .execute()
        )
        has_full_embedding_coverage = not (unembedded.count or 0)
    except Exception as e:
        logger.warning(f"Embedding coverage check failed for tenant {tenant_id}, treating as partial: {e}")
        has_full_embedding_coverage = False

    if has_full_embedding_coverage:
        # Smart retrieval is only trustworthy when every ready item has an embedding --
        # match_catalog_items filters to embedding IS NOT NULL, so a partially-embedded
        # catalog would silently hide the un-embedded items the moment ANY item matches
        # elsewhere. Falling back to the full-catalog listing below (same as a zero-match
        # result) guarantees no item is ever invisible, at the cost of losing the smart
        # gate for that one reply.
        try:
            candidates = await match_catalog_items(db, tenant_id, message)
        except Exception as e:
            logger.warning(f"Catalog retrieval failed for tenant {tenant_id}, falling back to full catalog: {e}")

    directive = ""
    if candidates:
        contention = contention_set(candidates)
        gate = classify_gate(contention)
        if gate == "confident":
            items = contention
        elif gate == "same_group":
            items = []
            directive = differing_attribute_directive(contention)
        else:
            items = []
            directive = broad_browse_directive(contention)
    else:
        try:
            res = (
                db.table("catalog_items")
                .select("id,name,item_type,description")
                .eq("tenant_id", tenant_id)
                .eq("status", "ready")
                .order("name")
                .execute()
            )
            items = res.data or []
        except Exception as e:
            logger.warning(f"Failed to load catalog items for tenant {tenant_id}: {e}")
            return "", [], {}, 0

    if not items and not directive:
        return "", [], {}, 0

    items_by_id = {row["id"]: row for row in items}
    item_lines: list[str] = []
    for row in items:
        line = f"  • {row['name']} ({row['item_type']}) [id: {row['id']}]"
        if row.get("description"):
            line += f" — {row['description']}"
        item_lines.append(line)

    text_block = ""
    if item_lines:
        text_block = (
            "\n\nCATALOG:\nWhen the customer asks about what's available or shows interest in a type of "
            "product/service, use your catalog below. Mention items by name — and when you do, call the "
            "recommend_catalog_item tool with the item's [id] so the customer receives its photo automatically.\n"
            + "\n".join(item_lines)
        )
    text_block += directive

    try:
        max_images = max(0, int(rules.get("max_images_per_reply", 3)))
    except (TypeError, ValueError):
        max_images = 3
    tools: list[dict] = []
    if rules.get("can_send_images", True) and items:
        tools = [dict(_CATALOG_RECOMMEND_TOOL)]
        text_block += f"\n\nYou may recommend up to {max_images} item(s) with photos per reply."

    return text_block, tools, items_by_id, max_images


async def generate_reply(
    lead_id: str,
    message: str,
    phone: str | None = None,
    channel: str = "whatsapp",
    ig_user_id: str | None = None,
    context_block: str | None = None,
    tg_user_id: str | None = None,
    fb_user_id: str | None = None,
    phone_number_id: str | None = None,
    inbound_media_type: str | None = None,
) -> None:
    """
    Core pipeline:
    1. Inject knowledge base context
    2. Call the LLM for a reply
    3. Send reply via the matching channel
    4. Score the message and update lead score + segment in DB
    """
    db = get_supabase()

    # Step 0: fetch lead + load module configs
    lead_row = (
        db.table("leads")
        .select("ai_enabled,score,segment,phone,converted_at,tenant_id,assigned_to,name,blocked_at")
        .eq("id", str(lead_id))
        .limit(1)
        .execute()
    )
    lead_data = lead_row.data[0] if lead_row.data else {}
    if lead_data.get("blocked_at"):
        logger.info(f"Lead {lead_id} is blocked — skipping auto-reply")
        return
    tenant_id = lead_data.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id missing from lead_data")
    segment = lead_data.get("segment") or "C"

    # Enforce global AI auto-reply toggle
    _ai_setting = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "ai_auto_reply_enabled")
        .limit(1)
        .execute()
    )
    if _ai_setting.data and _ai_setting.data[0].get("value") == "false":
        logger.info(f"AI auto-reply globally disabled for tenant {tenant_id} — skipping reply")
        return

    inbox_cfg = get_inbox_config(tenant_id)
    escalation_flags: set[str] = set()

    # Trigger C: user explicitly asked for human (always fires, not config-gated)
    if _HUMAN_REQUEST_RE.search(message):
        escalation_flags.add("C")
        logger.info(f"Trigger C: lead {lead_id} asked for human agent")

    # Pre-fetch recent thread (reused for trigger D + LLM chat below)
    recent_thread = _recent_thread(db, lead_id, limit=8)

    # Trigger D: user repeated the same question (AI not resolving it)
    # Skip the first inbound match — it's the current message (already stored before generate_reply runs).
    # We need the PREVIOUS inbound to compare against.
    if "D" in inbox_cfg.get("triggers", []):
        prev_inbounds = [r for r in recent_thread if r.get("direction") == "inbound"]
        prev_inbound = prev_inbounds[1] if len(prev_inbounds) > 1 else None
        if prev_inbound and _is_similar(message, prev_inbound.get("content", "")):
            escalation_flags.add("D")
            logger.info(f"Trigger D: lead {lead_id} repeated same question")
    from app.config_dynamic import get_setting
    global_ai_enabled = get_setting("ai_auto_reply_enabled", fallback="true", tenant_id=tenant_id) == "true"
    if (lead_data and lead_data.get("ai_enabled") is False) or not global_ai_enabled:
        logger.info(f"AI auto-reply is disabled (lead_ai_enabled={lead_data.get('ai_enabled')}, global_ai_enabled={global_ai_enabled}) — skipping auto-reply")
        # Still rescore via Score Engine v2 so admin sees segment updates during manual handling
        try:
            from app.services.scoring_engine import compute_score as _compute_score
            _tid = lead_data.get("tenant_id")
            _sr = await _compute_score(
                message=message, lead_id=str(lead_id), db=db,
                tenant_id=_tid,
            )
            new_score = _sr["score"]
            new_segment = _sr["segment"]
            if _sr.get("intent_reason") == "rejection" and lead_data.get("assigned_to"):
                try:
                    db.table("leads").update({"assigned_to": None}).eq("id", str(lead_id)).execute()
                    lead_data["assigned_to"] = None
                    logger.info(f"Lead {lead_id} unassigned after rejection (AI-disabled path)")
                except Exception:
                    pass
            _score_meta = {
                "new_score": new_score,
                "prev_score": lead_data.get("score", 5),
                "arc_score": _sr["arc_score"],
                "intent_delta": _sr["intent_delta"],
                "engagement": _sr["engagement"],
                "decay": _sr["decay"],
                "intent_reason": _sr["intent_reason"],
                "arc_updated": _sr["arc_updated"],
                "message_snippet": message[:150],
                "channel": channel,
                "reason": "ai_disabled_inbound",
            }
            record_stage_event(
                lead_id,
                from_segment=lead_data.get("segment"),
                to_segment=new_segment,
                event_type="segment_changed" if new_segment != lead_data.get("segment") else "score_updated",
                metadata=_score_meta,
                tenant_id=_tid,
                db=db,
            )
            sync_follow_up_jobs(
                lead_id,
                segment=new_segment,
                phone=lead_data.get("phone") or phone,
                converted_at=lead_data.get("converted_at"),
                ai_enabled=False,
                reason="ai_disabled",
                tenant_id=_tid,
                db=db,
            )
        except Exception as e:
            logger.error(f"Scoring update failed (takeover mode) for lead {lead_id}: {e}")
        return

    # Campaign scoping: which campaign did this lead come from? Drives both the
    # KB filter and the prompt focus. None = cold lead → unscoped (full KB) as before.
    if not check_quota(db, tenant_id, "ai_reply"):
        logger.info(f"AI reply skipped for tenant {tenant_id}: ai_reply quota exhausted")
        return

    campaign_tag_id, campaign_name = _resolve_campaign(db, lead_id)

    # RAG: retrieve the most relevant knowledge-base chunks for THIS message
    try:
        context_text = await get_knowledge_context(
            tenant_id,
            query=message,
            campaign_tag_id=campaign_tag_id,
        )
    except Exception as e:
        logger.warning(f"Knowledge context fetch failed for lead {lead_id}: {e}")
        context_text = ""

    catalog_tools: list[dict] = []
    catalog_items_by_id: dict[str, dict] = {}
    catalog_max_images = 0
    try:
        catalog_context, catalog_tools, catalog_items_by_id, catalog_max_images = await _build_catalog_context(
            db, tenant_id, message
        )
    except Exception:
        catalog_context = ""
        logger.warning(f"Catalog context build failed for tenant {tenant_id}")

    try:
        system_prompt = _get_prompt(f"{channel}_reply", tenant_id=lead_data.get("tenant_id"))
        if campaign_name:
            system_prompt += (
                f'\n\nCAMPAIGN CONTEXT:\nThis lead came from the "{campaign_name}" campaign. '
                "Assume their questions relate to that unless they clearly ask about something else. "
                "If they ask about something outside it, offer to connect them with the team."
            )
        if context_text:
            system_prompt += "\n\nKNOWLEDGE BASE:\nUse the following excerpts to answer the user's question accurately. If the answer is not in the excerpts, say you will connect them with a team member.\n\n" + context_text

        lead_name = (lead_data.get("name") or "").strip()
        lead_segment = lead_data.get("segment") or "C"
        summary = _fetch_conversation_summary(db, lead_id)

        lead_facts: list[str] = []
        if lead_name:
            lead_facts.append(f"Lead name: {lead_name}")
        lead_facts.append(f"Current segment: {lead_segment} (A=hot, B=warm, C=cold, D=disqualified)")
        if summary:
            lead_facts.append(f"Earlier conversation summary:\n{summary}")
        system_prompt += "\n\nLEAD CONTEXT:\n" + "\n".join(lead_facts)

        system_prompt += (
            "\n\nLANGUAGE RULE: Reply in the SAME language style the user just wrote in. "
            "Tamil script -> reply in Tamil script. English -> reply in English. "
            "Tanglish (Tamil words spelled in English letters, e.g. 'eppo varuvinga', 'jaadhagam paakanum') "
            "-> reply in Tanglish too - do NOT convert it to pure Tamil script or to formal English. "
            "If the customer's latest message explicitly requests a different language (e.g. 'in English please', "
            "'tamil-la sollunga', 'reply in tamil'), you MUST fully switch to that requested language for this "
            "reply and continue in it afterward, overriding whatever style earlier messages in the conversation used."
        )
        system_prompt += (
            f"\n\nCUSTOMER'S LATEST MESSAGE SCRIPT: {_latest_message_script_note(message)}"
        )

        if catalog_context:
            system_prompt += catalog_context

        # recent_thread already fetched at step 0 (reuse - no extra DB call)
        chat_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for row in reversed(recent_thread):  # oldest first
            content = (row.get("content") or "").strip()
            if not content:
                continue
            role = "assistant" if row.get("direction") == "outbound" else "user"
            chat_messages.append({"role": role, "content": content})

        # No code-injected tag on the user turn itself: the CUSTOMER'S LATEST MESSAGE
        # SCRIPT line already added to system_prompt above covers the one thing that's
        # reliably checkable (Tamil-block vs Latin script). We deliberately do NOT also
        # inject _detect_lang()'s Tanglish-vs-English keyword guess here -- that half is
        # fuzzy, and the model reading the raw words is reliably better at that call
        # than a hardcoded keyword list.
        if not chat_messages or chat_messages[-1].get("role") != "user" or chat_messages[-1].get("content") != message:
            chat_messages.append({"role": "user", "content": message})

        catalog_images_to_send: list[tuple[str, bytes]] = []  # (filename, image_bytes)

        if catalog_tools:
            reply_text, tool_calls = await _llm_chat_with_tools(
                chat_messages, tools=catalog_tools, max_tokens=600, tenant_id=tenant_id,
            )
            reply_text = reply_text.strip()

            # Handle tool calls — the model asked to recommend catalog items
            for tc in tool_calls:
                func = tc.get("function") or {}
                if func.get("name") != "recommend_catalog_item":
                    continue
                try:
                    args = json.loads(func.get("arguments") or "{}")
                except (ValueError, TypeError):
                    continue
                item_id = args.get("item_id")
                if not item_id or item_id not in catalog_items_by_id:
                    continue

                item = catalog_items_by_id[item_id]
                logger.info(
                    "Catalog recommendation: lead %s -> item %s (%s)", lead_id, item["name"], item_id
                )
                # Append a natural confirmation sentence to the reply if we're sending photos
                # — only if no customer-facing text was generated by the model.
                if not reply_text:
                    reply_text = f"Here's our {item['name']}:"

                # Load the item's images from the catalog-media storage bucket so we can
                # send them as WhatsApp attachments, in the client's ranked order, capped
                # at max_images_per_reply.
                try:
                    media_rows = (
                        db.table("catalog_media")
                        .select("id,storage_path,label")
                        .eq("catalog_item_id", item_id)
                        .eq("tenant_id", tenant_id)
                        .order("sort_order")
                        .limit(catalog_max_images)
                        .execute()
                    )
                    for mrow in (media_rows.data or []):
                        path = mrow["storage_path"]
                        label = mrow["label"] or item["name"]
                        file_bytes = db.storage.from_("catalog-media").download(path)
                        catalog_images_to_send.append((label, file_bytes))
                except Exception as media_err:
                    logger.warning("Failed to load catalog media for item %s: %s", item_id, media_err)
        else:
            reply_text = (await _llm_chat(chat_messages, max_tokens=600, tenant_id=tenant_id)).strip()

        is_ai = True
        reply_source = "knowledge" if context_text else "ai"

        if not reply_text:
            reply_text = _FALLBACK_BY_LANG.get(_detect_lang(message), _FALLBACK_BY_LANG["en"])
        elif _reply_script_mismatch(message, reply_text):
            # Preemptive prompt instructions (LANGUAGE RULE + the per-turn script note
            # above) do not reliably stop silent script-switch anchoring -- live-tested
            # 0/6, see subsystem-notes.md 2026-07-13. This catches it after generation,
            # before anything is sent, and asks for one corrected regeneration.
            #
            # The regen call deliberately carries NO conversation history and is framed
            # as an isolated translation task, not "continue the chat" -- live-tested
            # 2026-07-13: feeding the wrong reply back in as part of the same history
            # (i.e. asking the model to "redo" its own last turn) mostly failed (1/6,
            # the anchor re-triggers even with an explicit correction). An isolated
            # rewrite-only call with no prior turns to anchor to fixed it 10/10. The
            # target language must be named explicitly ("English or Tanglish"), not
            # "Latin script" -- a vague script-only instruction let the model drift
            # into literal Latin (the dead language) once, since any Latin-alphabet
            # text technically satisfies "not Tamil script".
            try:
                regen_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are a translator. Rewrite the following WhatsApp reply so it is in "
                            f"{_regen_target_instruction(message)}. Keep the same meaning, tone, and "
                            "length. Output ONLY the rewritten reply, nothing else."
                        ),
                    },
                    {"role": "user", "content": reply_text},
                ]
                regenerated = (await _llm_chat(regen_messages, max_tokens=600, tenant_id=tenant_id)).strip()
                if regenerated:
                    if _reply_script_mismatch(message, regenerated):
                        logger.warning(f"Script-mismatch regen still mismatched for lead {lead_id}")
                    reply_text = regenerated
            except Exception as regen_err:
                logger.warning(f"Script-mismatch regeneration failed for lead {lead_id}: {regen_err}")

        # Trigger A: AI gave a generic fallback reply
        if _is_generic_fallback(reply_text):
            escalation_flags.add("A")
            logger.info(f"Trigger A: lead {lead_id} received generic fallback reply")
        # Trigger F: AI reply contained escalation phrases
        if _AI_ESCALATION_RE.search(reply_text):
            escalation_flags.add("F")

    except Exception as e:
        logger.error(f"LLM reply failed for lead {lead_id}: {e}")
        reply_text = _FALLBACK_BY_LANG.get(_detect_lang(message), _FALLBACK_BY_LANG["en"])
        is_ai = False
        reply_source = "ai"
        # Trigger B: AI/LLM exception - escalate so a human can pick up
        escalation_flags.add("B")
        logger.info(f"Trigger B: lead {lead_id} LLM exception - {e}")

    # Step 3: Dispatch to the correct channel
    outbound_media_type: str | None = None
    outbound_media_mime_type: str | None = None
    if channel == "instagram":
        sid = await send_instagram(ig_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if ig_user_id else None
    elif channel == "telegram":
        sid = await send_telegram(tg_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if tg_user_id else None
    elif channel == "facebook":
        sid = await send_facebook(fb_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if fb_user_id else None
    else:
        _wa_phone = phone or lead_data.get("phone")
        sid = None
        voice_reply_enabled = get_setting("ai_voice_reply_enabled", fallback="false", tenant_id=tenant_id) == "true"
        if _wa_phone and voice_reply_enabled and inbound_media_type == "audio":
            from app.services.gemini_client import DEFAULT_GEMINI_VOICE
            voice_speaker = get_setting("ai_voice_reply_speaker", fallback=DEFAULT_GEMINI_VOICE, tenant_id=tenant_id) or DEFAULT_GEMINI_VOICE
            sid = await send_whatsapp_voice_reply(
                _wa_phone,
                reply_text,
                tenant_id=lead_data.get("tenant_id"),
                phone_number_id=phone_number_id,
                speaker=voice_speaker,
                db=db,
            )
            if sid:
                outbound_media_type = "audio"
                outbound_media_mime_type = "audio/mpeg"
        if _wa_phone and not sid:
            sid = await send_whatsapp(_wa_phone, reply_text, tenant_id=lead_data.get("tenant_id"), phone_number_id=phone_number_id)

        # Send catalog recommendation images as follow-up WhatsApp media
        if _wa_phone and sid and catalog_images_to_send:
            from app.services.meta_cloud import upload_media_to_meta, send_media_message
            for img_filename, img_bytes in catalog_images_to_send[:catalog_max_images]:
                try:
                    media_id = await upload_media_to_meta(
                        file_bytes=img_bytes,
                        mime_type="image/jpeg",
                        filename=img_filename,
                        tenant_id=lead_data.get("tenant_id"),
                        phone_number_id=phone_number_id,
                    )
                    await send_media_message(
                        to_number=_wa_phone,
                        media_id=media_id,
                        wa_type="image",
                        caption=img_filename,
                        tenant_id=lead_data.get("tenant_id"),
                        phone_number_id=phone_number_id,
                    )
                    db.table("messages").insert({
                        "lead_id": str(lead_id),
                        "direction": "outbound",
                        "channel": channel,
                        "content": f"[Catalog image: {img_filename}]",
                        "is_ai_generated": True,
                        "reply_source": "ai",
                        "tenant_id": tenant_id,
                        "media_type": "image",
                        "media_mime_type": "image/jpeg",
                    }).execute()
                    meter(db, tenant_id, "ai_media_recommendation")
                except Exception as img_err:
                    logger.warning("Catalog image send failed for lead %s: %s", lead_id, img_err)

    # Track-only usage metering: count once per AI-generated reply that was
    # actually sent (non-None message id). Never blocks/caps — best-effort only.
    if is_ai and sid is not None:
        meter(db, tenant_id, "ai_reply")

    # Step 4: Store outbound message
    if channel == "telegram":
        sid_field = "tg_message_id"
    elif channel == "facebook":
        sid_field = "fb_message_id"
    elif channel == "whatsapp":
        sid_field = "meta_message_id"
    else:
        sid_field = "meta_message_id"  # instagram uses meta_message_id
    outbound_row = {
        "lead_id": str(lead_id),
        "direction": "outbound",
        "channel": channel,
        "content": reply_text,
        "is_ai_generated": is_ai,
        "reply_source": reply_source,
        "tenant_id": tenant_id,
        sid_field: sid,
    }
    if outbound_media_type:
        outbound_row["media_type"] = outbound_media_type
        outbound_row["media_mime_type"] = outbound_media_mime_type
    db.table("messages").insert(outbound_row).execute()

    # Step 5: Score Engine v2 — composite arc + intent + engagement (no gate)
    new_segment = segment  # fallback if scoring fails
    new_score = lead_data.get("score", 5)
    try:
        from app.services.scoring_engine import compute_score
        from datetime import datetime, timezone

        score_result = await compute_score(
            message=message,
            lead_id=str(lead_id),
            db=db,
            tenant_id=tenant_id,
        )
        new_score = score_result["score"]
        new_segment = score_result["segment"]

        _score_meta = {
            "new_score": new_score,
            "prev_score": lead_data.get("score", 5),
            "arc_score": score_result["arc_score"],
            "intent_delta": score_result["intent_delta"],
            "engagement": score_result["engagement"],
            "decay": score_result["decay"],
            "intent_reason": score_result["intent_reason"],
            "arc_updated": score_result["arc_updated"],
            "message_snippet": message[:150],
            "channel": channel,
            "broadcast_id": None,
        }
        record_stage_event(
            lead_id,
            from_segment=lead_data.get("segment"),
            to_segment=new_segment,
            event_type="segment_changed" if new_segment != lead_data.get("segment") else "score_updated",
            metadata=_score_meta,
            tenant_id=tenant_id,
            db=db,
        )
        if score_result.get("intent_reason") == "rejection" and lead_data.get("assigned_to"):
            try:
                db.table("leads").update({"assigned_to": None}).eq("id", str(lead_id)).execute()
                lead_data["assigned_to"] = None
                logger.info(f"Lead {lead_id} unassigned after rejection")
            except Exception:
                pass
        if not lead_data.get("assigned_to"):
            assigned_caller = maybe_assign_lead(
                str(lead_id), tenant_id, new_segment, channel,
                reason="scored", score=new_score,
            )
            if assigned_caller:
                lead_data["assigned_to"] = assigned_caller
    except Exception as e:
        logger.error(f"Scoring update failed for lead {lead_id}: {e}")

    sync_follow_up_jobs(
        lead_id,
        segment=new_segment,
        phone=lead_data.get("phone") or phone,
        converted_at=lead_data.get("converted_at"),
        ai_enabled=lead_data.get("ai_enabled", True),
        reason=f"{channel}_reply",
        tenant_id=tenant_id,
        db=db,
    )

    # Step 6: Fire inbox escalation — trigger-based only (A/B/C/D/F), no segment gate.
    # Creates an UNASSIGNED pending handover → shared pool (admin + any telecaller).
    active_triggers = [
        t for t in _TRIGGER_PRIORITY
        if t in escalation_flags and should_escalate_to_inbox(inbox_cfg, t, channel)
    ]
    if active_triggers:
        primary = active_triggers[0]
        try:
            _trigger_chat_escalation(
                lead_id=str(lead_id),
                reason=_TRIGGER_REASONS[primary],
                tenant_id=tenant_id,
                assigned_to=lead_data.get("assigned_to"),
                db=db,
            )
            logger.info(f"Inbox escalation fired for lead {lead_id} — trigger {primary}")
        except Exception as e:
            logger.error(f"Inbox escalation failed for lead {lead_id}: {e}")
