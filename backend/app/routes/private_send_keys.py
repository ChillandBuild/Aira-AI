"""Client-owned Private Send management: the tenant's own admin creates / revokes the
license key and picks the reply mode. Everything is scoped to the tenant of the
authenticated user (never read from the request). The full key is returned exactly once,
in the create response, and is never logged or audited. Tables: migration 218.
"""
import base64
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ConfigDict

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.routes.auto_messages import _SlidingWindow
from app.services import private_send as svc
from app.services.audit_log import record_audit_event

logger = logging.getLogger(__name__)

router = APIRouter()

require_settings_manage = require_permission("settings.manage")
require_settings_view = require_permission("settings.view")

KEY_CHANGES_PER_MINUTE = 5
SETTINGS_CHANGES_PER_MINUTE = 10
_NO_STORE = {"Cache-Control": "no-store"}

# Per tenant, in-process (slowapi in main.py is per IP only). Create and revoke share one
# budget so create/revoke/create/... can't be used to mint keys faster than 5 a minute.
_key_limiter = _SlidingWindow(KEY_CHANGES_PER_MINUTE, 60)
_settings_limiter = _SlidingWindow(SETTINGS_CHANGES_PER_MINUTE, 60)


class SettingsIn(BaseModel):
    # extra="forbid": a tenant_id (or any other field) in the body is a 422, never used.
    model_config = ConfigDict(extra="forbid")

    reply_mode: Literal["client", "aira"]


def _error(status_code: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": message, "code": code},
        headers={**_NO_STORE, **(headers or {})},
    )


def _rate_limited() -> JSONResponse:
    return _error(429, "rate_limited", "Too many requests. Try again in a minute.", {"Retry-After": "60"})


def _service_error(e: svc.PrivateSendError) -> JSONResponse:
    return _error(e.status_code, e.code, e.message)


def _feature_disabled() -> JSONResponse:
    return _error(403, "feature_disabled", "Private Send is not enabled for this account")


def _audit(db, ctx: dict, action: str, target_id: str, metadata: dict) -> None:
    # Never put a key (or its hash) in here. The full key exists only in the create response.
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx.get("user_id"), actor_role=ctx.get("role"),
        action=action, target_type="private_send", target_id=target_id, metadata=metadata,
    )


def _active_keys(db, tenant_id: str) -> list[dict]:
    return (
        db.table("private_send_keys").select("id, created_at")
        .eq("tenant_id", tenant_id).eq("status", "active").execute()
    ).data or []


def _active_key_count(db, tenant_id: str) -> int:
    return len(_active_keys(db, tenant_id))


def _oldest_first(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r.get("created_at") is None, r.get("created_at") or "", r["id"]))


def _created_at(db, tenant_id: str, key_id: str) -> str | None:
    rows = (
        db.table("private_send_keys").select("created_at")
        .eq("id", key_id).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    return rows[0].get("created_at") if rows else None


def _revoke_unseen_key(db, tenant_id: str, key_id: str) -> None:
    """The full key is only ever returned in the 200 body. If we can't return it, nobody has
    seen it, so it must not stay active (it would block a retry with 409 key_exists)."""
    try:
        svc.revoke_key(db, tenant_id, key_id)
    except Exception as e:
        logger.error("private-send unseen key could not be revoked tenant=%s key=%s err=%s",
                     tenant_id, key_id, type(e).__name__)


@router.post("/keys")
def create_key(ctx: dict = Depends(require_settings_manage)):
    tenant_id = ctx["tenant_id"]
    if not _key_limiter.allow(tenant_id):
        return _rate_limited()
    db = get_supabase()
    created = None
    try:
        if not svc.is_enabled(db, tenant_id):
            return _feature_disabled()
        if _active_key_count(db, tenant_id):
            return _error(409, "key_exists", "A key already exists. Revoke it before creating a new one.")
        created = svc.create_key(db, tenant_id)
        # No unique index limits keys per tenant (the operator may create several), so two
        # simultaneous creates can both pass the check above. Settle it deterministically:
        # the oldest active key survives, any other creator revokes its own key and gets 409.
        # Known theoretical window: until the loser revokes, both keys are active for a moment,
        # and a plug-in that fetched the loser's key in that gap holds a key that then dies.
        # Closing it needs a partial unique index on (tenant_id) WHERE status='active'; the
        # decision on that is with the owner.
        survivor = _oldest_first(_active_keys(db, tenant_id))[0]
        if survivor["id"] != created["id"]:
            svc.revoke_key(db, tenant_id, created["id"])
            return _error(409, "key_exists", "A key already exists. Revoke it before creating a new one.")
        created_at = _created_at(db, tenant_id, created["id"])
    except svc.PrivateSendError as e:
        if created:
            _revoke_unseen_key(db, tenant_id, created["id"])
        return _service_error(e)
    except Exception as e:
        logger.error("private-send key create failed tenant=%s err=%s", tenant_id, type(e).__name__)
        if created:
            _revoke_unseen_key(db, tenant_id, created["id"])
        return _error(500, "key_not_saved", "The key wasn't saved. Try again.")
    _audit(db, ctx, "tenant.private_send_key_created", created["id"], {"prefix": created["key_prefix"]})
    return JSONResponse(
        content={"key": created["key"], "key_prefix": created["key_prefix"], "created_at": created_at},
        headers=_NO_STORE,
    )


@router.delete("/keys/current")
def revoke_current_key(ctx: dict = Depends(require_settings_manage)):
    """Revokes every active key of the tenant (normally one). Allowed even if the feature
    was switched off since: a client must always be able to kill a key."""
    tenant_id = ctx["tenant_id"]
    if not _key_limiter.allow(tenant_id):
        return _rate_limited()
    db = get_supabase()
    try:
        active = _active_keys(db, tenant_id)
        if not active:
            return _error(404, "no_active_key", "There is no active key to revoke")
        for key in active:
            svc.revoke_key(db, tenant_id, key["id"])
    except svc.PrivateSendError as e:
        return _service_error(e)
    except Exception as e:
        logger.error("private-send key revoke failed tenant=%s err=%s", tenant_id, type(e).__name__)
        return _error(500, "key_not_revoked", "Could not revoke the key. Try again.")
    for key in active:
        _audit(db, ctx, "tenant.private_send_key_revoked", key["id"], {})
    return JSONResponse(content={"ok": True, "revoked": len(active)}, headers=_NO_STORE)


@router.patch("/settings")
async def update_settings(body: SettingsIn, ctx: dict = Depends(require_settings_manage)):
    tenant_id = ctx["tenant_id"]
    if not _settings_limiter.allow(tenant_id):
        return _rate_limited()
    db = get_supabase()
    try:
        if not svc.is_enabled(db, tenant_id):
            return _feature_disabled()
        await svc.update_settings(db, tenant_id, {"reply_mode": body.reply_mode})
    except svc.PrivateSendError as e:
        return _service_error(e)
    _audit(db, ctx, "tenant.private_send_settings_updated", tenant_id, {"reply_mode": body.reply_mode})
    return JSONResponse(content={"reply_mode": body.reply_mode}, headers=_NO_STORE)


@router.get("/public-key")
def get_public_keys(ctx: dict = Depends(require_settings_view)):
    """The public half of the key that signs rule bundles, for the client's security review
    and for the plug-in's required anril_public_key. Derived from the signing seed on every
    call; only the public bytes are returned, the seed is never echoed."""
    try:
        public = svc._signing_key().public_key()
    except svc.PrivateSendError:
        return _error(503, "signing_key_missing", "Bundle signing is not configured")
    raw = public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return JSONResponse(
        content={"public_keys": [base64.b64encode(raw).decode("ascii")]}, headers=_NO_STORE,
    )
