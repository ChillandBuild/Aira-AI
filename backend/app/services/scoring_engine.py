"""
AIRA Score Engine v3

Segment classification: Hot (A) / Warm (B) / Cold (C) / Not Interested (D)

  arc_classifier   — LLM classifies conversation intent as hot/warm/cold,
                     fires on every inbound message. Returns one of: A, B, C.
  rejection        — Rule-based rejection signal. Rejection phrases bypass
                     everything → immediate score 0, segment D.

Score compatibility layer (DB: 0-10 int):
  A (Hot) → score 9    | B (Warm) → score 6
  C (Cold) → score 2   | D (Not Interested) → score 0

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


def _check_rejection(message: str) -> bool:
    """Check if message contains rejection pattern. Returns True if rejection detected."""
    for pat in _REJECTION_PATTERNS:
        if re.search(pat, message, re.IGNORECASE):
            return True
    return False


_ARC_RUBRIC_DEFAULT = """
- Hot: Explicitly asked for pricing/payment, confirmed participation, ready to proceed, booking a slot
- Warm: Asking detailed questions, comparing options, providing requested info, multiple engaged follow-ups
- Cold: General inquiry, first contact, initial greetings, vague replies, low engagement, no follow-up to questions
"""

_AD_PREFILL_MARKER = "[ad-prefilled entry message]"
_ESCALATION_MARKER = "[handover follow-up]"


def _is_old_5band_rubric(rubric: str) -> bool:
    """Detect old numeric 5-band rubric format (lines starting with digit ranges like 9-10)."""
    lines = rubric.strip().split("\n")
    for line in lines:
        if re.match(r'^\s*\d+-\d+\s*:', line.strip()):
            return True
    return False


async def _classify_segment(conversation: str, tenant_id: str | None, fallback: str = "C") -> tuple[str, str]:
    """
    LLM classifies conversation for segment: hot/warm/cold.
    Returns (segment, reason) where segment is 'A'/'B'/'C' and reason is short explanation.
    fallback is returned on error as the segment (with reason='error_fallback').
    """
    try:
        from app.config_dynamic import get_setting
        custom = get_setting("scoring_rubric", tenant_id=tenant_id) if tenant_id else None

        # If custom rubric is old 5-band format, fall back to default
        if custom and _is_old_5band_rubric(custom):
            logger.info(f"Tenant {tenant_id} has old 5-band rubric format, using default")
            rubric = _ARC_RUBRIC_DEFAULT.strip()
        else:
            rubric = (custom or _ARC_RUBRIC_DEFAULT).strip()
    except Exception:
        rubric = _ARC_RUBRIC_DEFAULT.strip()

    prompt = (
        f"Classify the lead's purchase intent into one of three categories.\n\n"
        f"Rubric:\n{rubric}\n\n"
        f"Conversation:\n{conversation}\n\n"
        f"RULES:\n"
        f"- Initial greetings (e.g., \"Hi\", \"Hello\", \"Namaste\", \"Vanakkam\") = Cold unless rubric says otherwise.\n"
        f"- A line prefixed with \"{_AD_PREFILL_MARKER}\" = Meta's auto-fill (lead tapped ad, did not compose). Treat as Cold.\n"
        f"- A line prefixed with \"{_ESCALATION_MARKER}\" = frustration about response time, NOT intent. Ignore for classification.\n"
        f"- Regional language messages have same weight as English.\n\n"
        f"Reply with ONE WORD ONLY: hot or warm or cold\n"
        f"Optionally add a short reason on a second line (e.g., \"hot\\nAsked for pricing\")"
    )
    try:
        raw = await gemini_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=_MODEL,
            temperature=0.0,
            max_tokens=40,
            tenant_id=tenant_id,
            purpose="scoring",
        )

        lines = raw.strip().lower().split("\n")
        classification = lines[0].strip()
        reason = lines[1].strip() if len(lines) > 1 else ""

        # Robust parsing
        if "hot" in classification:
            return "A", reason or "classified_hot"
        elif "warm" in classification:
            return "B", reason or "classified_warm"
        elif "cold" in classification:
            return "C", reason or "classified_cold"
        else:
            logger.warning(f"Unexpected classification output: {raw}")
            return fallback, "parse_error_fallback"
    except Exception as e:
        logger.error(f"Segment classification failed: {e}")
        return fallback, "error_fallback"


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
    Main entry point. Classifies lead segment, persists to DB, returns breakdown.

    Segment/score only move on something the lead actually said (LLM classification,
    rejection detection) — going silent never changes either, by design.
    No time-based decay term.

    Returns:
        score, segment, arc_score, intent_delta, engagement,
        intent_reason, arc_updated, segment_drop_count, reason
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
    # score/segment/classification exactly where they were. Still update
    # last_inbound_at since that's activity recency, not a scoring input.
    if ad_prefill_confirmed_unedited:
        db.table("leads").update({"last_inbound_at": now_iso}).eq("id", str(lead_id)).execute()
        logger.info(f"Lead {lead_id} sent confirmed-unedited ad pre-fill — score frozen")
        return {
            "score": data.get("score") if data.get("score") is not None else 2,
            "segment": global_segment,
            "arc_score": global_arc,
            "intent_delta": 0,
            "engagement": 0,
            "intent_reason": "ad_prefilled_frozen",
            "arc_updated": False,
            "segment_drop_count": global_drop,
            "reason": "ad_prefilled_frozen",
        }

    # Known to have been edited: it's the lead's own words now, regardless of
    # how the conversation started -- score fully normally, no ad-related
    # discount at all.
    effective_via_ad_referral = via_ad_referral and not ad_prefill_known_edited

    # ── 3. Rejection check (instant, rule-based) ──────────────────────────────
    is_rejection = _check_rejection(message)

    # ── 4. REJECTION: bypass everything, force D for both global + broadcast ───
    if is_rejection:
        rejection_payload = {
            "score": 0, "score_arc": 0, "score_intent_delta": 0,
            "score_engagement": 0,
            "segment": "D",
            "segment_drop_count": 0,
            "last_inbound_at": now_iso,
            "broadcast_negative_reply_at": now_iso,
        }
        db.table("leads").update(rejection_payload).eq("id", str(lead_id)).execute()

        logger.info(f"Lead {lead_id} rejection detected — immediate D")
        return {
            "score": 0, "segment": "D", "arc_score": 0,
            "intent_delta": 0, "engagement": 0,
            "intent_reason": "rejection", "arc_updated": True,
            "segment_drop_count": 0,
            "reason": "rejection",
        }

    # ── 5. Segment classification (LLM, every inbound message) ────────────────
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

    classified_segment, classification_reason = await _classify_segment(conversation, tenant_id, fallback=current_seg)
    arc_updated = True

    # ── 6. Map segment to compatibility score (DB: 0-10) ──────────────────────
    segment_to_score = {"A": 9, "B": 6, "C": 2, "D": 0}

    # ── 7. Segment with lock ──────────────────────────────────────────────────
    final_segment, new_drop_count = _apply_segment_lock(
        classified_segment, current_seg, current_drop, big_drop=False
    )
    # Score follows the segment actually kept after the lock, not the raw label.
    final_score = segment_to_score.get(final_segment, 2)

    # ── 8. Persist global leads ───────────────────────────────────────────────
    db.table("leads").update({
        "score": final_score,
        "score_arc": final_score,  # For compat: store the score value here too
        "score_intent_delta": 0,  # Compat placeholder
        "score_engagement": 0,    # Compat placeholder
        "segment": final_segment,
        "segment_drop_count": new_drop_count,
        "last_inbound_at": now_iso,
    }).eq("id", str(lead_id)).execute()

    logger.info(
        f"Lead {lead_id} classified: {classified_segment} → score {final_score} "
        f"({final_segment}) [reason={classification_reason}]"
    )

    return {
        "score": final_score,
        "segment": final_segment,
        "arc_score": final_score,
        "intent_delta": 0,
        "engagement": 0,
        "intent_reason": "classified",
        "arc_updated": arc_updated,
        "segment_drop_count": new_drop_count,
        "reason": classification_reason,
    }


