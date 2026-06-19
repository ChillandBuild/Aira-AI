import logging
import re
from groq import Groq
from app.config import settings

logger = logging.getLogger(__name__)

from app.services.groq_client import get_groq_client
_SCORER_MODEL = "llama-3.3-70b-versatile"

_DEFAULT_RUBRIC = """- 9-10: High intent — asked for pricing, demo, or ready to buy, confirmed booking, completed booking flow
- 7-8: Warm — asking detailed questions, comparing options, multiple follow-ups, actively providing requested information
- 5-6: Neutral — general inquiry, first contact, acknowledgment without commitment
- 1-4: Low — no reply, said not interested, irrelevant message, dismissive"""

SCORING_PROMPT = """You are a lead scoring assistant for a B2B sales team.

Score this message from a prospect (1-10 integer):
{rubric}

IMPORTANT: Use the context to understand the message.
- A short reply like "ok", "yes", or "thank you" AFTER completing a booking flow or providing requested info = high intent (8-10)
- The same message as a first contact or without context = neutral/low (3-5)
- If the user is actively engaged in a booking flow (providing name, rasi, address, etc.) = warm/high (7-10)
- "ok" or "thank you" during an active booking flow = acknowledgment of progress, not disinterest (7-9)
- A message requesting communication in a regional language (Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, etc.) is an ENGAGEMENT SIGNAL — score minimum 5, never penalise for a language switch request.
- Non-English messages carry the same weight as equivalent English expressions. "ஆமா வேணும்" = "yes I want it" = high intent if context supports it. "சிம்மம்" answering a rasi question = a valid answer — score based on conversational context, not message length or language.

CONTEXT:
{context_block}

Previous score: {current_score}
Message: "{message}"

Reply with ONLY a single integer between 1 and 10. No explanation."""


def _get_rubric(tenant_id: str | None) -> str:
    if not tenant_id:
        return _DEFAULT_RUBRIC
    try:
        from app.config_dynamic import get_setting
        custom = get_setting("scoring_rubric", tenant_id=tenant_id)
        return custom.strip() if custom and custom.strip() else _DEFAULT_RUBRIC
    except Exception:
        return _DEFAULT_RUBRIC


async def score_message(
    message: str,
    current_score: int = 5,
    context_block: str | None = None,
    tenant_id: str | None = None,
) -> int:
    try:
        client = get_groq_client(tenant_id, is_async=False)
    except Exception as e:
        logger.warning(f"Groq API key not configured for tenant {tenant_id}: {e}")
        return current_score
    try:
        rubric = _get_rubric(tenant_id)
        context = context_block or "No prior conversation context available."
        prompt = SCORING_PROMPT.format(
            rubric=rubric,
            context_block=context,
            current_score=current_score,
            message=message,
        )
        response = client.chat.completions.create(
            model=_SCORER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4,
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r'\d+', raw)
        score = int(match.group()) if match else current_score
        return max(1, min(10, score))
    except Exception as e:
        logger.error(f"Scoring failed: {e}")
        return current_score


async def score_with_safety_net(
    message: str,
    current_score: int,
    context_block: str,
    db,
    lead_id: str,
    tenant_id: str | None = None,
) -> int:
    """Two-pass scoring with D-segment safety net."""
    first_score = await score_message(message, current_score, context_block, tenant_id=tenant_id)

    if first_score >= 5:
        return first_score

    logger.info(f"Lead {lead_id} scored {first_score} (Segment D) — triggering safety net re-evaluation")

    from app.services.context_builder import build_scorer_context
    full_context = build_scorer_context(lead_id, db, force_full_context=True)

    second_score = await score_message(message, current_score, full_context, tenant_id=tenant_id)

    logger.info(f"Safety net re-evaluation: {first_score} → {second_score}")

    return second_score
