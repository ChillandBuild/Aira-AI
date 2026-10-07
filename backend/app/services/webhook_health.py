"""Per-channel last inbound event plus recent token_invalid incidents for one tenant.

Shared by GET /api/v1/settings/webhook-health and the Anril Brain status block, so both
apply the same 48-hour token rule."""
from datetime import datetime, timedelta, timezone

CHANNELS = ("whatsapp", "instagram", "facebook", "telegram")
TOKEN_ALERT_WINDOW_HOURS = 48


def get_webhook_health(db, tenant_id: str) -> dict:
    """Return {"health": {channel: {"last_event"}}, "token_alerts": [...]}. Tenant-scoped."""
    health: dict = {}
    for channel in CHANNELS:
        row = (
            db.table("messages")
            .select("created_at")
            .eq("tenant_id", tenant_id)
            .eq("channel", channel)
            .eq("direction", "inbound")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        health[channel] = {"last_event": row.data[0]["created_at"] if row.data else None}

    # Token alerts: any token_invalid incidents in the last 48h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=TOKEN_ALERT_WINDOW_HOURS)).isoformat()
    alerts = (
        db.table("incidents")
        .select("type,detail,created_at")
        .eq("tenant_id", tenant_id)
        .eq("type", "token_invalid")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .execute()
    )
    token_alerts = []
    for inc in (alerts.data or []):
        detail = inc.get("detail") or {}
        token_alerts.append({
            "channel": detail.get("channel"),
            "error": detail.get("error"),
            "created_at": inc["created_at"],
        })

    return {"health": health, "token_alerts": token_alerts}
