import logging

from app.services.call_audio import AudioChunk, audio_for_evaluation, resplit_chunk, split_audio
from app.services.gemini_client import gemini_analysis_json, gemini_transcribe_audio

logger = logging.getLogger(__name__)


class TranscriptionIncomplete(Exception):
    """A piece of the recording kept coming back cut off and could not be cut smaller."""


class CallAnalysisError(Exception):
    """The evaluation came back without every selected criterion."""


# Order is the display order everywhere (settings, call card, QA feed).
SCORE_CRITERIA: dict[str, tuple[str, str]] = {
    "greeting_quality": (
        "Greeting",
        "Did the telecaller introduce themselves and the company clearly?",
    ),
    "communication_clarity": (
        "Clarity",
        "Was the telecaller's speech clear and easy to follow?",
    ),
    "product_knowledge": (
        "Product knowledge",
        "Was the product/service information the telecaller gave correct? Compare it against the knowledge base reference below.",
    ),
    "requirement_understanding": (
        "Requirement understanding",
        "Did the telecaller ask relevant questions and understand what the customer needs?",
    ),
    "conversation_engagement": (
        "Engagement",
        "Did the telecaller try to engage the customer: asking open questions, listening, and responding to what the customer actually said? Judge the telecaller's effort, not how interested the customer was.",
    ),
    "objection_handling": (
        "Objection handling",
        "Did the telecaller handle the customer's doubts and objections well? If the customer raised none, judge whether the telecaller checked for concerns.",
    ),
    "professionalism": (
        "Professionalism",
        "Polite language, no rudeness, no unnecessary arguments?",
    ),
    "tone": (
        "Tone",
        "Listen to the attached audio: did the telecaller sound warm, confident and energetic, at a comfortable pace, rather than flat, rushed or irritated?",
    ),
}
DEFAULT_CRITERIA: list[str] = list(SCORE_CRITERIA)
AUDIO_CRITERIA = {"tone"}
SCORABLE_OUTCOMES = ("converted", "interested", "callback", "not_interested")
DETECTED_OUTCOMES = SCORABLE_OUTCOMES + ("no_conversation",)


def normalize_criteria(raw) -> list[str]:
    """Known criteria in canonical order; [] when nothing valid was selected."""
    chosen = set(raw) if isinstance(raw, (list, tuple, set)) else set()
    return [key for key in SCORE_CRITERIA if key in chosen]


# ── Transcription ─────────────────────────────────────────────────────

_TRANSCRIBE_PROMPT = (
    "Transcribe this phone call recording completely and verbatim: every word, from the "
    "first second to the last. Do not summarise, skip, shorten or translate anything. Keep "
    "each speaker's words in the language and script they used (Tamil, Hindi, English or a mix).\n"
    "Put each speaker turn on its own line, starting with exactly 'Telecaller:' or 'Customer:'. "
    "The telecaller is the person calling on behalf of the business (they usually introduce "
    "themselves or the company and explain the offer); the customer is the person being called.\n"
    "If a stretch is unclear, write [inaudible] instead of guessing. If there is no speech at "
    "all, return nothing. Return only the transcript."
)


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _piece_prompt(chunk: AudioChunk) -> str:
    if chunk.start_seconds <= 0:
        return _TRANSCRIBE_PROMPT
    return (
        _TRANSCRIBE_PROMPT
        + f"\nThis audio is a later piece of the same call, starting {_clock(chunk.start_seconds)} "
        "into it, so it may begin or end mid-sentence. Keep using the same two labels."
    )


async def transcribe_call(
    audio_bytes: bytes, mime_type: str, tenant_id: str | None = None,
) -> tuple[str, list[AudioChunk]]:
    """Speaker-labelled transcript of the whole call, plus the pieces it was made from.

    Long recordings are transcribed piece by piece and joined in order. A piece that
    comes back cut off is halved and redone; if it can't be halved any further the
    whole transcription fails rather than returning half a call.
    """
    pending = list(split_audio(audio_bytes, mime_type))
    used: list[AudioChunk] = []
    parts: list[str] = []
    while pending:
        chunk = pending.pop(0)
        text, complete = await gemini_transcribe_audio(
            chunk.data, chunk.mime_type, _piece_prompt(chunk), tenant_id=tenant_id,
        )
        if not complete:
            smaller = resplit_chunk(chunk)
            if not smaller:
                raise TranscriptionIncomplete(
                    f"transcript cut off in the piece starting at {_clock(chunk.start_seconds)}"
                )
            logger.info(f"Transcript piece at {_clock(chunk.start_seconds)} was cut off; retrying as {len(smaller)} pieces")
            pending[:0] = smaller
            continue
        used.append(chunk)
        if text.strip():
            parts.append(text.strip())
    if len(used) > 1:
        logger.info(f"Call transcribed in {len(used)} pieces")
    return "\n".join(parts), used


# ── Analysis: summary + evaluation in one pass ────────────────────────

_ANALYZE_SYSTEM = (
    "You are a quality reviewer for a telecalling team. You read a phone call transcript "
    "(and, when attached, listen to the call audio), summarise the call and evaluate the "
    "telecaller. The transcript may be in English, Tamil, Hindi or a mix of these "
    "(including Tanglish). Understand it regardless of language, but write every output "
    "value in English.\n"
    "Judge only the telecaller's skill. Never lower a score because the customer said no, "
    "was busy or wasn't interested: a not-interested call that the telecaller handled well "
    "should score high."
)


def _criteria_block(criteria: list[str]) -> str:
    lines = [
        "Evaluation criteria: score each from 0 to 10 (0 = not done at all, 5 = partly done / "
        "average, 10 = excellent) and give a one-sentence reason:"
    ]
    for key in criteria:
        lines.append(f"- {key} / {key}_reason: {SCORE_CRITERIA[key][1]}")
    return "\n".join(lines)


def _analysis_prompt(
    transcript: str, criteria: list[str], lead_name: str | None, kb_context: str | None, audio_note: str,
) -> str:
    lead_line = f"Lead name: {lead_name}\n\n" if lead_name else ""
    if kb_context:
        kb_block = (
            "Knowledge base reference (use it to judge product_knowledge; if it doesn't cover "
            "what was discussed, grade product_knowledge leniently and say so):\n" + kb_context + "\n\n"
        )
    else:
        kb_block = "Knowledge base reference: none available. Grade product_knowledge leniently.\n\n"
    return (
        f"{lead_line}"
        f"Transcript (each line is labelled Telecaller or Customer):\n{transcript}\n\n"
        f"{kb_block}"
        f"{audio_note}"
        "Return valid JSON only, with ALL of these keys.\n"
        "Summary fields:\n"
        "- course: course/product/service the customer was interested in\n"
        "- product: same as course (duplicate for compatibility)\n"
        "- budget: budget mentioned, or null\n"
        "- timeline: timeline/deadline mentioned, or null\n"
        "- next_action: recommended next action\n"
        "- sentiment: one of 'positive', 'neutral', 'negative'\n"
        "- brief: a 2-3 sentence overview of what was discussed and how the customer reacted\n"
        "- objections: what the customer pushed back on, or null\n"
        "- commitments: what the telecaller promised to do or send, or null\n"
        "- open_questions: what the customer asked that the telecaller could not answer, or null\n"
        f"{_criteria_block(criteria)}\n"
        "Outcome fields:\n"
        "- real_conversation: true only if the telecaller and a real customer actually spoke to "
        "each other; false for voicemail, IVR/automated messages, ringing, silence or a one-sided message\n"
        "- detected_outcome: what actually happened, one of 'converted', 'interested', 'callback', "
        "'not_interested', 'no_conversation'\n"
        "- acceptable_outcomes: array of every label from ['converted', 'interested', 'callback', "
        "'not_interested'] a fair reviewer would accept for this call (e.g. both 'interested' and "
        "'callback' when the customer is interested and asked to be called later); [] if there was no real conversation\n"
        "- closing_move / closing_move_reason: integer 0-10 and one sentence: did the telecaller make "
        "the right closing move for what happened? converted: confirmed what was agreed and the next "
        "step (payment, onboarding). interested: fixed a concrete next step with a time (demo, visit, "
        "sending details). callback: got a specific date/time and the reason. not_interested: asked "
        "why, made one fair attempt to address it, and closed politely leaving the door open.\n"
        "Other fields:\n"
        "- talk_ratio: integer 0-100, estimated % of the call the telecaller was speaking\n"
        "- clear_next_step: true if the call ended with a clear next step\n"
        "- next_step_summary: short description of the agreed next step, or null\n"
        "- purchase_intent: one of 'high', 'medium', 'low'\n"
        "- missed_opportunity: true if the telecaller missed a chance to move the customer forward\n"
        "- missed_opportunity_note: one sentence on the missed opportunity, or null\n"
        "- coaching_tip: one specific, actionable improvement for the telecaller (max 50 words)"
    )


_SUMMARY_KEYS = (
    "course", "product", "budget", "timeline", "next_action", "sentiment", "brief",
    "objections", "commitments", "open_questions",
)
_EXTRA_EVAL_KEYS = (
    "closing_move_reason", "talk_ratio", "clear_next_step", "next_step_summary",
    "purchase_intent", "missed_opportunity", "missed_opportunity_note", "coaching_tip",
)


def _as_score(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return max(0, min(10, round(float(value))))
    except (TypeError, ValueError):
        return None


def _quality_label(score: float) -> str:
    if score >= 9:
        return "Excellent"
    if score >= 7:
        return "Good"
    if score >= 5:
        return "Average"
    return "Bad"


def build_evaluation(data: dict, criteria: list[str]) -> dict:
    """Validate the model's JSON into the v3 evaluation. Raises if a criterion is missing."""
    evaluation: dict = {}
    for key in criteria:
        score = _as_score(data.get(key))
        if score is None:
            raise CallAnalysisError(f"evaluation missing criterion {key}")
        evaluation[key] = score
        evaluation[f"{key}_reason"] = data.get(f"{key}_reason")
    for key in _EXTRA_EVAL_KEYS:
        if key in data:
            evaluation[key] = data[key]

    closing = _as_score(data.get("closing_move"))
    evaluation["closing_move"] = closing if closing is not None else 0
    detected = data.get("detected_outcome")
    evaluation["detected_outcome"] = detected if detected in DETECTED_OUTCOMES else "no_conversation"
    acceptable = data.get("acceptable_outcomes")
    evaluation["acceptable_outcomes"] = [o for o in SCORABLE_OUTCOMES if isinstance(acceptable, list) and o in acceptable]
    evaluation["real_conversation"] = data.get("real_conversation") is True

    average = round(sum(evaluation[k] for k in criteria) / len(criteria), 2)
    evaluation["criteria"] = list(criteria)
    evaluation["ai_average"] = average
    evaluation["quality_label"] = _quality_label(average)
    evaluation["evaluation_version"] = 3
    return evaluation


async def analyze_call(
    transcript: str,
    criteria: list[str],
    lead_name: str | None = None,
    kb_context: str | None = None,
    tenant_id: str | None = None,
    chunks: list[AudioChunk] | None = None,
) -> tuple[dict, dict]:
    """One pass returning (summary, evaluation). Raises on failure so the pipeline retries.

    Tone needs the audio: when it is selected, as much of the recording as fits in one
    request is attached. If none fits, tone is dropped for this call and recorded as skipped.
    """
    selected = list(criteria)
    skipped: list[str] = []
    audio: list[tuple[bytes, str]] = []
    audio_note = ""
    if AUDIO_CRITERIA & set(selected):
        pieces = audio_for_evaluation(chunks or [])
        if pieces:
            audio = [(p.data, p.mime_type) for p in pieces]
            covered = sum(p.duration for p in pieces)
            total = sum(p.duration for p in chunks or [])
            coverage = f" (covering the first {_clock(covered)} of {_clock(total)})" if total and covered < total else ""
            audio_note = f"The call audio is attached{coverage}. Use it for the tone criterion.\n\n"
        else:
            skipped = [k for k in selected if k in AUDIO_CRITERIA]
            selected = [k for k in selected if k not in AUDIO_CRITERIA]
    if not selected:
        raise CallAnalysisError("no criterion could be evaluated for this call")

    data = await gemini_analysis_json(
        system_prompt=_ANALYZE_SYSTEM,
        user_prompt=_analysis_prompt(transcript, selected, lead_name, kb_context, audio_note),
        audio=audio,
        tenant_id=tenant_id,
    )
    summary = {k: data[k] for k in _SUMMARY_KEYS if k in data}
    evaluation = build_evaluation(data, selected)
    if skipped:
        evaluation["criteria_skipped"] = skipped
    return summary, evaluation
