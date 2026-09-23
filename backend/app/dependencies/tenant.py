import logging
import time
from fastapi import Depends, HTTPException, status

from app.db.supabase import get_supabase
from app.dependencies.auth import get_current_user
from app.utils.db_retry import execute_with_retry

logger = logging.getLogger(__name__)

_TENANT_ROLE_CACHE: dict[str, tuple[float, dict]] = {}
_TENANT_CACHE_TTL_SECONDS = 60
_MAX_CACHE_SIZE = 1000


def invalidate_tenant_cache(user_id: str | None = None) -> None:
    """Invalidate tenant/role cache for a specific user, or all if user_id is None."""
    if user_id:
        _TENANT_ROLE_CACHE.pop(user_id, None)
    else:
        _TENANT_ROLE_CACHE.clear()


def _get_cached_tenant_and_role(user_id: str) -> dict | None:
    cached = _TENANT_ROLE_CACHE.get(user_id)
    if not cached:
        return None
    expires_at, data = cached
    if time.time() >= expires_at:
        _TENANT_ROLE_CACHE.pop(user_id, None)
        return None
    return dict(data)


def _set_cached_tenant_and_role(user_id: str, data: dict) -> None:
    if len(_TENANT_ROLE_CACHE) >= _MAX_CACHE_SIZE:
        now = time.time()
        expired = [uid for uid, (exp, _) in _TENANT_ROLE_CACHE.items() if exp <= now]
        for uid in expired:
            _TENANT_ROLE_CACHE.pop(uid, None)
        if len(_TENANT_ROLE_CACHE) >= _MAX_CACHE_SIZE:
            to_drop = list(_TENANT_ROLE_CACHE.keys())[: _MAX_CACHE_SIZE // 5]
            for uid in to_drop:
                _TENANT_ROLE_CACHE.pop(uid, None)
    _TENANT_ROLE_CACHE[user_id] = (time.time() + _TENANT_CACHE_TTL_SECONDS, dict(data))


def get_tenant_id(user: dict = Depends(get_current_user)) -> str:
    user_id = user["user_id"]
    cached = _get_cached_tenant_and_role(user_id)
    if cached and cached.get("tenant_id"):
        return cached["tenant_id"]
    ctx = get_tenant_and_role(user)
    return ctx["tenant_id"]


def get_tenant_and_role(user: dict = Depends(get_current_user)) -> dict:
    user_id = user["user_id"]
    cached = _get_cached_tenant_and_role(user_id)
    if cached is not None:
        return cached

    from app.services.assignment import get_caller_id_for_user
    from app.services.rbac import resolve_permissions
    db = get_supabase()
    result = execute_with_retry(
        db.table("tenant_users")
        .select("tenant_id, role")
        .eq("user_id", user_id)
        .maybe_single()
    )
    if not result or not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this account.",
        )
    tenant_id = result.data["tenant_id"]
    role = result.data["role"]
    tenant = execute_with_retry(
        db.table("tenants")
        .select("status")
        .eq("id", tenant_id)
        .maybe_single()
    )
    if (tenant.data if tenant else {}).get("status") == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended.")
    # Resolve a caller profile for ANY user that has one (owners can also be telecallers).
    # Role still governs visibility/permissions; caller_id only enables telecalling actions.
    caller_id = get_caller_id_for_user(user_id, tenant_id)
    access = resolve_permissions(db, tenant_id, user_id, role)
    ctx = {
        "tenant_id": tenant_id,
        "role": role,
        "user_id": user_id,
        "caller_id": caller_id,
        **access,
    }
    _set_cached_tenant_and_role(user_id, ctx)
    return ctx


def require_owner(ctx: dict = Depends(get_tenant_and_role)) -> dict:
    if ctx.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization owner privileges required."
        )
    return ctx


def get_owner_tenant_id(ctx: dict = Depends(require_owner)) -> str:
    """Owner-only tenant id. Use for admin-only read endpoints so a caller
    cannot reach them via a direct API call (the UI already hides them)."""
    return ctx["tenant_id"]


def require_permission(permission: str):
    def _dependency(ctx: dict = Depends(get_tenant_and_role)) -> dict:
        permissions = set(ctx.get("permissions") or [])
        manage_permission = f"{permission[:-5]}.manage" if permission.endswith(".view") else None
        reply_implies_view = permission == "conversations.view" and "conversations.reply" in permissions
        if ctx.get("role") == "owner" or permission in permissions or manage_permission in permissions or reply_implies_view:
            return ctx
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission}",
        )
    return _dependency

