"""Per-account partner send mode: how this account's app calls POST /partner/send-template.

"template" = a template_code (the original AstroTamil call); "event" = an Auto Messages event
key. One way per account, not per call. No stored value means "template", so an account that
never opened the Developer page behaves as it always did. Stored in app_settings (key
partner_send_mode), read straight from the db on every call so a switch takes effect at once on
every server instance (get_setting's 60-second cache would not).
"""
import logging

logger = logging.getLogger(__name__)

KEY = "partner_send_mode"
MODES = ("template", "event")
DEFAULT_MODE = "template"

WRONG_MODE_CODE = "wrong_mode"
EVENT_REFUSED_MESSAGE = "This account sends by template ID. To send events, switch to Event on the Developer page."
TEMPLATE_REFUSED_MESSAGE = (
    "This account sends by event. To send template IDs, switch to Template ID on the Developer page."
)


def get_partner_send_mode(db, tenant_id: str) -> str:
    """The account's mode. Any read problem (or a stored value that is not a mode) counts as
    "template" so a settings hiccup can never break the call AstroTamil makes."""
    try:
        rows = (
            db.table("app_settings").select("value")
            .eq("tenant_id", tenant_id).eq("key", KEY).limit(1).execute()
        ).data or []
    except Exception as e:
        logger.warning(f"{KEY} read failed for tenant {tenant_id}, using '{DEFAULT_MODE}': {e}")
        return DEFAULT_MODE
    value = rows[0].get("value") if rows else None
    return value if value in MODES else DEFAULT_MODE


def save_partner_send_mode(db, tenant_id: str, mode: str) -> None:
    """Raises when the write fails: the dashboard must never say "saved" for a mode that was not."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    db.table("app_settings").upsert(
        {"key": KEY, "value": mode, "tenant_id": tenant_id, "is_secret": False},
        on_conflict="key,tenant_id",
    ).execute()
