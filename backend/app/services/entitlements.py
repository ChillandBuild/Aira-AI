import logging
from supabase import Client
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def resolve_entitlements(db: Client, tenant_id: str) -> dict:
    """
    Look up the tenant's single assigned plan and return its entitlements.
    Returns {'features': list, 'quotas': dict}
    """
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        return {"features": [], "quotas": {}}

    sub_res = db.table("tenant_subscriptions").select("plan_id").eq("tenant_id", tenant_id).maybe_single().execute()
    plan_id = (sub_res.data or {}).get("plan_id")
    if not plan_id:
        return {"features": [], "quotas": {}}

    plan_res = db.table("plans").select("feature_keys, quotas").eq("id", plan_id).maybe_single().execute()
    if not plan_res.data:
        return {"features": [], "quotas": {}}

    return {
        "features": list(plan_res.data.get("feature_keys") or []),
        "quotas": dict(plan_res.data.get("quotas") or {}),
    }


def check_feature_enabled(
    db: Client,
    tenant_id: str,
    feature_key: str,
) -> bool:
    """Check if a feature is enabled for a tenant via plan + overrides."""
    ent = resolve_entitlements(db, tenant_id)
    return feature_key in ent["features"]


def check_quota(
    db: Client,
    tenant_id: str,
    metric: str,
    delta: int = 1,
) -> bool:
    """
    Check if tenant has quota remaining for a metered metric.
    Returns True if within soft cap (80% warn), False if at/above hard cap.
    Increments the counter if within limits.
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    
    period_res = db.table("tenant_usage_counters").select(
        "used, included, hard_cap"
    ).eq("tenant_id", tenant_id).eq("period", period).eq("metric", metric).maybe_single().execute()
    
    row = period_res.data or {}
    used = (row.get("used") or 0) + delta
    included = row.get("included") or 0
    hard_cap = row.get("hard_cap")
    
    if hard_cap is not None and used > hard_cap:
        return False
    
    db.table("tenant_usage_counters").upsert({
        "tenant_id": tenant_id,
        "period": period,
        "metric": metric,
        "used": used,
        "included": included,
        "hard_cap": hard_cap,
    }, on_conflict="tenant_id,period,metric").execute()
    
    return used <= included or included == 0


def increment_usage(
    db: Client,
    tenant_id: str,
    metric: str,
    delta: int = 1,
) -> dict:
    """
    Increment a metered counter and return status.
    Returns {'used': int, 'included': int, 'over_cap': bool, 'warning': bool}
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    
    counter_res = db.table("tenant_usage_counters").select("used, included, hard_cap").eq(
        "tenant_id", tenant_id
    ).eq("period", period).eq("metric", metric).maybe_single().execute()
    
    current = counter_res.data or {"used": 0, "included": 0, "hard_cap": None}
    used = (current.get("used") or 0) + delta
    included = current.get("included") or 0
    hard_cap = current.get("hard_cap")
    
    over_cap = False
    warning = False
    
    if hard_cap is not None:
        over_cap = used > hard_cap
    if included > 0:
        warning = used >= included * 0.8 and used < included
    
    db.table("tenant_usage_counters").upsert({
        "tenant_id": tenant_id,
        "period": period,
        "metric": metric,
        "used": used,
        "included": included,
        "hard_cap": hard_cap,
    }, on_conflict="tenant_id,period,metric").execute()
    
    return {
        "used": used,
        "included": included,
        "over_cap": over_cap,
        "warning": warning,
    }


def meter(db, tenant_id: str, metric: str, delta: int = 1) -> None:
    """Best-effort, non-blocking usage metering. Never raises.

    TRACK-ONLY: this must never block, cap, delay, or break a send/reply/call.
    Callers must not branch on this function's return value for gating.
    """
    if not tenant_id or delta <= 0:
        return
    try:
        increment_usage(db, tenant_id, metric, delta)
    except Exception as e:
        logger.warning(f"metering failed (tenant={tenant_id}, metric={metric}): {e}")