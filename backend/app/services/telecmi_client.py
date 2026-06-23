"""
TeleCMI Click-to-Call client.

Docs: https://doc.telecmi.com/chub/docs/click-to-call-admin
"""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELECMI_BASE_URL = "https://rest.telecmi.com/v2/webrtc/click2call"


async def initiate_click2call(
    agent_id: str,
    token: str,
    to: str,
    callerid: str,
    *,
    custom: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_id": agent_id,
        "secret": token,
        "to": _normalize_phone(to),
        "callerid": callerid,
        "webrtc": True,
        "followme": False,
    }
    if custom:
        payload["extra_params"] = {"call_log_id": custom}

    logger.info(f"TeleCMI click2call: agent_id={agent_id}, to={to}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TELECMI_BASE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 200:
        logger.error(f"TeleCMI rejected: {data}")
        error_msg = data.get("msg", "Unknown TeleCMI error")
        raise RuntimeError(f"TeleCMI error: {error_msg}")
    logger.info(f"TeleCMI success: request_id={data.get('request_id')}")

    return data


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "").replace("+", "")
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned
