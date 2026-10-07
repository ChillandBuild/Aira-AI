"""Lead page: Send details on WhatsApp (call wrap-up v2 spec §5)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.call_details_share import ShareError, send_details, share_context

router = APIRouter()


def require_share_permission(ctx: dict = Depends(get_tenant_and_role)) -> dict:
    permissions = set(ctx.get("permissions") or [])
    if ctx.get("role") == "owner" or permissions & {"telecalling.dialer", "conversations.reply"}:
        return ctx
    raise HTTPException(status_code=403, detail="Permission required: telecalling.dialer")


class SendDetailsIn(BaseModel):
    text: str | None = Field(None, max_length=4096)
    template_id: str | None = Field(None, max_length=64)
    variables: list[str] = Field(default_factory=list, max_length=20)


@router.get("/{lead_id}/send-details")
def get_send_details(lead_id: UUID, ctx: dict = Depends(require_share_permission)):
    context = share_context(get_supabase(), ctx["tenant_id"], str(lead_id), now=datetime.now(timezone.utc))
    if context is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return context


@router.post("/{lead_id}/send-details")
async def post_send_details(lead_id: UUID, payload: SendDetailsIn, ctx: dict = Depends(require_share_permission)):
    if (payload.text is None) == (payload.template_id is None):
        raise HTTPException(status_code=400, detail="Send either a message or a template")
    try:
        return await send_details(
            get_supabase(), ctx["tenant_id"], str(lead_id), text=payload.text, template_id=payload.template_id,
            variables=payload.variables, now=datetime.now(timezone.utc),
        )
    except ShareError as e:
        raise HTTPException(status_code=400, detail=str(e))
