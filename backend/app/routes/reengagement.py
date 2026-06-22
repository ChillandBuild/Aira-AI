import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role

logger = logging.getLogger(__name__)
router = APIRouter()


class ReengagementStepCreate(BaseModel):
    type: str  # 'broadcast' or 'inbound'
    broadcast_id: str | None = None
    delay_hours: int
    target_segments: list[str]
    target_sources: list[str] | None = None  # None/empty = all sources
    message_type: str  # 'freeform' or 'template'
    message_content: str | None = None
    template_name: str | None = None
    template_variables: list[str] | None = None
    fallback_template_name: str | None = None
    fallback_template_variables: list[str] | None = None


@router.get("/steps")
def list_steps(
    type: str | None = None,
    broadcast_id: str | None = None,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can manage re-engagement")
    db = get_supabase()
    q = db.table("reengagement_steps").select("*").eq("tenant_id", ctx["tenant_id"])
    if type:
        q = q.eq("type", type)
    if broadcast_id:
        q = q.eq("broadcast_id", broadcast_id)
    
    rows = q.order("delay_hours").execute()
    return {"data": rows.data or []}


@router.post("/steps")
def create_step(
    payload: ReengagementStepCreate,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can manage re-engagement")
    if payload.type not in ("broadcast", "inbound"):
        raise HTTPException(status_code=400, detail="Invalid step type")
    if payload.message_type not in ("freeform", "template"):
        raise HTTPException(status_code=400, detail="Invalid message type")
    if payload.delay_hours <= 0:
        raise HTTPException(status_code=400, detail="delay_hours must be positive")
    if payload.delay_hours > 24:
        raise HTTPException(status_code=400, detail="delay_hours must be within the 24h window (1-24)")
    if payload.type == "broadcast" and not payload.broadcast_id:
        raise HTTPException(status_code=400, detail="broadcast_id is required for broadcast steps")
    valid_sources = {"organic", "meta_ads", "csv", "telegram", "instagram", "facebook"}
    if payload.target_sources and not set(payload.target_sources).issubset(valid_sources):
        raise HTTPException(status_code=400, detail="Invalid source in target_sources")

    db = get_supabase()
    row = {
        "tenant_id": ctx["tenant_id"],
        "type": payload.type,
        "broadcast_id": payload.broadcast_id,
        "delay_hours": payload.delay_hours,
        "target_segments": payload.target_segments,
        "target_sources": payload.target_sources or None,
        "message_type": payload.message_type,
        "message_content": payload.message_content,
        "template_name": payload.template_name,
        "template_variables": payload.template_variables,
        "fallback_template_name": payload.fallback_template_name,
        "fallback_template_variables": payload.fallback_template_variables,
    }
    res = db.table("reengagement_steps").insert(row).execute()
    return res.data[0] if res.data else {}


@router.get("/logs")
def list_logs(
    step_id: str | None = None,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can view re-engagement logs")
    db = get_supabase()
    q = (
        db.table("reengagement_logs")
        .select("id, step_id, lead_id, status, sent_at, leads(name, phone, segment)")
        .eq("tenant_id", ctx["tenant_id"])
    )
    if step_id:
        q = q.eq("step_id", step_id)
    rows = q.order("sent_at", desc=True).limit(500).execute()
    return {"data": rows.data or []}


@router.post("/trigger-now")
async def trigger_now(ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can trigger re-engagement")
    from app.services.reengagement_service import process_due_reengagements
    fired = await process_due_reengagements()
    return {"fired": fired}


@router.delete("/steps/{step_id}")
def delete_step(
    step_id: str,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can manage re-engagement")
    db = get_supabase()
    result = db.table("reengagement_steps").delete().eq("id", step_id).eq("tenant_id", ctx["tenant_id"]).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Step not found")
    return {"success": True}
