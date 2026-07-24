"""Meta Ads dashboard — read-only full-account performance + analytics.
Reporting only (ads_read). Ad creation/management is a separate router (Plan 2)."""
import logging
from fastapi import APIRouter, Depends, Query

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()


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
