"""WhatsApp Cloud API template send, using the client's own Meta token. The token goes only in the
Authorization header of this one request; it is never logged or placed in an error."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("anril_connector")
GRAPH_BASE = "https://graph.facebook.com"
META_TIMEOUT_SECONDS = 15.0
_RETRYABLE_STATUSES = (429, 503)


@dataclass(frozen=True)
class MetaOutcome:
    ok: bool
    message_id: Optional[str] = None
    reason: Optional[str] = None
    retryable: bool = False  # the request provably never reached Meta, so sending it again cannot double-send


def template_body(to_number: str, template_name: str, lang_code: str, components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Same body as backend/app/services/meta_cloud.py::send_template_message."""
    return {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {"name": template_name, "language": {"code": lang_code}, "components": components or []},
    }


def _error_reason(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error") or {}
        code, message = err.get("code"), err.get("message")
        if message:
            return f"meta_{code}: {message}" if code is not None else f"meta: {message}"
    except (ValueError, AttributeError):
        pass
    return f"http_{resp.status_code}"


def send_template(
    http: httpx.Client, graph_version: str, phone_number_id: str, token: str, body: Dict[str, Any],
) -> MetaOutcome:
    url = f"{GRAPH_BASE}/{graph_version}/{phone_number_id}/messages"
    try:
        resp = http.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=META_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("meta send failed: %s", type(exc).__name__)
        # only a failed connect is safe to repeat; a read timeout may mean Meta already accepted the message
        never_arrived = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
        return MetaOutcome(ok=False, reason=f"network_error: {type(exc).__name__}", retryable=never_arrived)
    if not resp.is_success:
        return MetaOutcome(ok=False, reason=_error_reason(resp), retryable=resp.status_code in _RETRYABLE_STATUSES)
    try:
        message_id = (resp.json().get("messages") or [{}])[0].get("id")
    except (ValueError, AttributeError, IndexError):
        message_id = None
    return MetaOutcome(ok=True, message_id=message_id)
