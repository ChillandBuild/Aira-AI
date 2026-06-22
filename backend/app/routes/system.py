from fastapi import APIRouter, Depends
from app.config import settings
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_owner

router = APIRouter()


@router.get("/status", dependencies=[Depends(require_owner)])
async def status():
    db = get_supabase()

    prompt_row = (
        db.table("ai_prompts")
        .select("name,updated_at")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    active_prompt = prompt_row.data[0] if prompt_row.data else None

    return {
        "has_meta": bool(settings.meta_page_token),
        "has_gemini": False,
        "has_groq": bool(settings.groq_api_key),
        "supabase_url": settings.supabase_url,
        "active_prompt": active_prompt,
    }
