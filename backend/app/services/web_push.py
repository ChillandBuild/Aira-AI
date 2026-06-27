import json
import logging
from typing import Any

from app.config import settings
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def vapid_public_key() -> str | None:
    return settings.vapid_public_key


def _webpush():
    try:
        from pywebpush import WebPushException, webpush
    except Exception:
        return None, None
    return webpush, WebPushException


def send_user_push(
    tenant_id: str,
    user_id: str,
    *,
    title: str,
    body: str,
    url: str = "/dashboard",
    tag: str | None = None,
    data: dict[str, Any] | None = None,
    db=None,
) -> None:
    """Best-effort Web Push fan-out. Never raise into business flows."""
    if not settings.vapid_public_key or not settings.vapid_private_key:
        return

    webpush, webpush_exception = _webpush()
    if webpush is None:
        logger.warning("pywebpush is not installed; skipping browser push")
        return

    db = db or get_supabase()
    try:
        rows = (
            db.table("push_subscriptions")
            .select("id,endpoint,p256dh,auth")
            .eq("tenant_id", tenant_id)
            .eq("user_id", user_id)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning("Failed to load push subscriptions for user=%s: %s", user_id, exc)
        return

    if not rows:
        return

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
        "data": data or {},
    })
    claims = {"sub": settings.vapid_subject or "mailto:support@aira.ai"}

    for row in rows:
        sub_info = {
            "endpoint": row["endpoint"],
            "keys": {
                "p256dh": row["p256dh"],
                "auth": row["auth"],
            },
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=claims,
            )
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if webpush_exception and isinstance(exc, webpush_exception) and status_code in {404, 410}:
                try:
                    db.table("push_subscriptions").delete().eq("id", row["id"]).execute()
                except Exception:
                    pass
            else:
                logger.warning("Web Push delivery failed for user=%s: %s", user_id, exc)
