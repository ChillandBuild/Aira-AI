"""Gates shared by every automated AI-authored outbound path.

Deliberately narrow. It covers ONLY the three lead-level checks that
reengagement_service and silence_nudge genuinely share. reengagement does not
check ai_enabled/converted_at/blocked_at, so those are NOT here — widening this
module would silently change re-engagement behaviour.
"""
import logging

from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)


def master_switch_on(tenant_id: str) -> bool:
    """ai_auto_reply_enabled is the single master switch for every automated
    AI-authored outbound message, not just inbound replies. Callers decide
    whether an off switch consumes their job or leaves it queued."""
    return get_setting("ai_auto_reply_enabled", fallback="true", tenant_id=tenant_id) != "false"


def lead_blocks_automated_outbound(lead: dict) -> str | None:
    """Return a human-readable skip reason, or None if sending is allowed."""
    if not lead.get("phone"):
        return "no phone"
    if lead.get("whatsapp_undeliverable"):
        return "whatsapp undeliverable"
    if lead.get("opted_out"):
        return "opted out"
    return None
