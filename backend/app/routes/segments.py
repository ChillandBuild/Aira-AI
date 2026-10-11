import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.ai_reply import send_whatsapp

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


@router.post("/{segment}/broadcast")
async def broadcast_to_segment(
    segment: str = Path(pattern="^[ABCD]$"),
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_leads_manage),
):
    db = get_supabase()

    tpl = db.table("segment_templates").select("*").eq("segment", segment).eq("tenant_id", tenant_id).limit(1).execute()
    if not tpl.data or not (tpl.data[0].get("message") or "").strip():
        raise HTTPException(status_code=400, detail="Template is empty — save a message first")
    if not tpl.data[0].get("enabled"):
        raise HTTPException(status_code=400, detail="Template is disabled")
    message = tpl.data[0]["message"]

    leads = db.table("leads").select("id,phone").eq("segment", segment).eq("tenant_id", tenant_id).execute()
    targets = leads.data or []
    if not targets:
        return {"sent": 0, "failed": 0, "skipped_window": 0, "total": 0}

    # WhatsApp 24h rule: only free-form to leads with an inbound msg in the last 24h.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    lead_ids = [t["id"] for t in targets]
    recent = (
        db.table("messages")
        .select("lead_id")
        .eq("direction", "inbound")
        .eq("tenant_id", tenant_id)
        .gte("created_at", cutoff)
        .in_("lead_id", lead_ids)
        .execute()
    )
    eligible_ids = {r["lead_id"] for r in (recent.data or [])}

    sent = 0
    failed = 0
    skipped_window = 0
    for t in targets:
        if t["id"] not in eligible_ids:
            skipped_window += 1
            continue
        sid = await send_whatsapp(t["phone"], message, tenant_id=tenant_id)
        if sid:
            sent += 1
            db.table("messages").insert({
                "lead_id": t["id"],
                "tenant_id": tenant_id,
                "direction": "outbound",
                "channel": "whatsapp",
                "content": message,
                "is_ai_generated": False,
                "meta_message_id": sid,
            }).execute()
        else:
            failed += 1

    return {
        "total": len(targets),
        "sent": sent,
        "failed": failed,
        "skipped_window": skipped_window,
    }
