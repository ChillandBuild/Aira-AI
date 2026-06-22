import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_TTL = 60.0
# Bootstrapping default for get_setting/save_setting when called without an explicit
# tenant_id (the two genuinely-global reads: public_base_url + webhook verify fallback).
# This is NOT a privileged tenant — all credentials resolve per-tenant from app_settings.
_DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def get_setting(key: str, fallback: Optional[str] = None, tenant_id: Optional[str] = None) -> Optional[str]:
    """Read from cache → app_settings table → fallback. No env-var fallback: every
    tenant (including the first) configures its own credentials in app_settings."""
    now = time.monotonic()
    resolved_tenant_id = tenant_id or _DEFAULT_TENANT_ID
    cache_key = f"{resolved_tenant_id}:{key}"
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    value: Optional[str] = None
    try:
        from app.db.supabase import get_supabase
        db = get_supabase()
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", resolved_tenant_id)
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        if row and row.data:
            value = row.data.get("value")
    except Exception as e:
        logger.warning(f"get_setting({key}, tenant_id={resolved_tenant_id}) DB read failed: {e}")

    if not value:
        value = fallback

    _CACHE[cache_key] = (now, value)
    return value


def save_setting(key: str, value: str, tenant_id: Optional[str] = None) -> None:
    """Upsert a key/value into app_settings and invalidate the local cache."""
    resolved_tenant_id = tenant_id or _DEFAULT_TENANT_ID
    try:
        from app.db.supabase import get_supabase
        db = get_supabase()
        db.table("app_settings").upsert(
            {"key": key, "value": value, "tenant_id": resolved_tenant_id, "is_secret": False},
            on_conflict="key,tenant_id",
        ).execute()
    except Exception as e:
        logger.warning(f"save_setting({key}, tenant_id={resolved_tenant_id}) DB write failed: {e}")
        return
    cache_key = f"{resolved_tenant_id}:{key}"
    _CACHE[cache_key] = (time.monotonic(), value)


def invalidate_cache(key: Optional[str] = None) -> None:
    if key:
        keys_to_remove = [cache_key for cache_key in _CACHE if cache_key.endswith(f":{key}")]
        for cache_key in keys_to_remove:
            _CACHE.pop(cache_key, None)
    else:
        _CACHE.clear()
