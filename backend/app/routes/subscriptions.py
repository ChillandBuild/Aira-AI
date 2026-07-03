import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.subscription_requests import submit_request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/catalog")
def get_catalog(ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    catalog = db.table("feature_catalog").select(
        "feature_key, display_name, category, monthly_price, unit_price, included_qty, usage_metric"
    ).order("sort_order").execute()
    packages = db.table("plans").select(
        "id, name, monthly_price, feature_keys, discount_percent"
    ).eq("active", True).order("created_at").execute()
    return {"catalog": catalog.data or [], "packages": packages.data or []}


@router.get("/me")
def get_my_subscription(ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]

    sub = db.table("tenant_subscriptions").select("status, mrr").eq("tenant_id", tenant_id).maybe_single().execute()
    items = db.table("tenant_subscription_items").select("feature_key, quantity, unit_price_snapshot").eq("tenant_id", tenant_id).execute()

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    usage = db.table("tenant_usage_counters").select("metric, used, included, hard_cap").eq("tenant_id", tenant_id).eq("period", period).execute()

    pending = db.table("subscription_requests").select(
        "id, requested_items, total_amount, submitted_at, status, rejection_reason"
    ).eq("tenant_id", tenant_id).order("submitted_at", desc=True).limit(1).execute()
    latest_request = (pending.data or [None])[0]

    return {
        "status": (sub.data or {}).get("status", "none"),
        "mrr": (sub.data or {}).get("mrr", 0),
        "items": items.data or [],
        "usage": usage.data or [],
        "latest_request": latest_request,
    }


class SubmitItem(BaseModel):
    feature_key: str
    quantity: int = 1


class SubmitRequestPayload(BaseModel):
    package_id: str | None = None
    items: list[SubmitItem]


@router.post("/requests")
def create_subscription_request(payload: SubmitRequestPayload, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can manage the subscription")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    db = get_supabase()
    result = submit_request(
        db,
        ctx["tenant_id"],
        requested_items=[item.model_dump() for item in payload.items],
        package_id=payload.package_id,
    )
    return {"data": result}
