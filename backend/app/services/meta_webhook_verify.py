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
    app_secret = get_setting(secret_key, tenant_id=tenant_id)
    if not app_secret and secret_key != "meta_app_secret":
        app_secret = get_setting("meta_app_secret", tenant_id=tenant_id)
    if not app_secret:
        logger.warning(f"{secret_key} not configured for tenant {tenant_id} — rejecting webhook")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    received = signature_header.split("=", 1)[1]
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


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
