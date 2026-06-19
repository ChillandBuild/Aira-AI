import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role, require_owner

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])


class ScriptStep(BaseModel):
    order: int
    text: str
    note: str | None = None
    branches: list[dict] | None = None


class CreateScript(BaseModel):
    name: str
    segment: str | None = None
    steps: list[ScriptStep]
    is_default: bool = False


class UpdateScript(BaseModel):
    name: str | None = None
    segment: str | None = None
    steps: list[ScriptStep] | None = None
    is_default: bool | None = None
    active: bool | None = None


def get_script_for_call(tenant_id: str, segment: str) -> dict | None:
    """Resolve best script: segment-matching > default script."""
    db = get_supabase()

    segment_script = (
        db.table("call_scripts")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("segment", segment)
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if segment_script.data:
        return segment_script.data[0]

    default_script = (
        db.table("call_scripts")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_default", True)
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if default_script.data:
        return default_script.data[0]

    return None


@router.get("")
async def list_scripts(ctx: dict = Depends(get_tenant_and_role)) -> list:
    db = get_supabase()
    result = (
        db.table("call_scripts")
        .select("*")
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/resolve")
async def resolve_script(
    segment: str = Query(..., description="Segment A/B/C/D"),
    ctx: dict = Depends(get_tenant_and_role)
) -> dict | None:
    if segment not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="Segment must be A, B, C, or D")

    script = get_script_for_call(ctx["tenant_id"], segment)
    return script


@router.get("/{script_id}")
async def get_script(script_id: str, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    db = get_supabase()
    result = (
        db.table("call_scripts")
        .select("*")
        .eq("id", script_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Script not found")
    return result.data


@router.post("")
async def create_script(payload: CreateScript, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    if payload.segment is not None and payload.segment not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="Segment must be A, B, C, or D")

    db = get_supabase()

    if payload.is_default:
        db.table("call_scripts").update({"is_default": False}).eq("tenant_id", ctx["tenant_id"]).execute()

    steps_data = [step.model_dump() for step in payload.steps]

    result = db.table("call_scripts").insert({
        "tenant_id": ctx["tenant_id"],
        "name": payload.name,
        "segment": payload.segment,
        "steps": steps_data,
        "is_default": payload.is_default,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create script")

    return result.data[0]


@router.patch("/{script_id}")
async def update_script(
    script_id: str,
    payload: UpdateScript,
    ctx: dict = Depends(get_tenant_and_role)
) -> dict:
    db = get_supabase()

    script = (
        db.table("call_scripts")
        .select("*")
        .eq("id", script_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not script.data:
        raise HTTPException(status_code=404, detail="Script not found")

    if payload.segment is not None and payload.segment not in ("A", "B", "C", "D"):
        raise HTTPException(status_code=400, detail="Segment must be A, B, C, or D")

    if payload.is_default:
        db.table("call_scripts").update({"is_default": False}).eq("tenant_id", ctx["tenant_id"]).execute()

    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.segment is not None:
        updates["segment"] = payload.segment
    if payload.steps is not None:
        updates["steps"] = [step.model_dump() for step in payload.steps]
    if payload.is_default is not None:
        updates["is_default"] = payload.is_default
    if payload.active is not None:
        updates["active"] = payload.active

    if not updates:
        return script.data

    result = db.table("call_scripts").update(updates).eq("id", script_id).eq("tenant_id", ctx["tenant_id"]).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update script")

    return result.data[0]


@router.delete("/{script_id}")
async def delete_script(script_id: str, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    db = get_supabase()

    script = (
        db.table("call_scripts")
        .select("id")
        .eq("id", script_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not script.data:
        raise HTTPException(status_code=404, detail="Script not found")

    db.table("call_scripts").delete().eq("id", script_id).eq("tenant_id", ctx["tenant_id"]).execute()

    return {"deleted": True}
