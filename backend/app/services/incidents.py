"""Shared incident recording helpers.

Kept dependency-light (takes `db` as a param) so both the proactive scheduler
in main.py and reactive send paths (e.g. send_telegram) can record incidents
without circular imports.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Suppress repeat token_invalid incidents for the same (tenant, channel) within
# this window so a persistently-broken token doesn't spam the incidents table.
_TOKEN_INCIDENT_DEDUP_HOURS = 23


def create_token_incident(db, tenant_id: str, channel: str, error_msg: str) -> None:
    """Record a `token_invalid` incident, deduped per (tenant, channel) per 23h.

    Dedup is per-channel (not per-tenant) so a broken Telegram token still
    surfaces in webhook-health even when another channel already logged one.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=_TOKEN_INCIDENT_DEDUP_HOURS)).isoformat()
        # Fetch recent token_invalid rows for the tenant and dedup per-channel in Python.
        # Mirrors how webhook_health reads incidents (detail->>channel JSON filtering is
        # avoided since it's not an established query pattern in this codebase).
        recent = (
            db.table("incidents")
            .select("detail")
            .eq("tenant_id", tenant_id)
            .eq("type", "token_invalid")
            .gte("created_at", cutoff)
            .execute()
        )
        for row in (recent.data or []):
            if (row.get("detail") or {}).get("channel") == channel:
                return
        db.table("incidents").insert({
            "tenant_id": tenant_id,
            "type": "token_invalid",
            "detail": {"channel": channel, "error": error_msg},
        }).execute()
        logger.warning(f"Token invalid incident created: tenant={tenant_id} channel={channel}")
    except Exception as e:
        logger.error(f"Failed to create token incident: {e}")
