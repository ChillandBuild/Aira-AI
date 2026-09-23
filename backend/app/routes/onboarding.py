import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config_dynamic import get_setting, save_setting
from app.db.supabase import get_supabase
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id
from app.services.ai_reply import invalidate_prompt_cache

logger = logging.getLogger(__name__)
router = APIRouter()

_SETTING_KEYS: list[tuple[str, bool]] = [
    ("meta_phone_number_id", False), ("meta_access_token", True),
    ("meta_waba_id", False), ("meta_webhook_verify_token", True),
    ("meta_app_secret", True),
    ("telecmi_user_id", False), ("telecmi_secret", True),
    ("telecmi_callerid", False), ("telecmi_recording_base_url", False),
    ("sarvam_api_key", True), ("groq_api_key", True),
    ("gemini_api_key", True), ("openai_api_key", True),
    ("jina_api_key", True),
    ("ai_reply_model", False),
    ("telegram_bot_token", True),
    ("instagram_page_id", False), ("instagram_access_token", True),
    ("facebook_page_id", False), ("facebook_access_token", True),
    ("ai_auto_reply_enabled", False),
    ("ai_voice_reply_enabled", False),
    ("ai_voice_reply_speaker", False),
    ("ai_media_recommendations_enabled", False),
    ("catalog_ai_max_images_ceiling", False),
]


def _seed_app_settings(db, tenant_id: str) -> None:
    try:
        db.table("app_settings").insert([
            {"tenant_id": tenant_id, "key": k, "value": None, "is_secret": s}
            for k, s in _SETTING_KEYS
        ]).execute()
    except Exception as e:
        logger.warning(f"Failed to seed app_settings for tenant {tenant_id}: {e}")


class CreateTenantPayload(BaseModel):
    name: str


@router.post("/")
def create_tenant(payload: CreateTenantPayload, user: dict = Depends(get_current_user)):
    db = get_supabase()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tenant name is required")

    existing = (
        db.table("tenant_users")
        .select("tenant_id")
        .eq("user_id", user["user_id"])
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return {"tenant_id": existing.data["tenant_id"], "already_exists": True}

    tenant = db.table("tenants").insert({"name": name}).execute()
    tenant_id = tenant.data[0]["id"]

    db.table("tenant_users").insert({
        "tenant_id": tenant_id,
        "user_id": user["user_id"],
        "role": "owner",
    }).execute()

    _seed_app_settings(db, tenant_id)

    try:
        db.table("callers").insert({
            "tenant_id": tenant_id,
            "user_id": user["user_id"],
            "name": "Admin",
            "active": True,
            "status": "active",
            "overall_score": 10.0,
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to seed admin caller for tenant {tenant_id}: {e}")

    logger.info(f"Tenant created: {tenant_id} for user {user['user_id']}")
    return {"tenant_id": tenant_id, "already_exists": False}


@router.get("/status")
def tenant_status(user: dict = Depends(get_current_user)):
    db = get_supabase()
    result = (
        db.table("tenant_users")
        .select("tenant_id, role")
        .eq("user_id", user["user_id"])
        .maybe_single()
        .execute()
    )
    admin = (
        db.table("system_admins")
        .select("user_id")
        .eq("user_id", user["user_id"])
        .limit(1)
        .execute()
    )
    is_system_admin = bool(admin and admin.data)

    if not result or not result.data:
        return {"has_tenant": False, "is_system_admin": is_system_admin}
    return {
        "has_tenant": True,
        "tenant_id": result.data["tenant_id"],
        "role": result.data["role"],
        "is_system_admin": is_system_admin,
    }


@router.get("/starters")
def list_starters():
    """Zero-AI-calls fallback for a brand-new self-serve tenant: hand-written
    starting points, applied verbatim. Not the AI-drafted interview -- that
    needs a provider key, which a fresh tenant never has yet."""
    db = get_supabase()
    result = (
        db.table("vertical_starters")
        .select("key, label, master_prompt, business_description")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return {"data": result.data or []}


class ApplyStarterPayload(BaseModel):
    key: str
    force: bool = False


def _check_not_customised(db, tenant_id: str, force: bool) -> None:
    """Shared clobber guard for apply-starter and the interview's apply step.
    Raw table read, not _get_prompt(): that function falls back to a
    hardcoded default when no row exists, which would make an un-customised
    tenant look "already customised" and block every starter/draft forever."""
    if force:
        return
    existing_prompt = (
        db.table("ai_prompts")
        .select("content")
        .eq("tenant_id", tenant_id)
        .eq("name", "master")
        .maybe_single()
        .execute()
    )
    has_custom_prompt = bool(existing_prompt and existing_prompt.data and (existing_prompt.data.get("content") or "").strip())
    has_custom_description = bool((get_setting("business_description", tenant_id=tenant_id) or "").strip())

    if has_custom_prompt or has_custom_description:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This workspace already has a customised prompt or business description.",
                "would_overwrite": {
                    "master_prompt": has_custom_prompt,
                    "business_description": has_custom_description,
                },
            },
        )


def _apply_prompt_and_description(db, tenant_id: str, master_prompt: str, business_description: str) -> None:
    db.table("ai_prompts").upsert(
        {"tenant_id": tenant_id, "name": "master", "content": master_prompt},
        on_conflict="tenant_id,name",
    ).execute()
    invalidate_prompt_cache("master")
    save_setting("business_description", business_description, tenant_id=tenant_id)


@router.post("/apply-starter")
def apply_starter(payload: ApplyStarterPayload, user: dict = Depends(get_current_user), tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()

    starter = (
        db.table("vertical_starters")
        .select("key, master_prompt, business_description")
        .eq("key", payload.key)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not starter or not starter.data:
        raise HTTPException(status_code=404, detail="Unknown starter")

    _check_not_customised(db, tenant_id, payload.force)
    _apply_prompt_and_description(db, tenant_id, starter.data["master_prompt"], starter.data["business_description"])

    return {"applied": starter.data["key"]}


INTERVIEW_QUESTIONS = [
    {"id": "what_you_sell", "question": "What does your business sell, and who buys it?"},
    {"id": "never_promise", "question": "What should the AI never promise or claim?"},
    {"id": "hand_over", "question": "When should the AI stop and hand the chat to a real person?"},
]


@router.get("/interview/questions")
def interview_questions():
    return {"data": INTERVIEW_QUESTIONS}


class InterviewAnswer(BaseModel):
    question_id: str
    answer: str


class InterviewDraftPayload(BaseModel):
    answers: list[InterviewAnswer]


_DRAFT_SYSTEM_PROMPT = """You are helping set up a WhatsApp AI assistant for a new business client, \
based on their own answers below. Write two things and return ONLY a JSON object with exactly these \
two keys, nothing else, no markdown fences:

{"master_prompt": "...", "business_description": "..."}

master_prompt: instructions telling the assistant HOW to behave -- tone, what it should never promise, \
and when it must hand over to a human. Write it as direct instructions to the assistant, in English, \
3-6 sentences.

business_description: a factual description of WHAT the business sells and WHO it sells to, ending with \
a line starting "HAND OVER TO A PERSON WHEN:" and a line starting "WHAT YOU MUST NEVER DO:", each filled \
in from the client's own answers. 3-6 sentences plus those two lines.

Use only what the client actually said below -- do not invent products, promises, or policies they did \
not mention."""


@router.post("/interview/draft")
async def interview_draft(payload: InterviewDraftPayload, tenant_id: str = Depends(get_tenant_id)):
    """Runs on the tenant's OWN configured AI provider -- never a shared
    platform key (see _resolve_provider's docstring: no fallback, ever).
    A tenant with no provider connected yet gets a clear 400, not a 500."""
    if not payload.answers:
        raise HTTPException(status_code=400, detail="At least one answer is required")

    qa_text = "\n".join(f"Q: {a.question_id}\nA: {a.answer.strip()}" for a in payload.answers if a.answer.strip())
    if not qa_text:
        raise HTTPException(status_code=400, detail="At least one answer is required")

    from app.services.ai_reply import _llm_chat

    try:
        raw = await _llm_chat(
            [
                {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": qa_text},
            ],
            max_tokens=700,
            tenant_id=tenant_id,
            purpose="onboarding_interview",
            temperature=0.4,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=400,
            detail="Connect an AI provider (Sarvam, Groq, Gemini or OpenAI) in Settings before running the interview.",
        )

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        draft = json.loads(cleaned)
        master_prompt = draft["master_prompt"].strip()
        business_description = draft["business_description"].strip()
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        logger.warning(f"Interview draft parse failed for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=502, detail="The AI's draft could not be read. Try again.")

    if not master_prompt or not business_description:
        raise HTTPException(status_code=502, detail="The AI's draft was incomplete. Try again.")

    return {"master_prompt": master_prompt, "business_description": business_description}


class ApplyDraftPayload(BaseModel):
    master_prompt: str
    business_description: str
    force: bool = False


@router.post("/interview/apply")
def interview_apply(payload: ApplyDraftPayload, tenant_id: str = Depends(get_tenant_id)):
    """Applies a draft the client has already seen and (possibly edited) --
    the interview never writes anything before this explicit step."""
    master_prompt = payload.master_prompt.strip()
    business_description = payload.business_description.strip()
    if not master_prompt or not business_description:
        raise HTTPException(status_code=400, detail="Both master_prompt and business_description are required")

    db = get_supabase()
    _check_not_customised(db, tenant_id, payload.force)
    _apply_prompt_and_description(db, tenant_id, master_prompt, business_description)

    return {"applied": True}
