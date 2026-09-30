"""'Aira can reply': auto-reply switch, WhatsApp/channel connection, quota.

Connection reuses services/webhook_health (the GET /settings/webhook-health logic) and is
included only for callers with settings.view. A token problem is a token_invalid incident
in the last 48 hours (same rule as webhook-health; not the operator's "ever" rule).
Quota is null unless some metric has a hard_cap: no tenant has one today."""
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from app.config_dynamic import get_setting
from app.services import entitlements, webhook_health
from app.services.brain.access import has_permission

QUIET_AFTER_DAYS = 7


def auto_reply_state(tenant_id: str) -> str:
    """'on' unless the owner switched it off (ai_reply reads the same key, default on)."""
    return "on" if get_setting("ai_auto_reply_enabled", fallback="true", tenant_id=tenant_id) == "true" else "off"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def connection_status(db, tenant_id: str, *, now: datetime | None = None) -> dict:
    """state: token_problem (48h incident) > ok (an inbound event within QUIET_AFTER_DAYS)
    > quiet (events seen, none recently) > unknown (never any inbound event)."""
    now = now or datetime.now(timezone.utc)
    report = webhook_health.get_webhook_health(db, tenant_id)
    problem_channels = {a.get("channel") for a in report["token_alerts"]}
    channels = [
        {
            "channel": channel,
            "last_event": info.get("last_event"),
            "token_problem": channel in problem_channels,
        }
        for channel, info in report["health"].items()
    ]
    seen = [t for t in (_parse_time(c["last_event"]) for c in channels) if t]
    if report["token_alerts"]:
        state = "token_problem"
    elif not seen:
        state = "unknown"
    elif max(seen) >= now - timedelta(days=QUIET_AFTER_DAYS):
        state = "ok"
    else:
        state = "quiet"
    return {"state": state, "channels": channels}


def quota_status(db, tenant_id: str) -> dict | None:
    """Metrics with a hard_cap this billing period, or None when nothing is capped.
    Read-only: uses compute_period_key, never get_billing_period (which rolls the cycle)."""
    sub = (
        db.table("tenant_subscriptions").select("period_start,period_end").eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    period = entitlements.compute_period_key(
        (sub[0] if sub else {}).get("period_start"), (sub[0] if sub else {}).get("period_end"),
    )
    rows = (
        db.table("tenant_usage_counters")
        .select("metric,used,hard_cap")
        .eq("tenant_id", tenant_id)
        .eq("period", period)
        .execute()
    ).data or []
    capped = [
        {"metric": r["metric"], "used": r.get("used") or 0, "hard_cap": r["hard_cap"]}
        for r in rows if r.get("hard_cap") is not None
    ]
    return {"metrics": capped} if capped else None


def build_status(db, tenant_id: str, *, role: str | None, permissions: Iterable[str] | None) -> dict:
    status = {"auto_reply": auto_reply_state(tenant_id), "quota": quota_status(db, tenant_id)}
    if has_permission(role, permissions, "settings.view"):
        status = {**status, "connection": connection_status(db, tenant_id)}
    return status
