from fastapi import APIRouter, Depends
from app.config import settings
from app.dependencies.tenant import require_owner

router = APIRouter(dependencies=[Depends(require_owner)])


@router.get("/status", dependencies=[Depends(require_owner)])
async def status():
    return {
        "has_meta": bool(settings.meta_page_token),
        "has_gemini": False,
        "has_sarvam": bool(settings.sarvam_api_key),
        "has_groq": bool(settings.groq_api_key),
        "supabase_url": settings.supabase_url,
    }
