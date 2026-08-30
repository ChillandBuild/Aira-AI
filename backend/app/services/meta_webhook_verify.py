"""Shared helpers for Meta webhook verification (FB Messenger + Instagram)."""
import hmac
import hashlib
import logging
from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)


def verify_meta_signature(
    raw_body: bytes,
    signature_header: str | None,
    tenant_id: str,
    secret_key: str = "meta_app_secret",
) -> bool:
    """Verify Meta's X-Hub-Signature-256 header against raw request body.

    Returns True on valid signature. If no app secret is configured, returns False
    (fail-closed) so misconfiguration cannot accept unverified traffic.

    secret_key selects which app_settings secret signs this channel. Instagram-Login
    webhooks are signed with a separate Instagram App Secret; pass
    secret_key="instagram_app_secret". When that key is unset we fall back to the
    shared meta_app_secret so Facebook-Login Instagram (same secret as WhatsApp)
    keeps working.
    """
    used_key = secret_key
    app_secret = get_setting(secret_key, tenant_id=tenant_id)
    if not app_secret and secret_key != "meta_app_secret":
        app_secret = get_setting("meta_app_secret", tenant_id=tenant_id)
        used_key = "meta_app_secret"
    if not app_secret:
        logger.warning(f"{secret_key} not configured for tenant {tenant_id} — rejecting webhook")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning(
            f"Meta webhook for tenant {tenant_id} has no X-Hub-Signature-256 header — rejecting"
        )
        return False

    received = signature_header.split("=", 1)[1]
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if hmac.compare_digest(received, expected):
        return True

    # A bare "signature invalid" is a dead end: the overwhelmingly common cause is
    # that the channel was configured in a *different* Meta app, and nothing in the
    # rejection said so. Name the secret we used and fingerprint it (never log the
    # secret itself) so this is diagnosable against the Meta console in one step.
    logger.warning(
        f"Meta webhook signature mismatch for tenant {tenant_id}: verified against "
        f"{used_key} (md5 {secret_fingerprint(app_secret)}). Meta signs each payload with "
        f"the App Secret of the app that owns the webhook subscription — if this channel is "
        f"configured in a different Meta app, that app's App Secret is what signs it. Compare "
        f"the fingerprint above with Meta → App settings → Basic → App Secret."
    )
    return False


def resolve_tenant_for_page(page_id: str, channel: str) -> str | None:
    """Look up the tenant that owns this page_id for the given channel.

    channel: "facebook" or "instagram".
    Returns tenant_id or None if no tenant has this page configured.
    """
    if not page_id:
        return None
    key = "facebook_page_id" if channel == "facebook" else "instagram_page_id"
    try:
        from app.db.supabase import get_supabase
        db = get_supabase()
        row = (
            db.table("app_settings")
            .select("tenant_id")
            .eq("key", key)
            .eq("value", page_id)
            .limit(1)
            .execute()
        )
        if row.data:
            return row.data[0]["tenant_id"]
    except Exception as e:
        logger.error(f"resolve_tenant_for_page({channel}, {page_id}) failed: {e}")
    return None


def secret_fingerprint(secret: str) -> str:
    """Short, non-reversible fingerprint of a secret, safe to log.

    Lets an operator compare what the backend holds against what the Meta console
    shows without either value being written to a log or pasted into a chat.
    """
    return hashlib.md5(secret.encode("utf-8")).hexdigest()[:8]


def resolve_tenants_from_payload(payload: dict, channel: str) -> list[str]:
    """Distinct tenants owning the entries in a Meta webhook payload, in order.

    This is what lets one callback URL serve every tenant. Meta allows a single
    callback URL per app per webhook object, so a URL carrying `tenant_id` in its
    path can only ever serve one tenant; the account id in `entry[].id` identifies
    the owner just as well, which is how /webhook/whatsapp has always worked.
    """
    tenants: list[str] = []
    for entry in payload.get("entry", []) or []:
        tenant_id = resolve_tenant_for_page(entry.get("id", ""), channel)
        if tenant_id and tenant_id not in tenants:
            tenants.append(tenant_id)
    return tenants


def matches_any_tenant_verify_token(token: str | None) -> bool:
    """True when `token` matches any tenant's verify token, or the env fallback.

    Mirrors the WhatsApp webhook's shared-endpoint check. The verify token is
    app-level (every tenant holds the same copy), so a shared endpoint cannot scope
    the challenge to one tenant. This proves nothing about *which app* is calling —
    only the signed POST does that.
    """
    if not token:
        return False
    try:
        from app.db.supabase import get_supabase
        db = get_supabase()
        rows = (
            db.table("app_settings")
            .select("value")
            .eq("key", "meta_webhook_verify_token")
            .execute()
        )
        for row in (rows.data or []):
            stored = row.get("value")
            if stored and hmac.compare_digest(stored, token):
                return True
    except Exception as e:
        logger.error(f"matches_any_tenant_verify_token lookup failed: {e}")

    from app.config import settings as env_settings
    env_token = getattr(env_settings, "meta_verify_token", None)
    return bool(env_token and hmac.compare_digest(env_token, token))
