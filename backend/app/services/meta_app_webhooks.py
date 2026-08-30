"""Register this Meta app's webhook callback URL + verify token from code.

The callback URL and verify token are **app-level**, not per-tenant: one address and
one token serve every client forever. That is why nothing in the per-client signup
flow can configure them — but Meta exposes them at `POST /{app-id}/subscriptions`,
so there is no reason to paste them into the console by hand either.

Callback URLs registered here are the shared, tenant-agnostic ones
(`/webhook/instagram`, not `/webhook/instagram/{tenant_id}`), because Meta permits a
single callback URL per app per object — a URL naming one tenant can only ever serve
that tenant.
"""
import logging

import httpx

from app.config import settings as env_settings

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"
_RENDER_BASE_URL = "https://aira-ai-5tfr.onrender.com"

# channel -> (Meta webhook object, shared callback path, subscribed fields)
# Fields differ per object: message_deliveries/message_reads are Messenger-only and
# make Meta reject the whole call when sent to the Instagram object.
WEBHOOK_OBJECTS: dict[str, tuple[str, str, str]] = {
    "instagram": (
        "instagram",
        "/webhook/instagram",
        "messages,messaging_postbacks,messaging_seen",
    ),
    "facebook": (
        "page",
        "/webhook/facebook",
        "messages,messaging_postbacks,message_deliveries,message_reads",
    ),
    "whatsapp": (
        "whatsapp_business_account",
        "/webhook/whatsapp",
        "messages",
    ),
}


def resolve_public_base_url() -> str:
    """Host of the single shared deployment. Same order as setup_telegram_webhook."""
    from app.config_dynamic import get_setting

    base_url = (
        get_setting("public_base_url")
        or env_settings.public_base_url
        or _RENDER_BASE_URL
    )
    if base_url == _RENDER_BASE_URL:
        logger.warning(
            "Meta webhook base URL fell back to the hardcoded default — "
            "set PUBLIC_BASE_URL so webhooks register against the correct host."
        )
    return base_url.rstrip("/")


def resolve_verify_token() -> str | None:
    """The token Meta must echo back during the callback-URL handshake.

    Prefers env. Falls back to any tenant's stored copy: the token is app-level, so
    every tenant holds the same value, and this deployment does not always have
    META_VERIFY_TOKEN set even though the tenants do.
    """
    if env_settings.meta_verify_token:
        return env_settings.meta_verify_token
    try:
        from app.db.supabase import get_supabase

        row = (
            get_supabase()
            .table("app_settings")
            .select("value")
            .eq("key", "meta_webhook_verify_token")
            .neq("value", "")
            .limit(1)
            .execute()
        )
        if row.data and row.data[0].get("value"):
            return row.data[0]["value"]
    except Exception as e:
        logger.error(f"resolve_verify_token lookup failed: {e}")
    return None


async def ensure_app_webhook_subscription(channel: str) -> dict:
    """Point Meta at our shared callback URL for one channel. Idempotent.

    Meta calls the callback URL back with `hub.challenge` *during* this request, so
    the server must already be serving the shared route — which is why this runs on
    demand rather than at startup.
    """
    spec = WEBHOOK_OBJECTS.get(channel)
    if not spec:
        return {"ok": False, "detail": f"unknown channel {channel!r}"}
    object_name, path, fields = spec

    if not env_settings.meta_app_id or not env_settings.meta_app_secret:
        return {"ok": False, "detail": "META_APP_ID / META_APP_SECRET are not configured"}

    verify_token = resolve_verify_token()
    if not verify_token:
        return {"ok": False, "detail": "No verify token in env or app_settings"}

    callback_url = f"{resolve_public_base_url()}{path}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{GRAPH}/{env_settings.meta_app_id}/subscriptions",
                params={
                    "object": object_name,
                    "callback_url": callback_url,
                    "verify_token": verify_token,
                    "fields": fields,
                    "access_token": f"{env_settings.meta_app_id}|{env_settings.meta_app_secret}",
                },
                timeout=15.0,
            )
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"App webhook subscription for {object_name} failed: {e}")
        return {"ok": False, "object": object_name, "callback_url": callback_url, "detail": str(e)}

    if isinstance(body, dict) and body.get("success"):
        logger.info(f"App webhook subscription live: {object_name} -> {callback_url}")
        return {"ok": True, "object": object_name, "callback_url": callback_url}

    error = (body or {}).get("error", {}) if isinstance(body, dict) else {}
    detail = error.get("message", "Meta did not confirm the subscription")
    logger.warning(f"App webhook subscription for {object_name} rejected: {detail}")
    return {"ok": False, "object": object_name, "callback_url": callback_url, "detail": detail}


async def sync_all_app_webhook_subscriptions() -> dict[str, dict]:
    """Register every channel's callback URL. Safe to re-run at any time."""
    return {channel: await ensure_app_webhook_subscription(channel) for channel in WEBHOOK_OBJECTS}
