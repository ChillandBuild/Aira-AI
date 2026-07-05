import json
import logging
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_NOTIFICATION_CONFIG_DEFAULT: dict = {
    "push_enabled": True,
    "events": {
        "callback_due": True,
        "callback_claimable": True,
        "callback_taken_over": True,
        "lead_assigned": True,
        "lead_replied": True,
        "handover_new": True,
    },
    "claimable_threshold_minutes": 15,
    "claimable_audience": "telecallers_and_admin",
    "claimable_caller_ids": [],
    "quiet_hours": {"enabled": False, "start_hour": 22, "end_hour": 8},
    "whatsapp_notifications": {
        "enabled": False,
        "recipient_phones": [],
        "template_id": None,
        "target_segments": ["A"],
        "delay_minutes": 5,
    },
}


def get_notification_config(tenant_id: str, db=None) -> dict:
    """Return notification_config from app_settings, deep-merged with defaults."""
    db = db or get_supabase()
    merged = {
        **_NOTIFICATION_CONFIG_DEFAULT,
        "events": dict(_NOTIFICATION_CONFIG_DEFAULT["events"]),
        "quiet_hours": dict(_NOTIFICATION_CONFIG_DEFAULT["quiet_hours"]),
        "whatsapp_notifications": dict(_NOTIFICATION_CONFIG_DEFAULT["whatsapp_notifications"]),
    }
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "notification_config")
            .maybe_single()
            .execute()
        )
        if row and row.data:
            stored = json.loads(row.data["value"])
            if isinstance(stored, dict):
                merged["events"] = {**merged["events"], **(stored.get("events") or {})}
                merged["quiet_hours"] = {**merged["quiet_hours"], **(stored.get("quiet_hours") or {})}
                merged["whatsapp_notifications"] = {**merged["whatsapp_notifications"], **(stored.get("whatsapp_notifications") or {})}
                for k in ("push_enabled", "claimable_threshold_minutes", "claimable_audience", "claimable_caller_ids"):
                    if k in stored:
                        merged[k] = stored[k]
    except Exception as e:
        logger.warning(f"get_notification_config failed for {tenant_id}: {e}")
    return merged


def save_notification_config(tenant_id: str, config: dict) -> None:
    """Persist notification_config to app_settings."""
    db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "notification_config",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


def _in_quiet_hours(quiet: dict, ist_hour: int) -> bool:
    """True if ist_hour falls inside the configured quiet window. Handles midnight wrap."""
    if not quiet.get("enabled"):
        return False
    start = quiet.get("start_hour", 22)
    end = quiet.get("end_hour", 8)
    if start == end:
        return False
    if start < end:
        return start <= ist_hour < end
    return ist_hour >= start or ist_hour < end


def push_allowed(tenant_id: str, event_type: str, *, db=None) -> bool:
    """Whether a web push for this event type may be delivered right now.

    Gates on master switch, per-event toggle (unknown types default allowed),
    and quiet hours (IST). In-app notifications are NEVER gated by this.
    """
    # Fail open: if the config can't be read/evaluated, allow the push rather
    # than silently dropping it — push is best-effort and the in-app row is
    # already written regardless.
    try:
        cfg = get_notification_config(tenant_id, db=db)
        if not cfg.get("push_enabled"):
            return False
        if not cfg.get("events", {}).get(event_type, True):
            return False
        quiet = cfg.get("quiet_hours", {})
        if quiet.get("enabled"):
            ist_hour = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).hour
            if _in_quiet_hours(quiet, ist_hour):
                return False
        return True
    except Exception as e:
        logger.warning(f"push_allowed check failed for {tenant_id}/{event_type}: {e}")
        return True
