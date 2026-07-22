"""Pull Meta Ads Insights (level=ad) per tenant, auto-import creatives, and
store daily clicks/spend. Credentials come from app_settings
(meta_ads_access_token / meta_ads_account_id, plaintext). Read-only against
Meta (ads_read). Service-role DB writes bypass RLS.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.db.supabase import get_supabase
from app.services.growth import get_or_create_campaign

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_INSIGHT_FIELDS = (
    "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,"
    "inline_link_clicks,clicks,spend"
)


def normalize_account_id(raw: str) -> str:
    """Return the ad account id in act_<digits> form."""
    v = (raw or "").strip()
    return v if v.startswith("act_") else f"act_{v}"


def _get_ads_credentials(db, tenant_id: str) -> tuple[str, str] | None:
    """(access_token, act_account_id) from app_settings, or None if unset."""
    rows = (
        db.table("app_settings").select("key,value")
        .eq("tenant_id", tenant_id)
        .in_("key", ["meta_ads_access_token", "meta_ads_account_id"])
        .execute()
    )
    kv = {r["key"]: r["value"] for r in (rows.data or []) if r.get("value")}
    token = kv.get("meta_ads_access_token")
    account = kv.get("meta_ads_account_id")
    if not token or not account:
        return None
    return token, normalize_account_id(account)


def upsert_creative_from_insight(db, tenant_id: str, row: dict) -> str | None:
    """Insert-or-reuse an ad_creatives row keyed by (tenant_id, meta_ad_id).
    Links to an ad_campaigns row via get_or_create_campaign. Never overwrites a
    tenant-edited creative_label (label_edited=True). Returns ad_creatives.id.
    """
    ad_id = (row.get("ad_id") or "").strip()
    if not ad_id:
        return None

    campaign = get_or_create_campaign(
        db=db,
        tenant_id=tenant_id,
        platform="whatsapp",
        campaign_name=row.get("campaign_name"),
        external_campaign_id=row.get("campaign_id"),
    )
    campaign_id = campaign["id"] if campaign else None

    existing = (
        db.table("ad_creatives").select("id,label_edited")
        .eq("tenant_id", tenant_id).eq("meta_ad_id", ad_id)
        .limit(1).execute()
    )
    found = (existing.data or [None])[0]
    now_iso = datetime.now(timezone.utc).isoformat()

    if found:
        updates = {
            "meta_adset_id": row.get("adset_id"),
            "meta_adset_name": row.get("adset_name"),
            "meta_campaign_id": row.get("campaign_id"),
            "campaign_id": campaign_id,
            "updated_at": now_iso,
        }
        if not found.get("label_edited"):
            updates["creative_label"] = (row.get("ad_name") or ad_id)
        db.table("ad_creatives").update(updates).eq("id", found["id"]).eq(
            "tenant_id", tenant_id
        ).execute()
        return found["id"]

    inserted = db.table("ad_creatives").insert({
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
        "meta_ad_id": ad_id,
        "meta_adset_id": row.get("adset_id"),
        "meta_adset_name": row.get("adset_name"),
        "meta_campaign_id": row.get("campaign_id"),
        "creative_label": (row.get("ad_name") or ad_id),
        "created_at": now_iso,
        "updated_at": now_iso,
    }).execute()
    return (inserted.data or [{}])[0].get("id")


def _fetch_insights(token: str, account: str, date_preset: str) -> list[dict]:
    """One page is enough for typical accounts; follow paging.next if present."""
    url = f"{_GRAPH_BASE}/{account}/insights"
    params = {
        "level": "ad",
        "fields": _INSIGHT_FIELDS,
        "date_preset": date_preset,
        "time_increment": "1",   # one row per ad PER DAY
        "limit": "200",
        "access_token": token,
    }
    out: list[dict] = []
    with httpx.Client(timeout=30) as client:
        next_url, next_params = url, params
        for _ in range(20):  # hard cap on pages
            resp = client.get(next_url, params=next_params)
            resp.raise_for_status()
            body = resp.json()
            out.extend(body.get("data", []))
            nxt = (body.get("paging") or {}).get("next")
            if not nxt:
                break
            next_url, next_params = nxt, None  # next already carries all params
    return out


def sync_tenant_ad_insights(db, tenant_id: str, *, date_preset: str = "last_30d") -> int:
    """Pull level=ad daily insights, upsert creatives, write ad_insights_daily.
    Returns number of daily rows written. Best-effort per row.
    """
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return 0
    token, account = creds
    try:
        rows = _fetch_insights(token, account, date_preset)
    except Exception as e:
        logger.warning(f"Ads insights fetch failed for tenant {tenant_id}: {e}")
        return 0

    written = 0
    for row in rows:
        creative_id = upsert_creative_from_insight(db, tenant_id, row)
        if not creative_id:
            continue
        insight_date = row.get("date_start")  # present when time_increment=1
        if not insight_date:
            continue
        try:
            db.table("ad_insights_daily").upsert({
                "tenant_id": tenant_id,
                "ad_creative_id": creative_id,
                "insight_date": insight_date,
                "clicks": int(float(row.get("clicks", 0) or 0)),
                "inline_link_clicks": int(float(row.get("inline_link_clicks", 0) or 0)),
                "spend": float(row.get("spend", 0) or 0),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="tenant_id,ad_creative_id,insight_date").execute()
            written += 1
        except Exception as e:
            logger.warning(f"insight row write failed (tenant {tenant_id}): {e}")
    logger.info(f"Ads insights sync: tenant {tenant_id} wrote {written} daily rows")
    return written


def sync_all_tenants_ad_insights() -> None:
    """Scheduler entrypoint: sync every tenant that has ads credentials set."""
    db = get_supabase()
    try:
        rows = (
            db.table("app_settings").select("tenant_id")
            .eq("key", "meta_ads_account_id").execute()
        )
        tenant_ids = sorted({r["tenant_id"] for r in (rows.data or []) if r.get("tenant_id")})
    except Exception as e:
        logger.error(f"Ads insights sync: tenant enumeration failed: {e}")
        return
    for tid in tenant_ids:
        try:
            sync_tenant_ad_insights(db, tid)
        except Exception as e:
            logger.warning(f"Ads insights sync failed for tenant {tid}: {e}")
