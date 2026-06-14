import json
import logging

import httpx
from groq import AsyncGroq

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncGroq(api_key=settings.groq_api_key) if settings.groq_api_key else None
_TRANSCRIBE_MODEL = "whisper-large-v3-turbo"
_SUMMARY_MODEL = "llama-3.3-70b-versatile"

_SUMMARIZE_SYSTEM = (
    "You are analyzing a sales call transcript for a B2B sales team. "
    "The transcript may be in English, Tamil, Hindi, or a mix of these languages "
    "(including transliterated/Tanglish text). Read and understand it regardless of "
    "language, but write all output field values in English."
)

_SUMMARIZE_USER = (
    "Transcript:\n{transcript}\n\n"
    "Extract: course/product/service interested in, budget mentioned, timeline/deadline, "
    "recommended next action, overall sentiment (positive/neutral/negative), and a call brief (a 2-3 sentence overview of what was discussed on the call).\n"
    "Translate any non-English content into English before writing the field values. "
    "Return valid JSON only with keys: course, product, budget, timeline, next_action, sentiment, brief."
)


async def transcribe_recording(recording_url: str) -> str:
    if not _client:
        logger.warning("GROQ_API_KEY not configured — skipping transcription")
        return ""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(recording_url)
            resp.raise_for_status()
            audio_bytes = resp.content
    except Exception as e:
        logger.error(f"Failed to download recording {recording_url}: {e}")
        return ""

    try:
        logger.info(f"Sending {len(audio_bytes)} bytes to Groq Whisper for transcription")
        result = await _client.audio.transcriptions.create(
            file=("recording.mp3", audio_bytes, "audio/mp3"),
            model=_TRANSCRIBE_MODEL,
        )
        transcript = (result.text or "").strip()
        logger.info(f"Transcription complete: {len(transcript)} chars")
        return transcript
    except Exception as e:
        logger.error(f"Groq transcription failed for {recording_url}: {e}")
        return ""


async def summarize_call(transcript: str, lead_name: str | None = None) -> dict:
    if not transcript or not _client:
        return {}

    user_prompt = _SUMMARIZE_USER.format(transcript=transcript)
    if lead_name:
        user_prompt = f"Lead name: {lead_name}\n\n" + user_prompt

    try:
        response = await _client.chat.completions.create(
            model=_SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=400,
        )
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Groq summary JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Groq summarize_call failed: {e}")
        return {}


_EVALUATE_PROMPT = (
    "You are evaluating a sales call recording transcript. Assess the caller's performance.\n\n"
    "Transcript:\n{transcript}\n\n"
    "Return valid JSON only with these exact keys:\n"
    "- talk_ratio: integer 0-100, estimated percentage of time the caller was speaking\n"
    "- objection_handling: one of 'good', 'average', 'poor'\n"
    "- outcome_clarity: 'yes' if call ended with a clear next step, 'no' otherwise\n"
    "- overall_score: integer 1-10 for overall call quality\n"
    "- coaching_tip: string, one specific actionable improvement for the caller (max 50 words)"
)


async def evaluate_call(transcript: str) -> dict:
    if not transcript or not _client:
        return {}
    try:
        response = await _client.chat.completions.create(
            model=_SUMMARY_MODEL,
            messages=[
                {"role": "user", "content": _EVALUATE_PROMPT.format(transcript=transcript)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=300,
        )
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Groq evaluation JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Groq evaluate_call failed: {e}")
        return {}


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
    "Evaluation fields:\n"
    "- talk_ratio: integer 0-100, estimated % of time the caller was speaking\n"
    "- objection_handling: one of 'good', 'average', 'poor'\n"
    "- outcome_clarity: 'yes' if call ended with a clear next step, 'no' otherwise\n"
    "- overall_score: integer 1-10 for overall call quality\n"
    "- coaching_tip: one specific actionable improvement for the caller (max 50 words)"
)

_SUMMARY_KEYS = {"course", "product", "budget", "timeline", "next_action", "sentiment", "brief"}
_EVAL_KEYS = {"talk_ratio", "objection_handling", "outcome_clarity", "overall_score", "coaching_tip"}

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


async def analyze_call(transcript: str, lead_name: str | None = None) -> tuple[dict, dict]:
    """Single LLM pass returning (summary_dict, evaluation_dict).

    Replaces calling summarize_call + evaluate_call separately.
    Falls back to ({}, {}) on any error.
    """
    if not transcript or not _client:
        return {}, {}

    lead_line = f"Lead name: {lead_name}\n\n" if lead_name else ""
    user_prompt = _ANALYZE_USER.format(lead_line=lead_line, transcript=transcript)

    try:
        response = await _client.chat.completions.create(
            model=_SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": _ANALYZE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=500,
        )
        data = json.loads(response.choices[0].message.content)
        summary = {k: data[k] for k in _SUMMARY_KEYS if k in data}
        evaluation = {k: data[k] for k in _EVAL_KEYS if k in data}
        return summary, evaluation
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Groq analyze_call JSON: {e}")
        return {}, {}
    except Exception as e:
        logger.error(f"Groq analyze_call failed: {e}")
        return {}, {}
