import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role, require_owner
from app.services.meta_cloud import BUTTON_COUNT_MAX, BUTTON_TITLE_MAX
from app.services.quick_replies import BODY_TEXT_MAX, MAX_BLOCKS_PER_TENANT

logger = logging.getLogger(__name__)
router = APIRouter()


class QuickReplyButton(BaseModel):
    id: str | None = None
    label: str


class CreateBlock(BaseModel):
    name: str
    use_when: str
    body_text: str
    buttons: list[QuickReplyButton]
    is_active: bool = True


class UpdateBlock(BaseModel):
    name: str | None = None
    use_when: str | None = None
    body_text: str | None = None
    buttons: list[QuickReplyButton] | None = None
    is_active: bool | None = None


def slugify_label(label: str) -> str:
    """Stable button id from its label. Returned in button_reply.id on a tap."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "option"


def validate_block(name: str, use_when: str, body_text: str, buttons: list) -> None:
    """Reject anything WhatsApp or the tool contract cannot carry.

    The UI blocks these too, but the API is the boundary that actually matters --
    an over-long label stored here would raise at send time, mid-conversation.
    """
    if not (name or "").strip():
        raise HTTPException(status_code=400, detail="Block name is required")
    if not (use_when or "").strip():
        raise HTTPException(
            status_code=400,
            detail="'Use when' is required — it is what the AI reads to decide when to send this",
        )
    if not (body_text or "").strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    if len(body_text) > BODY_TEXT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Message text must be {BODY_TEXT_MAX} characters or fewer",
        )
    if not (1 <= len(buttons) <= BUTTON_COUNT_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"A block needs between 1 and {BUTTON_COUNT_MAX} buttons",
        )
    for b in buttons:
        label = (b.get("label") if isinstance(b, dict) else b.label) or ""
        if not label.strip():
            raise HTTPException(status_code=400, detail="Button labels cannot be empty")
        if len(label) > BUTTON_TITLE_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"Button label {label!r} must be {BUTTON_TITLE_MAX} characters or fewer",
            )


def _normalise_buttons(buttons: list[QuickReplyButton]) -> list[dict]:
    return [
        {"id": (b.id or slugify_label(b.label)), "label": b.label.strip()}
        for b in buttons
    ]


@router.get("")
async def list_blocks(ctx: dict = Depends(get_tenant_and_role)) -> list:
    db = get_supabase()
    result = (
        db.table("quick_reply_blocks")
        .select("*")
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at")
        .execute()
    )
    return result.data or []


@router.post("", dependencies=[Depends(require_owner)])
async def create_block(payload: CreateBlock, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    validate_block(payload.name, payload.use_when, payload.body_text, payload.buttons)
    db = get_supabase()

    existing = (
        db.table("quick_reply_blocks")
        .select("id")
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    if len(existing.data or []) >= MAX_BLOCKS_PER_TENANT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"At most {MAX_BLOCKS_PER_TENANT} blocks per workspace — the list is sent "
                "to the AI on every reply, so a longer one slows and confuses matching."
            ),
        )

    result = db.table("quick_reply_blocks").insert({
        "tenant_id": ctx["tenant_id"],
        "name": payload.name.strip(),
        "use_when": payload.use_when.strip(),
        "body_text": payload.body_text,
        "buttons": _normalise_buttons(payload.buttons),
        "is_active": payload.is_active,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create block")
    return result.data[0]


@router.patch("/{block_id}", dependencies=[Depends(require_owner)])
async def update_block(
    block_id: str, payload: UpdateBlock, ctx: dict = Depends(get_tenant_and_role)
) -> dict:
    db = get_supabase()
    current = (
        db.table("quick_reply_blocks")
        .select("*")
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not current or not current.data:
        raise HTTPException(status_code=404, detail="Block not found")
    row = current.data

    name = payload.name if payload.name is not None else row["name"]
    use_when = payload.use_when if payload.use_when is not None else row["use_when"]
    body_text = payload.body_text if payload.body_text is not None else row["body_text"]
    if payload.buttons is not None:
        buttons = _normalise_buttons(payload.buttons)
    else:
        buttons = row["buttons"]
    validate_block(name, use_when, body_text, buttons)

    patch = {
        "name": name.strip(),
        "use_when": use_when.strip(),
        "body_text": body_text,
        "buttons": buttons,
    }
    if payload.is_active is not None:
        patch["is_active"] = payload.is_active

    result = (
        db.table("quick_reply_blocks")
        .update(patch)
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update block")
    return result.data[0]


@router.delete("/{block_id}", dependencies=[Depends(require_owner)])
async def delete_block(block_id: str, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    db = get_supabase()
    (
        db.table("quick_reply_blocks")
        .delete()
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    return {"ok": True}
