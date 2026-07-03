import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_USAGE_METRICS = (
    "message_sent", "ai_reply", "call_minute", "team_seat_active",
    "storage_gb", "ai_call_summary", "ai_call_scoring", "phone_number",
)


def _price_for_item(catalog_row: dict, quantity: int) -> float:
    unit_price = catalog_row.get("unit_price")
    if unit_price is not None:
        return float(unit_price) * quantity
    return float(catalog_row.get("monthly_price") or 0) * quantity


def submit_request(db, tenant_id: str, requested_items: list[dict], package_id: str | None = None) -> dict:
    """
    Create a subscription_requests row for a cart submission (first-time
    onboarding or a later top-up ask) and flip the tenant into
    pending_approval. `requested_items` is [{"feature_key": str, "quantity": int}].
    """
    feature_keys = [i["feature_key"] for i in requested_items]
    catalog_res = db.table("feature_catalog").select("feature_key, monthly_price, unit_price").in_("feature_key", feature_keys).execute()
    catalog_by_key = {row["feature_key"]: row for row in (catalog_res.data or [])}

    total_amount = 0.0
    priced_items = []
    for item in requested_items:
        catalog_row = catalog_by_key.get(item["feature_key"], {})
        quantity = item.get("quantity") or 1
        price = _price_for_item(catalog_row, quantity)
        total_amount += price
        priced_items.append({**item, "quantity": quantity, "line_total": price})

    existing = db.table("tenant_subscriptions").select("status").eq("tenant_id", tenant_id).maybe_single().execute()
    is_initial = not existing.data or existing.data.get("status") != "active"

    inserted = db.table("subscription_requests").insert({
        "tenant_id": tenant_id,
        "status": "submitted",
        "requested_items": priced_items,
        "package_id": package_id,
        "total_amount": total_amount,
        "is_initial": is_initial,
    }).execute()

    db.table("tenant_subscriptions").upsert({
        "tenant_id": tenant_id,
        "status": "pending_approval",
    }, on_conflict="tenant_id").execute()

    request_row = inserted.data[0] if inserted.data else {}
    return {**request_row, "total_amount": total_amount}


def approve_request(db, request_id: str, reviewer_user_id: str) -> dict:
    """
    Approve a pending request: upsert tenant_subscription_items (incrementing
    quantity on an existing feature_key row rather than duplicating),
    recompute entitlements/usage/mrr, and activate the subscription.
    """
    from app.services.entitlements import resolve_entitlements

    req = db.table("subscription_requests").select(
        "id, tenant_id, requested_items, package_id, total_amount"
    ).eq("id", request_id).maybe_single().execute()
    if not req.data:
        raise ValueError(f"subscription_request {request_id} not found")

    tenant_id = req.data["tenant_id"]
    package_id = req.data.get("package_id")

    for item in (req.data.get("requested_items") or []):
        feature_key = item["feature_key"]
        quantity = item.get("quantity") or 1
        unit_price = item.get("unit_price") or item.get("line_total", 0) / max(quantity, 1)

        existing = db.table("tenant_subscription_items").select("quantity").eq(
            "tenant_id", tenant_id
        ).eq("feature_key", feature_key).maybe_single().execute()
        new_quantity = quantity + ((existing.data or {}).get("quantity") or 0)

        db.table("tenant_subscription_items").upsert({
            "tenant_id": tenant_id,
            "feature_key": feature_key,
            "quantity": new_quantity,
            "unit_price_snapshot": unit_price,
            "package_id": package_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="tenant_id,feature_key").execute()

    ent = resolve_entitlements(db, tenant_id)
    db.table("tenants").update({"enabled_features": ent["features"]}).eq("id", tenant_id).execute()

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    for metric in _USAGE_METRICS:
        included = ent["quotas"].get(metric, 0)
        db.table("tenant_usage_counters").upsert({
            "tenant_id": tenant_id,
            "period": period,
            "metric": metric,
            "included": included,
        }, on_conflict="tenant_id,period,metric").execute()

    all_items = db.table("tenant_subscription_items").select("quantity, unit_price_snapshot").eq("tenant_id", tenant_id).execute()
    mrr = sum((r.get("quantity") or 0) * (r.get("unit_price_snapshot") or 0) for r in (all_items.data or []))

    db.table("tenant_subscriptions").update({
        "status": "active",
        "mrr": mrr,
    }).eq("tenant_id", tenant_id).execute()

    updated = db.table("subscription_requests").update({
        "status": "approved",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer_user_id,
    }).eq("id", request_id).execute()

    return updated.data[0] if updated.data else {"id": request_id, "status": "approved"}


def reject_request(db, request_id: str, reviewer_user_id: str, reason: str) -> dict:
    """Reject a pending request. Does not touch tenant_subscription_items."""
    updated = db.table("subscription_requests").update({
        "status": "rejected",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer_user_id,
        "rejection_reason": reason,
    }).eq("id", request_id).execute()

    return updated.data[0] if updated.data else {"id": request_id, "status": "rejected"}
