import logging
from supabase import Client
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def resolve_entitlements(db: Client, tenant_id: str) -> dict:
    """
    Build a tenant's entitlements from their purchased line items
    (`tenant_subscription_items`), not a single assigned plan.

    Each purchased item enables itself plus everything in its catalog
    row's `depends_on` list. Metered items contribute
    `included_qty * quantity` to the returned quotas, keyed by the
    catalog row's `usage_metric`.

    Returns {'features': list, 'quotas': dict}
    """
    items_res = db.table("tenant_subscription_items").select("feature_key, quantity").eq("tenant_id", tenant_id).execute()
    items = items_res.data or []
    if not items:
        return {"features": [], "quotas": {}}

    catalog_res = db.table("feature_catalog").select("feature_key, depends_on, usage_metric, included_qty").execute()
    catalog_by_key = {row["feature_key"]: row for row in (catalog_res.data or [])}

    features: set[str] = set()
    quotas: dict[str, int] = {}

    for item in items:
        feature_key = item["feature_key"]
        quantity = item.get("quantity") or 1
        features.add(feature_key)

        catalog_row = catalog_by_key.get(feature_key)
        if not catalog_row:
            continue

        for dep in (catalog_row.get("depends_on") or []):
            features.add(dep)

        metric = catalog_row.get("usage_metric")
        if metric:
            included_qty = catalog_row.get("included_qty") or 0
            quotas[metric] = quotas.get(metric, 0) + (included_qty * quantity)

    return {"features": sorted(features), "quotas": quotas}


def check_feature_enabled(
    db: Client,
    tenant_id: str,
    feature_key: str,
) -> bool:
    """Check if a feature is enabled for a tenant via purchased items."""
    ent = resolve_entitlements(db, tenant_id)
    return feature_key in ent["features"]


def get_purchased_quantity(db: Client, tenant_id: str, feature_key: str) -> int:
    """Total quantity purchased for a feature_key. 0 if never purchased."""
    rows = (
        db.table("tenant_subscription_items")
        .select("quantity")
        .eq("tenant_id", tenant_id)
        .eq("feature_key", feature_key)
        .execute()
    )
    return sum((r.get("quantity") or 0) for r in (rows.data or []))


def check_quota(
    db: Client,
    tenant_id: str,
    metric: str,
    delta: int = 1,
) -> bool:
    """
    Hard-cap check: True if this delta stays within the tenant's included
    quota for `metric` this period, False otherwise. Pure read — does NOT
    mutate `tenant_usage_counters`. Callers must call `increment_usage()`
    (or `meter()`) themselves after the guarded action succeeds.

    included == 0 (no counter row, or a row with included=0) means the
    tenant has not purchased this metric at all — blocked, not unlimited.
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")

    period_res = db.table("tenant_usage_counters").select(
        "used, included, hard_cap"
    ).eq("tenant_id", tenant_id).eq("period", period).eq("metric", metric).maybe_single().execute()

    row = period_res.data or {}
    used = row.get("used") or 0
    included = row.get("included") or 0

    return (used + delta) <= included


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
    Pair with `check_quota()` (called BEFORE the action) for hard enforcement.
    """
    if not tenant_id or delta <= 0:
        return
    try:
        increment_usage(db, tenant_id, metric, delta)
    except Exception as e:
        logger.warning(f"metering failed (tenant={tenant_id}, metric={metric}): {e}")
