import json
import logging

import httpx

logger = logging.getLogger(__name__)

from app.services.gemini_client import gemini_chat_completion_json, gemini_speech_to_text


async def transcribe_recording(recording_url: str, tenant_id: str | None = None) -> str:
    try:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.get(recording_url)
            resp.raise_for_status()
            audio_bytes = resp.content
    except Exception as e:
        logger.error(f"Failed to download recording {recording_url}: {e}")
        return ""

    try:
        logger.info(f"Sending {len(audio_bytes)} bytes to Gemini for transcription")
        transcript = await gemini_speech_to_text(audio_bytes, "audio/mp3", tenant_id=tenant_id)
        logger.info(f"Transcription complete: {len(transcript)} chars")
        return transcript
    except Exception as e:
        logger.error(f"Gemini transcription failed for {recording_url}: {e}")
        return ""


# ── Single-pass analysis (summary + evaluation in one LLM call) ────────

_ANALYZE_SYSTEM = (
    "You are analyzing a B2B sales call transcript. Extract lead info and evaluate the "
    "caller's performance in one pass. The transcript may be in English, Tamil, Hindi, "
    "or a mix of these languages (including transliterated/Tanglish text). Read and "
    "understand it regardless of language, but write all output field values in English."
)

_ANALYZE_USER = (
    "{lead_line}"
    "Transcript:\n{transcript}\n\n"
    "{outcome_line}"
    "{kb_block}"
    "Translate any non-English content into English before writing the field values.\n"
    "Return valid JSON only with ALL of these keys:\n"
    "Summary fields:\n"
    "- course: course/product/service the lead was interested in\n"
    "- product: same as course (duplicate for compatibility)\n"
    "- budget: budget mentioned (or null)\n"
    "- timeline: timeline/deadline mentioned (or null)\n"
    "- next_action: recommended next action\n"
    "- sentiment: one of 'positive', 'neutral', 'negative'\n"
    "- brief: a 2-3 sentence overview/summary of what was discussed on the call (e.g. key topics discussed, lead's reaction, customer concerns)\n"
    "Evaluation fields — score each 1-10 and give a one-sentence reason:\n"
    "- greeting_quality / greeting_quality_reason: did the caller introduce themselves and the company clearly?\n"
    "- communication_clarity / communication_clarity_reason: was the caller's speech clear and understandable?\n"
    "- product_knowledge / product_knowledge_reason: did the caller give correct product/service info? Compare against the knowledge base reference below.\n"
    "- requirement_understanding / requirement_understanding_reason: did the caller ask relevant questions and understand the customer's need?\n"
    "- conversation_engagement / conversation_engagement_reason: was the customer actively engaged in the conversation?\n"
    "- objection_handling / objection_handling_reason: did the caller handle doubts and objections properly?\n"
    "- professionalism / professionalism_reason: polite language, no rude behavior, no unnecessary arguments?\n"
    "Other evaluation fields:\n"
    "- talk_ratio: integer 0-100, estimated % of time the caller was speaking\n"
    "- clear_next_step: true if the call ended with a clear next step, false otherwise\n"
    "- next_step_summary: short description of the agreed next step, or null\n"
    "- outcome_match: true if the caller-recorded outcome above matches what actually happened on the call, false otherwise\n"
    "- outcome_match_reason: one sentence explaining the outcome_match verdict\n"
    "- purchase_intent: one of 'high', 'medium', 'low'\n"
    "- missed_opportunity: true if the caller missed a chance to push the lead further, false otherwise\n"
    "- missed_opportunity_note: one sentence describing the missed opportunity, or null\n"
    "- coaching_tip: one specific actionable improvement for the caller (max 50 words)"
)

_SUMMARY_KEYS = {"course", "product", "budget", "timeline", "next_action", "sentiment", "brief"}
_EVAL_KEYS = {
    "greeting_quality", "greeting_quality_reason",
    "communication_clarity", "communication_clarity_reason",
    "product_knowledge", "product_knowledge_reason",
    "requirement_understanding", "requirement_understanding_reason",
    "conversation_engagement", "conversation_engagement_reason",
    "objection_handling", "objection_handling_reason",
    "professionalism", "professionalism_reason",
    "talk_ratio",
    "clear_next_step", "next_step_summary",
    "outcome_match", "outcome_match_reason",
    "purchase_intent",
    "missed_opportunity", "missed_opportunity_note",
    "coaching_tip",
}

_SCORE_KEYS = [
    "greeting_quality",
    "communication_clarity",
    "product_knowledge",
    "requirement_understanding",
    "conversation_engagement",
    "objection_handling",
    "professionalism",
]


def _quality_label(score: float) -> str:
    if score >= 9:
        return "Excellent"
    if score >= 7:
        return "Good"
    if score >= 5:
        return "Average"
    return "Bad"


def _finalize_evaluation(evaluation: dict) -> dict:
    """Derive overall_score/quality_label from the 7 graded criteria and tag the schema version."""
    scores = [evaluation[k] for k in _SCORE_KEYS if k in evaluation]
    if scores:
        overall = round(sum(scores) / len(scores), 1)
        evaluation["overall_score"] = overall
        evaluation["quality_label"] = _quality_label(overall)
    evaluation["evaluation_version"] = 2
    return evaluation


async def analyze_call(
    transcript: str,
    lead_name: str | None = None,
    outcome: str | None = None,
    kb_context: str | None = None,
    tenant_id: str | None = None,
) -> tuple[dict, dict]:
    """Single LLM pass returning (summary_dict, evaluation_dict).

    evaluation_dict is the v2 QA scorecard — see _finalize_evaluation for the
    derived overall_score/quality_label. Falls back to ({}, {}) on any error.
    """
    if not transcript:
        return {}, {}

    lead_line = f"Lead name: {lead_name}\n\n" if lead_name else ""
    outcome_line = f"Caller-recorded outcome: {outcome}\n\n" if outcome else ""
    if kb_context:
        kb_block = (
            "Knowledge base reference (use this to judge product_knowledge accuracy; "
            "if it doesn't cover what was discussed, grade product_knowledge leniently "
            "and say so in product_knowledge_reason):\n" + kb_context + "\n\n"
        )
    else:
        kb_block = (
            "Knowledge base reference: none available — grade product_knowledge "
            "leniently/neutral.\n\n"
        )
    user_prompt = _ANALYZE_USER.format(
        lead_line=lead_line,
        outcome_line=outcome_line,
        kb_block=kb_block,
        transcript=transcript,
    )

    try:
        data = await gemini_chat_completion_json(
            system_prompt=_ANALYZE_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=1500,
            tenant_id=tenant_id,
            purpose="call_analysis",
        )
        summary = {k: data[k] for k in _SUMMARY_KEYS if k in data}
        evaluation = {k: data[k] for k in _EVAL_KEYS if k in data}
        evaluation = _finalize_evaluation(evaluation)
        return summary, evaluation
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini analyze_call JSON: {e}")
        return {}, {}
    except Exception as e:
        logger.error(f"Gemini analyze_call failed: {e}")
        return {}, {}
