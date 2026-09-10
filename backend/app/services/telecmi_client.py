"""
TeleCMI CHUB Click-to-Call client.

Docs:
  https://doc.telecmi.com/chub/docs/app-auth
  https://doc.telecmi.com/chub/docs/click-to-call-admin
"""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELECMI_BASE_URL = "https://rest.telecmi.com/v2/webrtc/click2call"


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "").replace("+", "")
    if len(cleaned) == 10:
        cleaned = f"91{cleaned}"
    return cleaned


async def initiate_click2call(
    agent_id: str,
    secret: str,
    to: str,
    callerid: str,
    *,
    custom: str | None = None,
    followme: bool = True,
    webrtc: bool = False,
) -> dict[str, Any]:
    """Initiate click-to-call via TeleCMI CHUB Admin API.

    Connects to the agent's phone (via followme mobile by default, or webrtc softphone)
    first, and once answered, connects to the customer number.
    """
    normalized_to = _normalize_phone(to)
    normalized_callerid = _normalize_phone(callerid)

    payload: dict[str, Any] = {
        "user_id": agent_id,
        "secret": secret,
        "to": int(normalized_to) if normalized_to.isdigit() else normalized_to,
        "callerid": int(normalized_callerid) if normalized_callerid.isdigit() else normalized_callerid,
        "webrtc": webrtc,
        "followme": followme,
    }
    if custom:
        payload["extra_params"] = {"call_log_id": custom}

    logger.info(f"TeleCMI CHUB click2call: user_id={agent_id}, callerid={normalized_callerid}, to={normalized_to}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TELECMI_BASE_URL, json=payload)
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise RuntimeError(f"TeleCMI returned unexpected non-JSON response ({resp.status_code})")

    code = data.get("code")
    if code != 200:
        msg = data.get("msg") or data.get("message") or f"HTTP {resp.status_code}"
        logger.error(f"TeleCMI click2call rejected: code={code}, msg={msg}, response={data}")
        if code == 407:
            raise RuntimeError("Invalid TeleCMI App Secret. Please verify App Secret in Settings → Telecalling.")
        elif code == 404:
            raise RuntimeError(f"Invalid TeleCMI User ID '{agent_id}'. Please check caller's User ID in Team / Roles.")
        elif code == 420:
            raise RuntimeError(f"TeleCMI error (420): {msg}. Follow-me calls to mobile numbers are disabled on this TeleCMI account. Please contact TeleCMI support to enable Follow-Me on your App.")
        elif code == 400:
            raise RuntimeError(f"TeleCMI validation error: {msg}")
        raise RuntimeError(f"TeleCMI error ({code}): {msg}")

    request_id = data.get("request_id")
    logger.info(f"TeleCMI click2call success: request_id={request_id}")
    return data
