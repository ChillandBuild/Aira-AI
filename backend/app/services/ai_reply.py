import logging
import re
import time
import httpx
from app.db.supabase import get_supabase
from app.services.growth import record_stage_event, sync_follow_up_jobs
from app.services.segmentation import score_to_segment, parse_thresholds
from app.services.knowledge_service import get_knowledge_context
from app.services.assignment import (
    maybe_assign_lead,
    get_inbox_config,
    should_escalate_hot_lead,
    should_escalate_to_inbox,
)
from app.services.entitlements import meter, check_quota

logger = logging.getLogger(__name__)

from app.services.sarvam_client import sarvam_chat_completion
_REPLY_MODEL = "sarvam-30b"


async def _llm_complete(prompt: str, max_tokens: int = 300, tenant_id: str | None = None) -> str:
    return await sarvam_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=_REPLY_MODEL,
        temperature=0.4,
        max_tokens=max_tokens,
        tenant_id=tenant_id,
    )


async def _llm_chat(messages: list[dict], max_tokens: int = 300, tenant_id: str | None = None) -> str:
    return await sarvam_chat_completion(
        messages=messages,
        model=_REPLY_MODEL,
        temperature=0.4,
        max_tokens=max_tokens,
        tenant_id=tenant_id,
    )


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
    return (
        db.table("messages")
        .select("direction,content,created_at")
        .eq("lead_id", str(lead_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )

_LANG_NAMES = {
    "ta": "Tamil",
    "hi": "Hindi",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "en": "English",
    "tanglish": "Tanglish (Tamil words spelled in English letters - reply the same way, do not switch to Tamil script or formal English)",
}

_FALLBACK_BY_LANG = {
    "ta": "நன்றி! உங்கள் விசாரணைக்கு விரைவில் பதிலளிப்போம்.",
    "hi": "धन्यवाद! हम जल्द ही आपसे संपर्क करेंगे।",
    "te": "ధన్యవాదాలు! మేము త్వరలో మీకు తిరిగి వస్తాము.",
    "kn": "ಧನ್ಯವಾದಗಳು! ನಾವು ಶೀಘ್ರದಲ್ಲೇ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತೇವೆ.",
    "ml": "നന്ദി! ഞങ്ങൾ ഉടൻ തന്നെ നിങ്ങളുമായി ബന്ധപ്പെടും.",
    "en": "Thank you for reaching out! We'll get back to you shortly.",
    "tanglish": "Nandri! Naanga seekiram unga kooda contact pannuvom.",
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


def _detect_lang(text: str) -> str:
    """Return dominant language code based on Unicode block frequency,
    falling back to a Tanglish keyword heuristic when the script is pure Latin."""
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
    dominant = max(counts, key=counts.__getitem__) if counts else "en"
    if dominant == "en":
        tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
        if tokens & _TANGLISH_MARKERS:
            return "tanglish"
    return dominant


_LAST_SEND_ERROR: str | None = None


def get_last_send_error() -> str | None:
    return _LAST_SEND_ERROR


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


_ESCALATION_PHRASES = [
    "connect you with our team",
    "connect them with a team member",
    "let me connect",
    "our team will",
    "team will reach out",
    "team member will",
    "team will get back",
]

_HUMAN_REQUEST_RE = re.compile(
    r"""
    \b(
        (?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+)?
            (?:human|person|agent|someone|representative|staff|team\s+member)
        |
        (?:want|need|like)\s+(?:to\s+)?(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+)?
            (?:human|person|agent|someone|representative)
        |
        connect\s+me\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+)?
            (?:human|person|agent|team|someone|representative)
        |
        (?:get|find)\s+me\s+(?:a\s+)?(?:human|person|agent)
        |
        human\s+agent | real\s+person | live\s+agent
        |
        customer\s+(?:care|support|service)
        |
        can\s+i\s+speak | call\s+me
    )\b
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

    _raw_reply = ""  # holds unstripped LLM output for the defensive [COLLECT_DONE] strip below
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
            "Never switch styles unless the user explicitly asks you to."
        )

        # recent_thread already fetched at step 0 (reuse - no extra DB call)
        chat_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for row in reversed(recent_thread):  # oldest first
            content = (row.get("content") or "").strip()
            if not content:
                continue
            role = "assistant" if row.get("direction") == "outbound" else "user"
            chat_messages.append({"role": role, "content": content})

        # Inject language hint directly into the final user turn - strongest signal,
        # overrides any knowledge-base language that may dominate the system prompt.
        _user_lang_name = _LANG_NAMES.get(_detect_lang(message), "English")
        _tagged_message = f"[Respond in {_user_lang_name}] {message}"
        if not chat_messages or chat_messages[-1].get("role") != "user" or chat_messages[-1].get("content") != message:
            chat_messages.append({"role": "user", "content": _tagged_message})
        else:
            chat_messages[-1]["content"] = _tagged_message

        _raw_reply = await _llm_chat(chat_messages, max_tokens=600, tenant_id=tenant_id)
        is_ai = True
        reply_source = "knowledge" if context_text else "ai"

        # Defensive strip: some tenants' custom AI Tune prompts (stored in the DB, not
        # this code) may still instruct the model to end replies with [COLLECT_DONE]{...}
        # from the old data-collection feature (its parser/save logic is removed below).
        # Keep stripping so a stale stored prompt can't leak the raw tag to a customer.
        _display_text = re.sub(r'^\s*\[COLLECT_DONE\]\s*\{.*\}\s*$', '', _raw_reply.strip(), flags=re.DOTALL).strip()
        reply_text = _display_text if _display_text != _raw_reply else _raw_reply
        if not reply_text:
            reply_text = "Thank you — we've got all your details. We'll be in touch shortly."

        # Trigger A: AI gave a generic fallback reply
        if _is_generic_fallback(reply_text):
            escalation_flags.add("A")
            logger.info(f"Trigger A: lead {lead_id} received generic fallback reply")
        # Trigger F: AI reply contained escalation phrases
        if any(phrase in reply_text.lower() for phrase in _ESCALATION_PHRASES):
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
    if channel == "instagram":
        sid = await send_instagram(ig_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if ig_user_id else None
    elif channel == "telegram":
        sid = await send_telegram(tg_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if tg_user_id else None
    elif channel == "facebook":
        sid = await send_facebook(fb_user_id, reply_text, tenant_id=lead_data.get("tenant_id")) if fb_user_id else None
    else:
        _wa_phone = phone or lead_data.get("phone")
        sid = await send_whatsapp(_wa_phone, reply_text, tenant_id=lead_data.get("tenant_id"), phone_number_id=phone_number_id) if _wa_phone else None

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
    db.table("messages").insert({
        "lead_id": str(lead_id),
        "direction": "outbound",
        "channel": channel,
        "content": reply_text,
        "is_ai_generated": is_ai,
        "reply_source": reply_source,
        "tenant_id": tenant_id,
        sid_field: sid,
    }).execute()

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
