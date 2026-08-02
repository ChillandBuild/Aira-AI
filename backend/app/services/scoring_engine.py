"""
AIRA Score Engine v2

Composite score = clamp(arc + intent_delta + engagement, 1, 10)

  arc_score        — LLM scores the conversation thread, fires on every inbound
                     message (no periodic gate — see decisions/log.md 2026-08-02).
  intent_delta     — Rule-based instant signal on the current message. -3..+2.
                     Rejection phrases bypass everything → immediate score 1, segment D.
  engagement      — Rule-based engagement signal on message history. 0..+2.
                     Reply volume, message substance, media shared.

No time-based decay: score and segment only move on something the lead actually
said. Going silent never changes either, by design.

Segment lock: upgrade always immediate. Small drop (1 segment) needs 2 consecutive
confirmations. Big drop (2+ segments) or rejection phrase: immediate.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.services.segmentation import score_to_segment

logger = logging.getLogger(__name__)

from app.services.gemini_client import gemini_chat_completion
_MODEL = "gemini-3.1-flash-lite"

# ── Intent signal patterns ────────────────────────────────────────────────────

_REJECTION_PATTERNS = [
    r"\bnot interested\b",
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\bno thanks\b",
    r"\bno thank you\b",
    r"\bwrong number\b",
    r"\bdo not contact\b",
    r"\bdon'?t contact\b",
    r"\bdo not message\b",
    r"\bdon'?t message\b",
    r"\bdo not msg\b",
    r"\bdon'?t msg\b",
    r"\bdo not text\b",
    r"\bdon'?t text\b",
    r"\bstop messaging\b",
    r"\bstop texting\b",
    r"\bdo not call\b",
    r"\bdon'?t call\b",
    r"\bstop calling\b",
    r"\bplease remove\b",
    r"\bremove my number\b",
    r"\bnot needed\b",
    r"\bnot required\b",
    r"\bno interest\b",
    r"\bleave me alone\b",
    r"\bopt.?out\b",
    # Tamil
    r"வேண்டாம்",
    r"நிறுத்துங்கள்",
    r"தேவையில்லை",
    r"விலகு",
    r"தொந்தரவு செய்யாதீர்கள்",
    r"கூப்பிடாதீர்கள்",
    # Tanglish (romanized Tamil — spelling varies a lot in real chat,
    # these cover the most common forms seen on WhatsApp)
    r"\bvena+m\b",
    r"\bvenda\b",
    r"\bthevai\s*illa(i)?\b",
    r"\b(message|msg|call)\s*panna{1,2}(dh|th)(ee|e|i)nga\b",
    # Hindi
    r"नहीं चाहिए",
    r"रुको",
    r"बंद करो",
    r"ज़?रूरत नहीं",
    r"दिलचस्पी नहीं",
    r"मैसेज मत करो",
    r"कॉल मत करो",
    # Hinglish (romanized Hindi)
    r"\bzaroor?at nahi\b",
    r"\binterest nahi\b",
    r"\b(message|msg|call) mat karo\b",
    # Telugu — core rejection words (vaddu/aapandi are unambiguous; verify
    # phrasing with a native speaker before relying on this for compliance)
    r"వద్దు",
    r"ఆపండి",
    r"అవసరం లేదు",
    # Kannada — same caveat as Telugu above
    r"ಬೇಡ",
    r"ನಿಲ್ಲಿಸಿ",
    r"ಅಗತ್ಯವಿಲ್ಲ",
    # Malayalam — same caveat as Telugu above
    r"വേണ്ട",
    r"നിർത്തുക",
    r"ആവശ്യമില്ല",
]

_HIGH_INTENT_PATTERNS = [
    r"\bbook\b",
    r"\bconfirm\b",
    r"\bproceed\b",
    r"\bpayment\b",
    r"\bpay\b",
    r"\bprice\b",
    r"\bcost\b",
    r"\bhow much\b",
    r"\bregister\b",
    r"\bschedule\b",
    r"\bslot\b",
    # Tamil
    r"பதிவு",
    r"விலை",
    r"கட்டணம்",
    r"book பண்ண",
    r"confirm பண்ண",
    # Hindi
    r"बुक करना",
    r"कीमत",
    r"भुगतान",
]

_INFO_PROVIDED_PATTERNS = [
    r"\bmy name is\b",
    r"\bname\s*[:\-]",
    r"\bgotram\b",
    r"\bnakshatram\b",
    r"\brasi\b",
    r"\brashi\b",
    r"\baddress\b",
    r"\bpincode\b",
    # Tamil equivalents
    r"பெயர்",
    r"பேர்",
    r"முகவரி",
    r"அட்ரஸ்",
    r"கோத்திரம்",
    r"நட்சத்திரம்",
    r"ராசி",
    r"பின்கோடு",
]

_REJECTION_SENTINEL = -99


def _compute_intent_delta(message: str, flow_state: str, via_ad_referral: bool = False) -> tuple[int, str]:
    """
    Returns (delta, reason).
    delta is -2..+2 or _REJECTION_SENTINEL for immediate D override.
    Max +2 so arc must carry the weight to reach Hot (A≥9).

    via_ad_referral: True when this message is Meta's own click-to-WhatsApp
    auto-fill text (the lead tapped an ad and hit Send, didn't compose it).
    Mirrors _score_arc's prompt rule -- never credit the lead for Meta's own
    copy, even if it's long or contains a high-intent keyword like "book".
    Rejection detection still runs first: an auto-filled message won't
    realistically match those patterns, but skipping that check to save a
    lookup isn't worth the risk of missing a real rejection.
    """
    for pat in _REJECTION_PATTERNS:
        if re.search(pat, message, re.IGNORECASE):
            return _REJECTION_SENTINEL, "rejection"

    if via_ad_referral:
        return 0, "ad_prefilled"

    delta = 0
    reasons: list[str] = []

    for pat in _HIGH_INTENT_PATTERNS:
        if re.search(pat, message, re.IGNORECASE):
            delta += 1
            reasons.append("high_intent")
            break

    for pat in _INFO_PROVIDED_PATTERNS:
        if re.search(pat, message, re.IGNORECASE):
            delta += 1
            reasons.append("info_provided")
            break

    if len(message.strip()) > 60:
        delta += 1
        reasons.append("detailed_message")

    return max(-3, min(2, delta)), ",".join(reasons) or "neutral"


def _compute_engagement(lead_id: str, db) -> int:
    """Rule-based engagement score from message history. 0..+2."""
    try:
        msgs = (
            db.table("messages")
            .select("content,media_url")
            .eq("lead_id", str(lead_id))
            .eq("direction", "inbound")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        ).data or []
    except Exception:
        return 0

    if not msgs:
        return 0

    score = 0

    if len(msgs) >= 5:
        score += 1

    avg_len = sum(len((m.get("content") or "").strip()) for m in msgs) / len(msgs)
    if avg_len >= 40:
        score += 1

    if any(m.get("media_url") for m in msgs):
        score += 1

    return min(2, score)


_ARC_RUBRIC_DEFAULT = """
9-10: High intent — explicitly asked for pricing/payment, confirmed participation, ready to proceed
7-8:  Warm — asking detailed questions, comparing options, providing requested info, multiple engaged follow-ups
5-6:  Neutral — general inquiry, first contact, initial greetings/salutations (e.g. "Hi", "Hello", "Vanakkam", "Namaste"), short acknowledgments with some context
3-4:  Lukewarm — vague replies, no follow-up to questions, low engagement
1-2:  Low intent — unresponsive, dismissive, irrelevant, or repeated single-word replies with no context (excluding greetings)
"""

_AD_PREFILL_MARKER = "[ad-prefilled entry message]"
_ESCALATION_MARKER = "[handover follow-up]"


async def _score_arc(conversation: str, tenant_id: str | None, fallback: int = 5) -> int:
    """LLM scores the conversation thread for overall purchase intent."""
    try:
        from app.config_dynamic import get_setting
        custom = get_setting("scoring_rubric", tenant_id=tenant_id) if tenant_id else None
        rubric = (custom or _ARC_RUBRIC_DEFAULT).strip()
    except Exception:
        rubric = _ARC_RUBRIC_DEFAULT.strip()

    prompt = (
        f"You score sales conversations for purchase intent (1-10).\n\n"
        f"Rubric:\n{rubric}\n\n"
        f"Conversation:\n{conversation}\n\n"
        f"LANGUAGE & GREETING RULES:\n"
        f"- Initial greetings, salutations, or first contact messages (e.g., \"Hi\", \"Hello\", \"Namaste\", \"Vanakkam\", \"Hi sir\") must be scored as 5 or 6 (Neutral), NOT penalized as low-intent or single-word replies.\n"
        f"- A message requesting communication in a regional language (Tamil, Hindi, Telugu, etc.) is an engagement signal — never score below 5 for it.\n"
        f"- Single-word answers in regional languages (e.g. \"சிம்மம்\", \"பூரம்\", \"ஆமா\") must be evaluated for their semantic intent, not penalised for brevity or language.\n"
        f"- Non-English intent = same weight as English equivalent.\n"
        f"- A line prefixed with \"{_AD_PREFILL_MARKER}\" is Meta's own click-to-WhatsApp auto-fill text — the lead tapped an ad and hit Send, they did not compose it. Treat it as a neutral first-contact signal only (score 5-6), never as evidence of the lead's own composed interest, even if it contains intent-sounding words like \"detailed\" or \"urgent\".\n"
        f"- A line prefixed with \"{_ESCALATION_MARKER}\" is the lead chasing a human callback they were already promised (e.g. \"still no one contacted me\", \"when will they call\"). This is frustration about response time, NOT a signal about product interest — do not let it lower the score. Weigh the conversation's non-escalation lines to judge actual purchase intent instead.\n\n"
        f"Score the OVERALL purchase intent trajectory of this conversation. "
        f"Consider the full arc — not just the last message. "
        f"Reply with ONLY a single integer 1-10."
    )
    try:
        raw = await gemini_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=_MODEL,
            temperature=0.0,
            max_tokens=8,
            tenant_id=tenant_id,
            purpose="scoring",
        )
        match = re.search(r'\d+', raw.strip())
        return max(1, min(10, int(match.group()))) if match else fallback
    except Exception as e:
        logger.error(f"Arc scoring failed: {e}")
        return fallback


def _apply_segment_lock(
    proposed: str,
    current: str,
    drop_count: int,
    big_drop: bool,
) -> tuple[str, int]:
    """
    Returns (final_segment, new_drop_count).

    Upgrade:            always immediate, resets counter.
    Small drop (1 seg): needs 2 consecutive proposed drops.
    Big drop (2+ segs)  or rejection: immediate, resets counter.
    """
    order = {"A": 4, "B": 3, "C": 2, "D": 1}
    diff = order.get(current, 2) - order.get(proposed, 2)

    if diff <= 0:
        return proposed, 0

    if big_drop or diff >= 2:
        return proposed, 0

    new_count = drop_count + 1
    if new_count >= 2:
        return proposed, 0
    return current, new_count


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


async def compute_score(
    message: str,
    lead_id: str,
    db,
    tenant_id: str | None = None,
) -> dict:
    """
    Main entry point. Computes composite score, persists to DB, returns breakdown.

    Segment/score only move on something the lead actually said (arc, intent,
    engagement) — going silent never changes either, by design. No time-based
    decay term.

    Returns:
        score, segment, arc_score, intent_delta, engagement,
        intent_reason, arc_updated, segment_drop_count
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── 1. Load global lead state ──────────────────────────────────────────────
    lead_row = (
        db.table("leads")
        .select(
            "score,score_arc,score_intent_delta,"
            "score_engagement,segment,segment_drop_count"
        )
        .eq("id", str(lead_id))
        .limit(1)
        .execute()
    )
    data = lead_row.data[0] if lead_row.data else {}

    global_arc     = data.get("score_arc") or 5
    global_segment = data.get("segment") or "C"
    global_drop    = data.get("segment_drop_count") or 0

    current_arc  = global_arc
    current_seg  = global_segment
    current_drop = global_drop

    # ── 2. Was the current message Meta's own ad auto-fill text, and was it sent
    #      untouched or did the lead edit/replace it before hitting send? ──────
    # via_ad_referral alone only means "this message arrived via a CTWA ad click"
    # -- Meta lets the lead freely edit or delete the pre-fill before sending, so
    # the flag alone can't be trusted either way. The current inbound message is
    # already persisted by the time compute_score runs, so the latest inbound row
    # for this lead IS the message being scored; attributed_ad_creative_id ties it
    # to the specific ad it came from, whose known original text (synced from
    # Meta, or Aira's own tracking-code flow -- see ad_creatives.prefilled_greeting_text)
    # is the ground truth to compare against.
    via_ad_referral = False
    ad_prefill_confirmed_unedited = False
    ad_prefill_known_edited = False
    try:
        latest_inbound = (
            db.table("messages")
            .select("via_ad_referral,attributed_ad_creative_id")
            .eq("lead_id", str(lead_id))
            .eq("direction", "inbound")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        latest = latest_inbound[0] if latest_inbound else {}
        via_ad_referral = bool(latest.get("via_ad_referral"))
        creative_id = latest.get("attributed_ad_creative_id")
        if via_ad_referral and creative_id:
            creative_rows = (
                db.table("ad_creatives")
                .select("prefilled_greeting_text")
                .eq("id", creative_id)
                .limit(1)
                .execute()
            ).data or []
            original = creative_rows[0].get("prefilled_greeting_text") if creative_rows else None
            if original:
                if message.strip() == original.strip():
                    ad_prefill_confirmed_unedited = True
                else:
                    ad_prefill_known_edited = True
    except Exception:
        via_ad_referral = False
        ad_prefill_confirmed_unedited = False
        ad_prefill_known_edited = False

    # Confirmed untouched pre-fill: zero real signal from this message -- freeze
    # score/segment/arc/intent/engagement exactly where they were. Still update
    # last_inbound_at since that's activity recency, not a scoring input.
    if ad_prefill_confirmed_unedited:
        db.table("leads").update({"last_inbound_at": now_iso}).eq("id", str(lead_id)).execute()
        logger.info(f"Lead {lead_id} sent confirmed-unedited ad pre-fill — score frozen")
        return {
            "score": data.get("score") if data.get("score") is not None else 1,
            "segment": global_segment,
            "arc_score": global_arc,
            "intent_delta": data.get("score_intent_delta") or 0,
            "engagement": data.get("score_engagement") or 0,
            "intent_reason": "ad_prefilled_frozen",
            "arc_updated": False,
            "segment_drop_count": global_drop,
        }

    # Known to have been edited: it's the lead's own words now, regardless of
    # how the conversation started -- score fully normally, no ad-related
    # discount at all. Unknown (flag set but no original text to compare, e.g.
    # not synced yet): keep today's softer treatment as a safe fallback.
    effective_via_ad_referral = via_ad_referral and not ad_prefill_known_edited

    # ── 3. Intent delta (instant, rule-based) ─────────────────────────────────
    intent_delta, intent_reason = _compute_intent_delta(message, "idle", via_ad_referral=effective_via_ad_referral)
    is_rejection = intent_delta == _REJECTION_SENTINEL

    # ── 5. REJECTION: bypass everything, force D for both global + broadcast ───
    if is_rejection:
        rejection_payload = {
            "score": 0, "score_arc": 1, "score_intent_delta": -3,
            "score_engagement": 0,
            "segment": "D",
            "segment_drop_count": 0,
            "last_inbound_at": now_iso,
            "broadcast_negative_reply_at": now_iso,
        }
        db.table("leads").update(rejection_payload).eq("id", str(lead_id)).execute()

        logger.info(f"Lead {lead_id} rejection detected — immediate D")
        return {
            "score": 0, "segment": "D", "arc_score": 1,
            "intent_delta": -3, "engagement": 0,
            "intent_reason": "rejection", "arc_updated": True,
            "segment_drop_count": 0,
        }

    # ── 6. Engagement (rule-based, from message history) ─────────────────────
    engagement = _compute_engagement(lead_id, db)

    # ── 7. Arc score (LLM, every inbound message) ─────────────────────────────
    try:
        msg_query = (
            db.table("messages")
            .select("direction,content,created_at,via_ad_referral,attributed_ad_creative_id")
            .eq("lead_id", str(lead_id))
            .order("created_at", desc=True)
            .limit(10)
        )
        msgs = (msg_query.execute().data or [])

        # Batch-resolve creatives for any ad-referred message in this window, so
        # each gets checked against its OWN known pre-fill text -- a message
        # flagged via_ad_referral that turns out to have been edited must NOT
        # get the ad-prefill marker here either; it's the lead's real words.
        greetings_by_creative: dict = {}
        creative_ids = {
            m.get("attributed_ad_creative_id") for m in msgs
            if m.get("via_ad_referral") and m.get("attributed_ad_creative_id")
        }
        if creative_ids:
            try:
                creative_rows = (
                    db.table("ad_creatives")
                    .select("id,prefilled_greeting_text")
                    .in_("id", list(creative_ids))
                    .execute()
                ).data or []
                greetings_by_creative = {r["id"]: r.get("prefilled_greeting_text") for r in creative_rows}
            except Exception:
                greetings_by_creative = {}

        escalation_windows = []
        try:
            handovers = (
                db.table("chat_handovers")
                .select("opened_at,resolved_at")
                .eq("lead_id", str(lead_id))
                .execute()
            ).data or []
            for h in handovers:
                opened = _parse_dt(h.get("opened_at"))
                if opened:
                    # opened_at is stamped a few seconds after the message that
                    # triggers the handover, and back-to-back re-escalations can
                    # leave a short gap between one resolved_at and the next
                    # opened_at — pad the start so both cases stay in-window.
                    start = opened - timedelta(minutes=5)
                    closed = _parse_dt(h.get("resolved_at")) or datetime.now(timezone.utc)
                    escalation_windows.append((start, closed))
        except Exception:
            escalation_windows = []

        lines = []
        for m in reversed(msgs):
            role = "Bot" if m.get("direction") == "outbound" else "User"
            content = (m.get("content") or "").strip()[:200]
            if content and not content.startswith("[Template"):
                created = _parse_dt(m.get("created_at"))
                is_escalation_followup = role == "User" and created and any(
                    start <= created <= end for start, end in escalation_windows
                )
                original_greeting = greetings_by_creative.get(m.get("attributed_ad_creative_id"))
                is_confirmed_unedited = (
                    bool(m.get("via_ad_referral"))
                    and bool(original_greeting)
                    and (m.get("content") or "").strip() == (original_greeting or "").strip()
                )
                is_unknown_ad_referral = bool(m.get("via_ad_referral")) and not original_greeting
                if is_confirmed_unedited or is_unknown_ad_referral:
                    prefix = f"{_AD_PREFILL_MARKER} "
                elif is_escalation_followup:
                    prefix = f"{_ESCALATION_MARKER} "
                else:
                    prefix = ""
                lines.append(f"{role}: {prefix}{content}")
        conversation = "\n".join(lines) if lines else f"User: {message}"
    except Exception:
        conversation = f"User: {message}"

    current_arc = await _score_arc(conversation, tenant_id, fallback=current_arc)
    arc_updated = True

    # ── 8. Composite final score ───────────────────────────────────────────────
    final_score = max(0, min(10, current_arc + intent_delta + engagement))

    # ── 9. Segment with lock ───────────────────────────────────────────────────
    proposed_segment = score_to_segment(final_score)
    final_segment, new_drop_count = _apply_segment_lock(
        proposed_segment, current_seg, current_drop, big_drop=False
    )

    # ── 10. Persist global leads ───────────────────────────────────────────────
    db.table("leads").update({
        "score": final_score,
        "score_arc": current_arc,
        "score_intent_delta": intent_delta,
        "score_engagement": engagement,
        "segment": final_segment,
        "segment_drop_count": new_drop_count,
        "last_inbound_at": now_iso,
    }).eq("id", str(lead_id)).execute()

    logger.info(
        f"Lead {lead_id} scored: arc={current_arc} intent={intent_delta:+d} "
        f"eng={engagement:+d} → {final_score} ({final_segment}) "
        f"[arc_updated={arc_updated}, reason={intent_reason}]"
    )

    return {
        "score": final_score,
        "segment": final_segment,
        "arc_score": current_arc,
        "intent_delta": intent_delta,
        "engagement": engagement,
        "intent_reason": intent_reason,
        "arc_updated": arc_updated,
        "segment_drop_count": new_drop_count,
    }


