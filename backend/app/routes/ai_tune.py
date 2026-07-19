import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config_dynamic import get_setting, save_setting, invalidate_cache
from app.dependencies.tenant import get_tenant_id, require_owner
from app.services.groq_client import get_groq_client
from app.services.token_meter import record_groq_sdk

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])

_TUNE_MODEL = "llama-3.3-70b-versatile"


class DescriptionUpdate(BaseModel):
    description: str


def _rubric_prompt(description: str) -> str:
    """Build the rubric-generation prompt from the client's business description.

    Input is the DESCRIPTION, not the master prompt: the rubric is meant to capture
    this specific business's conversion signals (a hot lead for an astrologer looks
    nothing like one for a real-estate agent). The master prompt is generic behaviour
    shared across clients and would produce an identical, useless rubric for everyone.
    """
    return f"""You are configuring a lead scoring system for a B2B sales team.

Based on this business's own description of what it does, write a lead scoring rubric
(1-10 scale). The rubric should reflect THIS specific business's conversion signals —
not generic ones.

Business description:
{description[:1500]}

Write a rubric in this exact format (5 lines, one per score band):
- 9-10: [High intent signals specific to this business]
- 7-8: [Warm signals specific to this business]
- 5-6: [Neutral signals]
- 3-4: [Low engagement signals]
- 1-2: [Disqualified / not interested signals]

Reply with ONLY the 5 rubric lines. No explanation, no preamble."""


async def _auto_generate_rubric(description: str, tenant_id: str, force: bool = False) -> None:
    """Generate a domain-appropriate scoring rubric from the tenant's business
    description. Best-effort: a failure here must never fail the description save."""
    try:
        if not force:
            existing_rubric = get_setting("scoring_rubric", tenant_id=tenant_id)
            if existing_rubric and existing_rubric.strip():
                logger.info(f"Scoring rubric already exists for tenant {tenant_id} — skipping auto-generation")
                return

        try:
            client = get_groq_client(tenant_id, is_async=True)
        except Exception:
            return

        resp = await client.chat.completions.create(
            model=_TUNE_MODEL,
            messages=[{"role": "user", "content": _rubric_prompt(description)}],
            temperature=0.3,
            max_tokens=300,
        )
        record_groq_sdk(tenant_id, "ai_tune", _TUNE_MODEL, resp)
        rubric = resp.choices[0].message.content.strip()
        if rubric and "9-10" in rubric:
            save_setting("scoring_rubric", rubric, tenant_id=tenant_id)
            logger.info(f"Auto-generated scoring rubric for tenant {tenant_id}")
    except Exception as e:
        logger.warning(f"Auto-rubric generation failed for tenant {tenant_id}: {e}")


@router.get("/description")
async def get_description(tenant_id: str = Depends(get_tenant_id)):
    return {"description": get_setting("business_description", tenant_id=tenant_id) or ""}


@router.put("/description")
async def update_description(
    payload: DescriptionUpdate, tenant_id: str = Depends(get_tenant_id)
):
    description = payload.description.strip()
    save_setting("business_description", description, tenant_id=tenant_id)
    invalidate_cache("business_description")

    if description:
        _task = asyncio.create_task(_auto_generate_rubric(description, tenant_id, force=True))
        _task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {"description": description}
