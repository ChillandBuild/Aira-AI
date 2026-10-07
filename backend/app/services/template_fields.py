"""Per-template variable map: which lead / alert detail fills each {{n}}.

The escalation and hot-lead WhatsApp alerts fill a template's placeholders in a
fixed order (name, phone, ...). A tenant can save, on the template itself, which
field fills which slot (`message_templates.variable_map`, e.g. {"1": "lead_phone"}).
No saved map = the fixed order, unchanged. A mapped field the alert can't supply
(escalation reason on a hot-lead alert) falls back to that slot's fixed value.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

logger = logging.getLogger(__name__)

VAR_RE = re.compile(r"\{\{(\d+)\}\}")
IST = timezone(timedelta(hours=5, minutes=30))
COLLECTED_PREFIX = "collected:"
_COLLECTED_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .-]{0,63}$")
_MAX_VALUE_CHARS = 200

FIELDS = frozenset({
    "lead_name", "lead_phone", "chat_link", "lead_source", "escalation_reason",
    "lead_temperature", "assigned_agent", "enquiry_date", "last_message",
    "business_name", "alert_time", "channel", "call_status",
})

_CHANNEL_LABELS = {"whatsapp": "WhatsApp", "instagram": "Instagram", "facebook": "Facebook", "telegram": "Telegram"}
_CALL_STATUS_LABELS = {
    "new": "New", "trying": "Trying", "unreachable": "Unreachable", "hot": "Hot", "warm": "Warm",
    "cold": "Cold", "callback": "Call later", "converted": "Converted", "not_interested": "Not interested",
    "disqualified": "Disqualified", "wrong_number": "Wrong number", "dnc": "Do not call",
    "language_barrier": "Language barrier",
}


def chat_link(lead_id: str) -> str:
    return f"https://www.bloommatrix.in/anril/dashboard/conversations?lead_id={lead_id}"


def is_valid_field(field: object) -> bool:
    if not isinstance(field, str):
        return False
    if field.startswith(COLLECTED_PREFIX):
        return bool(_COLLECTED_KEY_RE.match(field[len(COLLECTED_PREFIX):]))
    return field in FIELDS


def placeholder_count(body: str | None) -> int:
    return len(set(VAR_RE.findall(body or "")))


def _one_line(value: str) -> str:
    """Meta rejects parameters with new lines, tabs or long runs of spaces, and empty ones."""
    text = " ".join(str(value).split())[:_MAX_VALUE_CHARS]
    return text or "-"


def _ist_date(value: str | None) -> str:
    if not value:
        return ""
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(IST)
    return f"{dt.day} {dt:%b %Y}"


def _ist_datetime(dt: datetime) -> str:
    dt = dt.astimezone(IST)
    return f"{dt.day} {dt:%b %Y}, {dt.hour % 12 or 12}:{dt:%M %p}"


class AlertFields:
    """Resolves field names to text for one lead, loading each detail only when asked.

    `known` holds what the alert itself supplies (escalation reason, Hot/Warm label,
    lead source); a value may be a zero-argument callable so it is only computed
    when a template uses it. Fields not in `known` that are alert-specific resolve
    to None, which tells the builder to use the slot's fixed value.
    """

    _ALERT_ONLY = {"escalation_reason", "lead_temperature", "lead_source"}

    def __init__(self, db, tenant_id: str, lead: dict, known: dict[str, str | Callable[[], str]] | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.lead = lead
        self.known = known or {}
        self._last_inbound: dict | None = None

    def get(self, field: str) -> str | None:
        try:
            value = self._resolve(field)
        except Exception:
            logger.exception("Template field %s failed for lead %s", field, self.lead.get("id"))
            return None
        return None if value is None else _one_line(value)

    def _resolve(self, field: str) -> str | None:
        if field in self.known:
            v = self.known[field]
            return v() if callable(v) else v
        if field in self._ALERT_ONLY:
            return None
        lead = self.lead
        if field.startswith(COLLECTED_PREFIX):
            data = lead.get("collected_data") or {}
            v = data.get(field[len(COLLECTED_PREFIX):]) if isinstance(data, dict) else None
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            return "" if v is None else str(v)
        if field == "lead_name":
            return lead.get("name") or "Lead"
        if field == "lead_phone":
            return lead.get("phone") or ""
        if field == "chat_link":
            return chat_link(lead["id"])
        if field == "enquiry_date":
            return _ist_date(lead.get("created_at"))
        if field == "alert_time":
            return _ist_datetime(datetime.now(timezone.utc))
        if field == "call_status":
            status = lead.get("call_status")
            return _CALL_STATUS_LABELS.get(status, status.replace("_", " ").capitalize()) if status else "Not called yet"
        if field == "assigned_agent":
            return self._agent_name()
        if field == "business_name":
            rows = self.db.table("tenants").select("name").eq("id", self.tenant_id).limit(1).execute().data or []
            return (rows[0].get("name") if rows else "") or ""
        if field == "last_message":
            msg = self._latest_inbound()
            if not msg:
                return ""
            return msg.get("content") or (f"[{msg['media_type']}]" if msg.get("media_type") else "")
        if field == "channel":
            msg = self._latest_inbound()
            ch = (msg or {}).get("channel") or "whatsapp"
            return _CHANNEL_LABELS.get(ch, ch.capitalize())
        return None

    def _agent_name(self) -> str:
        caller_id = self.lead.get("assigned_to")
        if not caller_id:
            return "Unassigned"
        rows = (
            self.db.table("callers").select("name")
            .eq("id", caller_id).eq("tenant_id", self.tenant_id).limit(1).execute().data or []
        )
        return (rows[0].get("name") if rows else "") or "Unassigned"

    def _latest_inbound(self) -> dict:
        if self._last_inbound is None:
            rows = (
                self.db.table("messages").select("content,channel,media_type")
                .eq("lead_id", self.lead["id"]).eq("tenant_id", self.tenant_id).eq("direction", "inbound")
                .order("created_at", desc=True).limit(1).execute().data or []
            )
            self._last_inbound = rows[0] if rows else {}
        return self._last_inbound


def build_body_components(template: dict, defaults: list[str], fields: AlertFields | None = None) -> list[dict] | None:
    """Body parameters for `template`: the saved variable map where one exists,
    otherwise `defaults` in order (the alert's fixed order). None when the body
    has no placeholders."""
    count = placeholder_count(template.get("body_text"))
    if not count:
        return None
    var_map = template.get("variable_map") or {}
    if not var_map or fields is None:
        values = defaults[:count]
    else:
        values = []
        for i in range(1, count + 1):
            field = var_map.get(str(i))
            value = fields.get(field) if is_valid_field(field) else None
            if value is None:
                value = defaults[i - 1] if i <= len(defaults) else "-"
            values.append(value)
    return [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]
