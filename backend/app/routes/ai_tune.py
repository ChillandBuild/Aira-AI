import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config_dynamic import get_setting, save_setting, invalidate_cache
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_owner
from app.services.gemini_client import gemini_chat_completion
from app.services.knowledge_versions import save_description

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])

# Same model the arc scorer itself uses (scoring_engine.py) -- one fewer provider
# key for a tenant to configure. Switched off Groq 2026-09-23: two live tenants
# (Astro Tamil - Co, Astrotamil Pooja) have a gemini_api_key but no groq_api_key,
# so auto-rubric-generation was silently no-op'ing for them (get_groq_client raises,
# caught, returns) every time their description was saved.
_TUNE_MODEL = "gemini-3.1-flash-lite"


class DescriptionUpdate(BaseModel):
    description: str


class AppLinkUpdate(BaseModel):
    app_link: str


def _rubric_prompt(description: str) -> str:
    """Build the rubric-generation prompt from the client's business description.

    Input is the DESCRIPTION, not the master prompt: the rubric is meant to capture
    this specific business's conversion signals (a hot lead for an astrologer looks
    nothing like one for a real-estate agent). The master prompt is generic behaviour
    shared across clients and would produce an identical, useless rubric for everyone.
    """
    return f"""You write the examples a lead classifier uses for ONE business.

The classifier already has fixed definitions for every business:
- HOT  = the lead took a buying step (asked the price or how to pay, asked to book /
         visit / get a demo, asked for the sign-up or app link, said they want to buy,
         sent the details the service needs to start, or is blocked while trying to buy).
- WARM = real interest but no buying step yet (asks about the service, describes a need
         or personal question the service answers, compares options, will decide later).
- COLD = no real interest (greetings, one-word replies, unrelated, wrong number, asks for
         something this business does not sell, or withdrew).

Your job: translate those definitions into what they look like for THIS business.
First work out, silently: what exactly does a customer pay for here, how do they
start or book it, and what problems or questions bring people here.

Business description:
{description[:1500]}

Rules:
- Hot must name concrete buying steps for this business (its booking, payment or
  sign-up actions), never a topic. "Asks about marriage" is a topic, so it is Warm.
- Warm must name the questions and needs people here typically have.
- Cold must name the typical non-buyers for this business (e.g. job seekers, people
  wanting a service it does not offer), plus greetings and one-word replies.
- Write in the customer's likely words where useful. Keep each line under 45 words.

Reply with exactly 3 lines and nothing else:
- Hot: ...
- Warm: ...
- Cold: ..."""


def is_old_5band_rubric(rubric: str) -> bool:
    """Detect old numeric 5-band rubric format. Single source: scoring_engine."""
    from app.services.scoring_engine import _is_old_5band_rubric
    return _is_old_5band_rubric(rubric)


async def _auto_generate_rubric(description: str, tenant_id: str, force: bool = False) -> None:
    """Generate a domain-appropriate scoring rubric from the tenant's business
    description. Best-effort: a failure here must never fail the description save."""
    try:
        if not force:
            existing_rubric = get_setting("scoring_rubric", tenant_id=tenant_id)
            if existing_rubric and existing_rubric.strip() and not is_old_5band_rubric(existing_rubric):
                logger.info(f"Scoring rubric already exists for tenant {tenant_id} — skipping auto-generation")
                return

        rubric = (
            await gemini_chat_completion(
                messages=[{"role": "user", "content": _rubric_prompt(description)}],
                model=_TUNE_MODEL,
                temperature=0.2,
                max_tokens=400,
                tenant_id=tenant_id,
                purpose="ai_tune_rubric",
            )
        ).strip()
        if rubric and ("Hot" in rubric or "hot" in rubric):
            save_setting("scoring_rubric", rubric, tenant_id=tenant_id)
            logger.info(f"Auto-generated scoring rubric for tenant {tenant_id}")
        else:
            logger.warning(f"Generated rubric for tenant {tenant_id} does not match expected format")
    except Exception as e:
        logger.warning(f"Auto-rubric generation failed for tenant {tenant_id}: {e}")


@router.get("/description")
async def get_description(tenant_id: str = Depends(get_tenant_id)):
    return {"description": get_setting("business_description", tenant_id=tenant_id) or ""}


def _rubric_auto_update_enabled(tenant_id: str) -> bool:
    """Opt-in per client. Defaults to OFF so saving a description never silently
    overwrites a hand-tuned scoring rubric -- that is the whole point of the toggle."""
    return get_setting("rubric_auto_update", fallback="false", tenant_id=tenant_id) == "true"


def queue_rubric_for_description(tenant_id: str, description: str, *, base_was_empty: bool = False) -> bool:
    """Rubric follow-up for every Description write path (manual save, knowledge
    review apply, restore, document delete). Regenerates when the client opted in to
    auto-update; otherwise fills a missing rubric only when the Description has just
    gone from empty to filled (knowledge auto-sort spec §6.6). Best-effort, never
    blocks the save."""
    if not description:
        return False
    if _rubric_auto_update_enabled(tenant_id):
        force = True
    elif base_was_empty:
        force = False
    else:
        return False
    task = asyncio.create_task(_auto_generate_rubric(description, tenant_id, force=force))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return True


@router.put("/description")
async def update_description(
    payload: DescriptionUpdate,
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_owner),
):
    description = payload.description.strip()
    # Versioned write (knowledge auto-sort spec §7) -- every Description save can be undone.
    save_description(get_supabase(), tenant_id, description, "edit", ctx.get("user_id"))
    rubric_queued = queue_rubric_for_description(tenant_id, description)
    return {"description": description, "rubric_queued": rubric_queued}


@router.get("/app-link")
async def get_app_link(tenant_id: str = Depends(get_tenant_id)):
    return {"app_link": get_setting("app_download_link", tenant_id=tenant_id) or ""}


@router.put("/app-link")
async def update_app_link(payload: AppLinkUpdate, tenant_id: str = Depends(get_tenant_id)):
    app_link = payload.app_link.strip()
    save_setting("app_download_link", app_link, tenant_id=tenant_id)
    invalidate_cache("app_download_link")
    return {"app_link": app_link}
