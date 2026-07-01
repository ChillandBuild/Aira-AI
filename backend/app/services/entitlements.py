import logging
from supabase import Client
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def resolve_entitlements(
    db: Client,
    tenant_id: str,
    period: str | None = None,
) -> dict:
    """
    Merge plan.included + custom_overrides to produce enabled_features and quotas.
    Returns {'features': list, 'quotas': dict, 'ai_tier': str}
    """
    if period is None:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
    
    tenant = db.table("tenants").select("id, enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        return {"features": [], "quotas": {}, "ai_tier": "off"}
    
    sub_res = db.table("tenant_subscriptions").select(
        "messaging_plan_id, telecalling_plan_id, ai_tier, custom_overrides"
    ).eq("tenant_id", tenant_id).maybe_single().execute()
    
    sub = sub_res.data or {}
    custom_overrides = sub.get("custom_overrides", {}) or {}
    
    features: list[str] = []
    quotas: dict = {}
    
    for plan_id_key in ["messaging_plan_id", "telecalling_plan_id"]:
        plan_id = sub.get(plan_id_key)
        if plan_id:
            plan_res = db.table("plans").select("included").eq("id", plan_id).maybe_single().execute()
            if plan_res.data:
                included = plan_res.data.get("included", {}) or {}
                features.extend(included.get("feature_keys", []))
                quotas.update(included.get("quotas", {}))
    
    features.extend(custom_overrides.get("feature_keys", []))
    quotas.update(custom_overrides.get("quotas", {}))
    
    features = list(dict.fromkeys(features))
    
    return {
        "features": features,
        "quotas": quotas,
        "ai_tier": sub.get("ai_tier", "off"),
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