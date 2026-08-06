import re


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
