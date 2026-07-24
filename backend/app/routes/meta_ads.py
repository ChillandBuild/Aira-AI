"""Meta Ads dashboard — read-only full-account performance + analytics.
Reporting only (ads_read). Ad creation/management is a separate router (Plan 2)."""
import logging
from fastapi import APIRouter, Depends, Query, Body, UploadFile, File
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSpec(BaseModel):
    name: str
    creative_label: str
    message: str
    headline: str
    greeting: str
    image_hash: str
    page_id: str
    location_countries: list[str] = ["IN"]
    age_min: int = 18
    age_max: int = 65
    gender: str = "all"
    daily_budget_inr: float | None = None
    lifetime_budget_inr: float | None = None
    special_ad_category: str | None = None


@router.get("/performance")
async def performance(
    level: str = Query("campaign", pattern="^(campaign|adset|ad)$"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    from app.services.meta_ads_reporting import build_account_performance
    db = get_supabase()
    try:
        rows = build_account_performance(db, tenant_id, level=level,
                                         date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"meta-ads performance error: {e}")
        rows = []
    return {"data": rows}


@router.get("/analytics")
async def analytics(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    from app.services.meta_ads_analytics import build_analytics
    db = get_supabase()
    try:
        data = build_analytics(db, tenant_id, date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"meta-ads analytics error: {e}")
        data = {"kpis": {}, "funnel": [], "leaderboard": [], "trend": [],
                "heatmap": [], "quadrant": [], "spend_distribution": []}
    return {"data": data}


@router.get("/filters")
async def filters(tenant_id: str = Depends(get_tenant_id)):
    from app.services.ad_performance import build_ad_filter_tree
    db = get_supabase()
    return build_ad_filter_tree(db, tenant_id)


@router.get("/pages")
async def pages(tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_insights_sync import _get_ads_credentials
    from app.services.meta_ads_manager import list_pages
    db = get_supabase()
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"data": []}
    token, account = creds
    try:
        return {"data": list_pages(token, account)}
    except Exception as e:
        logger.error(f"meta-ads pages error: {e}")
        return {"data": []}


@router.get("/whatsapp-numbers")
async def whatsapp_numbers(tenant_id: str = Depends(get_tenant_id)):
    from app.routes.inbound_leads import _primary_whatsapp_number
    db = get_supabase()
    num = _primary_whatsapp_number(db, tenant_id)
    return {"data": [{"number": num}] if num else []}


@router.post("/media")
async def media(file: UploadFile = File(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_insights_sync import _get_ads_credentials
    from app.services.meta_ads_manager import upload_image
    db = get_supabase()
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"image_hash": "", "error": "No credentials configured."}
    token, account = creds
    try:
        data = await file.read()
        return {"image_hash": upload_image(token, account, data, file.filename or "ad.jpg")}
    except Exception as e:
        logger.error(f"meta-ads media upload error: {e}")
        return {"image_hash": "", "error": str(e)}


@router.post("/campaigns")
async def create_campaign(spec: CreateSpec, tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import create_full_campaign
    db = get_supabase()
    return create_full_campaign(db, tenant_id, spec=spec.model_dump())


@router.post("/{campaign_id}/status")
async def set_status(campaign_id: str, body: dict = Body(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import set_campaign_status
    db = get_supabase()
    return set_campaign_status(db, tenant_id, campaign_id, bool(body.get("active")))


@router.patch("/{campaign_id}/budget")
async def set_budget(campaign_id: str, body: dict = Body(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import update_campaign_budget
    db = get_supabase()
    return update_campaign_budget(db, tenant_id, campaign_id,
                                  daily_budget_inr=body.get("daily_budget_inr"),
                                  lifetime_budget_inr=body.get("lifetime_budget_inr"))
