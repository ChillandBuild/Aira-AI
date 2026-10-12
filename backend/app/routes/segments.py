import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()
require_leads_view = require_permission("leads.view")
require_leads_manage = require_permission("leads.manage")

SEGMENTS = ("A", "B", "C", "D")


class TemplateUpdate(BaseModel):
    message: str
    enabled: bool = True


def _ensure_templates(db, tenant_id: str) -> list[dict]:
    existing = db.table("segment_templates").select("*").eq("tenant_id", tenant_id).execute()
    present = {r["segment"] for r in (existing.data or [])}
    missing = [{"segment": s, "message": "", "enabled": True, "tenant_id": tenant_id} for s in SEGMENTS if s not in present]
    if missing:
        db.table("segment_templates").insert(missing).execute()
        existing = db.table("segment_templates").select("*").eq("tenant_id", tenant_id).execute()
    return sorted(existing.data or [], key=lambda r: r["segment"])


@router.get("/templates")
async def list_templates(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_leads_view),
):
    db = get_supabase()
    return {"data": _ensure_templates(db, tenant_id)}


@router.put("/templates/{segment}")
async def upsert_template(
    updates: TemplateUpdate,
    segment: str = Path(pattern="^[ABCD]$"),
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_leads_manage),
):
    db = get_supabase()
    _ensure_templates(db, tenant_id)
    result = (
        db.table("segment_templates")
        .update({"message": updates.message, "enabled": updates.enabled})
        .eq("segment", segment)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return result.data[0]
