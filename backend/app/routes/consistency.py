"""Where Aira's sources disagree with the Services page, and one-click fixes
(services/consistency.py)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services import consistency

router = APIRouter()
require_read = require_permission("knowledge.view")
require_manage = require_permission("knowledge.manage")


class FixBody(BaseModel):
    text: str | None = Field(default=None, max_length=2_000)


@router.get("")
async def get_report(ctx: dict = Depends(require_read)):
    return consistency.current_report(get_supabase(), ctx["tenant_id"])


@router.post("/check")
async def check_now(ctx: dict = Depends(require_manage)):
    report = await consistency.run_check(get_supabase(), ctx["tenant_id"])
    complete = report.get("suggestions_complete", True)
    return {"issues": report["issues"], "checked_at": report["checked_at"], "stale": not complete,
            "suggestions_complete": complete}


@router.post("/issues/{issue_id}/fix")
async def fix_issue(
    issue_id: str,
    body: FixBody,
    background_tasks: BackgroundTasks,
    ctx: dict = Depends(require_manage),
):
    tenant_id = ctx["tenant_id"]
    try:
        result = consistency.apply_fix(
            get_supabase(), tenant_id, issue_id[:32],
            user_id=ctx.get("user_id"), is_owner=ctx.get("role") == "owner", text=body.text,
        )
    except consistency.FixError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    if result.get("where") == "knowledge":
        from app.services import knowledge_sort as ks

        background_tasks.add_task(
            ks.index_facts, tenant_id, result["document_id"], result["facts"], result.get("campaign_tag_id"),
        )
    return {"success": True}


@router.post("/issues/{issue_id}/dismiss")
async def dismiss_issue(issue_id: str, ctx: dict = Depends(require_manage)):
    consistency.dismiss(ctx["tenant_id"], issue_id[:32])
    return {"success": True}
