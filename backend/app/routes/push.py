from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.web_push import vapid_public_key

router = APIRouter()


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: PushKeys


@router.get("/public-key")
async def get_public_key():
    return {"public_key": vapid_public_key()}


@router.post("/subscriptions")
async def save_subscription(
    payload: PushSubscriptionIn,
    request: Request,
    ctx: dict = Depends(get_tenant_and_role),
):
    user_id = ctx.get("user_id")
    tenant_id = ctx["tenant_id"]
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user")

    db = get_supabase()
    row = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "endpoint": payload.endpoint,
        "p256dh": payload.keys.p256dh,
        "auth": payload.keys.auth,
        "user_agent": request.headers.get("user-agent"),
        "updated_at": "now()",
    }
    db.table("push_subscriptions").upsert(row, on_conflict="user_id,endpoint").execute()
    return {"saved": True}


@router.delete("/subscriptions")
async def delete_subscription(endpoint: str, ctx: dict = Depends(get_tenant_and_role)):
    user_id = ctx.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user")
    db = get_supabase()
    db.table("push_subscriptions").delete().eq("user_id", user_id).eq("endpoint", endpoint).execute()
    return {"deleted": True}
