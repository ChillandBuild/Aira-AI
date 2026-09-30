"""Permission checks for Aira Brain rows. Services take the caller's role and permission
list as plain values (never a request object) so the operator route can reuse them."""
from collections.abc import Iterable

OWNER_ROLE = "owner"


def has_permission(role: str | None, permissions: Iterable[str] | None, key: str) -> bool:
    """Mirrors dependencies.tenant.require_permission: the owner passes, a ".view" key is
    also satisfied by its ".manage" sibling."""
    if role == OWNER_ROLE:
        return True
    held = set(permissions or [])
    if key in held:
        return True
    return key.endswith(".view") and f"{key[:-5]}.manage" in held
