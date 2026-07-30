"""
Inbound Leads — all leads that arrived through a messaging channel.

Inbound universe:  source IN ('whatsapp','instagram','facebook','telegram')
  (upload / manual leads are NOT inbound and never appear here)

Origin (independent of channel):
  ad_campaign_id IS NOT NULL  →  origin = "ad"      (clicked a Meta Ad CTA)
  ad_campaign_id IS NULL      →  origin = "organic" (messaged directly)

The "keyword" is the first inbound message the lead sent — for ad leads this is
the pre-filled CTA text; for organic leads it is just their opening message.
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id
from app.services.inbound_leads_logic import INBOUND_SOURCES
from app.services.google_ads_attribution import build_tracked_wa_link, slugify_campaign

logger = logging.getLogger(__name__)
router = APIRouter()

CHANNEL_LABELS = {
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "telegram": "Telegram",
}

SEGMENT_LABELS = {
    "A": "Hot",
    "B": "Warm",
    "C": "Cold",
    "D": "Disqualified",
}


class MetaAdTrackingCodeRequest(BaseModel):
    ad_creative_id: str
    message: str = Field(
        default="Hi, I'm interested in this service.",
        min_length=1,
        max_length=500,
    )


def _fmt_ist(iso: str) -> str:
    """Format UTC ISO timestamp to IST string."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        ist = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return ist.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return iso


def _fetch_inbound_leads(
    db,
    tenant_id: str,
    *,
    origin: str = "all",
    segment: str | None = None,
    ad_campaign_id: str | None = None,
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """
    Fetch inbound leads (source in INBOUND_SOURCES). Returns (rows, total_count).
    origin: "all" | "organic" | "ad". Two simple queries, no JOIN.
    """
    def _apply_common(q):
        q = (
            q.eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
        )
        if origin == "ad":
            q = q.not_.is_("ad_campaign_id", "null")
        elif origin == "organic":
            q = q.is_("ad_campaign_id", "null")
        if segment:
            q = q.eq("segment", segment)
        if ad_campaign_id:
            q = q.eq("ad_campaign_id", ad_campaign_id)
        if source:
            q = q.eq("source", source)
        if date_from:
            q = q.gte("created_at", date_from)
        if date_to:
            q = q.lte("created_at", date_to)
        return q

    data_q = _apply_common(
        db.table("leads").select(
            "id,phone,name,source,score,segment,created_at,ad_campaign_id"
        )
    )
    data_result = (
        data_q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    rows = data_result.data or []

    count_q = _apply_common(db.table("leads").select("id", count="exact"))
    count_result = count_q.execute()
    total = count_result.count or len(rows)

    return rows, total


def _fetch_campaign_names(db, tenant_id: str, campaign_ids: list[str]) -> dict[str, str]:
    """Look up campaign names for a set of campaign IDs. Returns {id: name}."""
    if not campaign_ids:
        return {}
    result = (
        db.table("ad_campaigns")
        .select("id,campaign_name")
        .in_("id", campaign_ids)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return {row["id"]: row["campaign_name"] for row in (result.data or [])}


def _fetch_first_keywords(db, tenant_id: str, lead_ids: list[str]) -> dict[str, str]:
    """
    For each lead_id, fetch the first inbound message (the CTA keyword/pre-fill text).
    Returns {lead_id: first_message_content}.
    """
    if not lead_ids:
        return {}
    # Explicit high limit: PostgREST caps at 1000 rows by default, which would
    # silently drop keywords for leads beyond that window on large exports.
    result = (
        db.table("messages")
        .select("lead_id,content,created_at")
        .in_("lead_id", lead_ids)
        .eq("tenant_id", tenant_id)
        .eq("direction", "inbound")
        .order("created_at", desc=False)
        .limit(50000)
        .execute()
    )
    keyword_map: dict[str, str] = {}
    for msg in (result.data or []):
        lid = msg.get("lead_id", "")
        if lid and lid not in keyword_map:
            keyword_map[lid] = (msg.get("content") or "").strip()
    return keyword_map


def _enrich(
    leads: list[dict],
    campaign_map: dict[str, str],
    keyword_map: dict[str, str],
) -> list[dict]:
    """Attach campaign name, keyword, and origin to each lead row."""
    enriched = []
    for lead in leads:
        cid = lead.get("ad_campaign_id") or ""
        src = lead.get("source", "whatsapp")
        enriched.append({
            "id": lead.get("id", ""),
            "phone": lead.get("phone") or "—",
            "name": lead.get("name") or "—",
            "source": src,
            "channel_label": CHANNEL_LABELS.get(src, src.title()),
            "origin": "ad" if lead.get("ad_campaign_id") else "organic",
            "score": lead.get("score", 5),
            "segment": lead.get("segment", "C"),
            "segment_label": SEGMENT_LABELS.get(lead.get("segment", "C"), "—"),
            "created_at": lead.get("created_at", ""),
            "ad_campaign_id": cid,
            "campaign_name": campaign_map.get(cid, "Unknown Campaign"),
            "keyword": keyword_map.get(lead.get("id", ""), "—") or "—",
        })
    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(tenant_id: str = Depends(get_tenant_id)):
    """Return all ad campaigns for this tenant (used for filter dropdown)."""
    db = get_supabase()
    try:
        result = (
            db.table("ad_campaigns")
            .select("id,campaign_name,platform")
            .eq("tenant_id", tenant_id)
            .order("campaign_name")
            .execute()
        )
        return {"data": result.data or []}
    except Exception as e:
        logger.error(f"inbound-leads campaigns fetch error: {e}")
        return {"data": []}


def _primary_whatsapp_number(db, tenant_id: str) -> str | None:
    """The tenant's active primary WhatsApp number, for building wa.me links."""
    result = (
        db.table("phone_numbers")
        .select("number,role")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    primary = next((r for r in rows if r.get("role") == "primary"), None)
    return (primary or rows[0]).get("number")


@router.get("/google-link")
async def generate_google_ads_link(
    campaign: str = Query(..., min_length=1, max_length=80),
    gclid: str | None = Query(None, max_length=200),
    tenant_id: str = Depends(get_tenant_id),
):
    """Generate a tracked wa.me link for a Google Ads campaign CTA.

    The returned link carries a [GADS:<slug>] tag in its pre-filled text so the
    WhatsApp webhook can attribute inbound leads to this Google campaign. Point
    the Google ad at `link` and every click becomes an attributed lead.
    """
    slug = slugify_campaign(campaign)
    if not slug:
        raise HTTPException(status_code=400, detail="Campaign name must contain letters or numbers.")

    db = get_supabase()
    number = _primary_whatsapp_number(db, tenant_id)
    if not number:
        raise HTTPException(
            status_code=400,
            detail="No active WhatsApp number found. Activate WhatsApp before generating a link.",
        )

    try:
        link = build_tracked_wa_link(number, slug, gclid=(gclid or None))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"link": link, "campaign_slug": slug, "whatsapp_number": number}


@router.get("/")
async def list_inbound_leads(
    origin: str = Query("all", pattern="^(all|organic|ad)$"),
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    ad_campaign_id: str | None = Query(None),
    source: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: str = Depends(get_tenant_id),
):
    """List inbound leads (organic + ad) with optional origin/segment/channel filters."""
    db = get_supabase()
    offset = (page - 1) * limit
    try:
        leads, total = _fetch_inbound_leads(
            db, tenant_id,
            origin=origin, segment=segment,
            ad_campaign_id=ad_campaign_id, source=source,
            date_from=date_from, date_to=date_to,
            limit=limit, offset=offset,
        )
    except Exception as e:
        logger.error(f"inbound-leads list error: {e}")
        return {"data": [], "total": 0, "page": page, "limit": limit}

    if not leads:
        return {"data": [], "total": total, "page": page, "limit": limit}

    try:
        lead_ids = [l["id"] for l in leads]
        campaign_ids = list({l["ad_campaign_id"] for l in leads if l.get("ad_campaign_id")})
        campaign_map = _fetch_campaign_names(db, tenant_id, campaign_ids)
        keyword_map = _fetch_first_keywords(db, tenant_id, lead_ids)
        enriched = _enrich(leads, campaign_map, keyword_map)
    except Exception as e:
        logger.error(f"inbound-leads enrich error: {e}")
        return {"data": [], "total": total, "page": page, "limit": limit}
    return {"data": enriched, "total": total, "page": page, "limit": limit}


@router.get("/export")
async def export_inbound_leads(
    origin: str = Query("all", pattern="^(all|organic|ad)$"),
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    ad_campaign_id: str | None = Query(None),
    source: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """CSV export for inbound leads. Respects origin/segment/channel/campaign/date filters."""
    db = get_supabase()
    try:
        leads, _ = _fetch_inbound_leads(
            db, tenant_id,
            origin=origin, segment=segment,
            ad_campaign_id=ad_campaign_id, source=source,
            date_from=date_from, date_to=date_to,
            limit=5000, offset=0,
        )
    except Exception as e:
        logger.error(f"inbound-leads export error: {e}")
        leads = []

    FIELDNAMES = [
        "phone", "name", "origin", "channel", "keyword",
        "ad_campaign", "date_joined_ist", "segment", "score",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()

    if leads:
        try:
            lead_ids = [l["id"] for l in leads]
            campaign_ids = list({l["ad_campaign_id"] for l in leads if l.get("ad_campaign_id")})
            campaign_map = _fetch_campaign_names(db, tenant_id, campaign_ids)
            keyword_map = _fetch_first_keywords(db, tenant_id, lead_ids)
            enriched = _enrich(leads, campaign_map, keyword_map)
        except Exception as e:
            logger.error(f"inbound-leads export enrich error: {e}")
            enriched = []
        for lead in enriched:
            writer.writerow({
                "phone": lead["phone"],
                "name": lead["name"],
                "origin": lead["origin"],
                "channel": lead["channel_label"],
                "keyword": lead["keyword"],
                "ad_campaign": lead["campaign_name"],
                "date_joined_ist": _fmt_ist(lead["created_at"]),
                "segment": lead["segment_label"],
                "score": lead["score"],
            })

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inbound_leads.csv"},
    )


@router.get("/ad-filters")
async def ad_filters(tenant_id: str = Depends(get_tenant_id)):
    """Campaign -> adset -> creative option tree for the cascading dropdowns."""
    from app.services.ad_performance import build_ad_filter_tree
    db = get_supabase()
    return build_ad_filter_tree(db, tenant_id)


@router.post("/ad-tracking-code")
async def generate_meta_ad_tracking_code(
    payload: MetaAdTrackingCodeRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Return a stable per-ad fallback code and ready-to-copy pre-filled text."""
    from app.services.meta_ads_insights_sync import get_current_ads_account_id
    from app.services.meta_ctwa_attribution import (
        build_prefilled_message,
        ensure_creative_tracking_code,
    )

    db = get_supabase()
    account_id = get_current_ads_account_id(db, tenant_id)
    if not account_id:
        raise HTTPException(status_code=400, detail="Connect a Meta Ads account first")

    creative = ensure_creative_tracking_code(
        db,
        tenant_id=tenant_id,
        meta_ad_account_id=account_id,
        ad_creative_id=payload.ad_creative_id,
    )
    if not creative:
        raise HTTPException(
            status_code=404,
            detail="Click-to-WhatsApp creative not found in the current ad account",
        )
    if not creative.get("meta_ad_id"):
        raise HTTPException(
            status_code=409,
            detail="This creative does not have a Meta Ad ID yet; sync Meta Ads and try again",
        )

    code = creative["prefilled_message_code"]
    return {
        "code": code,
        "prefilled_message": build_prefilled_message(payload.message, code),
        "ad_creative_id": creative["id"],
        "creative_name": creative.get("creative_label") or creative.get("meta_ad_id"),
        "meta_ad_id": creative.get("meta_ad_id"),
    }


@router.get("/ad-performance")
async def ad_performance(
    campaign_id: str | None = Query(None),
    adset_id: str | None = Query(None),
    ad_creative_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """Per-creative performance rows for the Ad Performance tab."""
    from app.services.ad_performance import build_creative_performance
    db = get_supabase()
    rows = build_creative_performance(
        db, tenant_id,
        campaign_id=campaign_id, adset_id=adset_id, ad_creative_id=ad_creative_id,
        date_from=date_from, date_to=date_to,
    )
    return {"data": rows}


@router.get("/ad-performance/export")
async def ad_performance_export(
    campaign_id: str | None = Query(None),
    adset_id: str | None = Query(None),
    ad_creative_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """CSV of the per-creative performance table, honoring the same filters."""
    from app.services.ad_performance import build_creative_performance
    db = get_supabase()
    rows = build_creative_performance(
        db, tenant_id,
        campaign_id=campaign_id, adset_id=adset_id, ad_creative_id=ad_creative_id,
        date_from=date_from, date_to=date_to,
    )
    fieldnames = [
        "campaign_name", "campaign_status", "adset_name", "creative_label",
        "daily_budget", "lifetime_budget", "budget_level",
        "impressions", "reach", "frequency", "inline_link_clicks", "clicks_all",
        "messages", "meta_conversations", "conversation_rate",
        "meta_conversation_rate", "attribution_gap",
        "clicked_no_message", "no_message_rate", "hot", "hot_rate", "spend", "cpc",
        "cost_per_message", "ctr", "cpm", "cost_per_hot",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    filename = f"ad_performance_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/ad-sync-now")
async def ad_sync_now(tenant_id: str = Depends(get_tenant_id)):
    """Manually trigger the Meta Ads Insights sync for this tenant, returning
    a diagnostic result instead of waiting on the 6h scheduled job."""
    from app.services.meta_ads_insights_sync import sync_tenant_ad_insights_verbose
    db = get_supabase()
    return sync_tenant_ad_insights_verbose(db, tenant_id)
