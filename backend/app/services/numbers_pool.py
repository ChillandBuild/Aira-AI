import re

from app.services.entitlements import get_purchased_quantity, resolve_entitlements


def normalize_phone_number(raw: str) -> str:
    """Strip everything except digits and a leading '+', so Meta-formatted
    numbers ("+91 98765-43210") match our stored format ("+919876543210")."""
    raw = (raw or "").strip()
    plus = "+" if raw.startswith("+") else ""
    digits = re.sub(r"\D", "", raw)
    return f"{plus}{digits}"


def compute_unlocked_ids(rows: list[dict], limit: int) -> set[str]:
    """
    Pure lock-slot algorithm, given a tenant's non-archived phone_numbers rows
    (each needs at least "id", "role", "created_at") and their numbers_pool
    limit.

    - role="primary" always wins a slot, regardless of age.
    - Remaining (limit - 1) slots go to non-primary rows, oldest `created_at`
      first.
    - If no primary exists yet, nothing is unlocked -- oldest-first only ever
      fills slots *in addition to* a guaranteed primary slot, it never
      operates without one. This matters for a brand-new tenant's first Meta
      sync: several numbers can land at once with no primary chosen yet, and
      none of them should be auto-activated by arbitrary sync-batch order --
      the client must explicitly choose one.
    """
    if limit <= 0:
        return set()

    primary = next((r for r in rows if r.get("role") == "primary"), None)
    if primary is None:
        return set()

    unlocked = {primary["id"]}
    others = sorted(
        (r for r in rows if r.get("id") != primary.get("id")),
        key=lambda r: r.get("created_at") or "",
    )
    for r in others[: max(limit - 1, 0)]:
        unlocked.add(r["id"])
    return unlocked


def numbers_pool_limit(db, tenant_id: str) -> int:
    """
    Purchasing Inbound or Outbound (WhatsApp) messaging includes 1 free
    phone number -- that's the messaging module's whole point, not an
    add-on. Anything beyond that free number is an explicit paid top-up via
    `tenant_subscription_items` (feature_key='numbers_pool'). A tenant with
    no messaging module purchased at all gets 0.
    """
    ent = resolve_entitlements(db, tenant_id)
    features = set(ent.get("features") or [])
    baseline = 1 if ("inbound_messaging" in features or "outbound_messaging" in features) else 0
    return baseline + get_purchased_quantity(db, tenant_id, "numbers_pool")


def get_unlocked_number_ids(db, tenant_id: str) -> set[str]:
    """DB-backed wrapper around compute_unlocked_ids -- fetches the tenant's
    non-archived phone_numbers and current numbers_pool limit, and returns the
    set of ids allowed to be active/primary/unpaused right now."""
    limit = numbers_pool_limit(db, tenant_id)
    rows = (
        db.table("phone_numbers")
        .select("id,role,created_at")
        .eq("tenant_id", tenant_id)
        .neq("status", "archived")
        .execute()
        .data
        or []
    )
    return compute_unlocked_ids(rows, limit)
