"""Anril Brain for the client dashboard: GET /api/v1/brain and GET /api/v1/brain/count
(services/brain). Read-only; both need brain.view."""
from fastapi import APIRouter, Depends

from app.dependencies.tenant import require_permission
from app.services.brain import brain_count, build_brain

router = APIRouter()
require_read = require_permission("brain.view")


@router.get("")
def get_brain(ctx: dict = Depends(require_read)):
    return build_brain(ctx["tenant_id"], role=ctx.get("role"), permissions=ctx.get("permissions") or [])


@router.get("/count")
def get_count(ctx: dict = Depends(require_read)):
    return brain_count(ctx["tenant_id"])
