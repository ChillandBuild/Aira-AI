import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role

logger = logging.getLogger(__name__)
router = APIRouter()

MESSAGE_MAX = 2000


class CreateFeedback(BaseModel):
    message: str


def validate_feedback_message(raw: str) -> str:
    message = raw.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Feedback message is required")
    if len(message) > MESSAGE_MAX:
        raise HTTPException(status_code=400, detail=f"Feedback must be {MESSAGE_MAX} characters or fewer")
    return message


@router.post("")
async def create_feedback(payload: CreateFeedback, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    message = validate_feedback_message(payload.message)

    db = get_supabase()
    result = db.table("tenant_feedback").insert({
        "tenant_id": ctx["tenant_id"],
        "user_id": ctx["user_id"],
        "message": message,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
    return result.data[0]
