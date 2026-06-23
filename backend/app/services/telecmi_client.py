"""
TeleCMI Click-to-Call client (CHUB India).

Docs: https://doc.telecmi.com/chub-india/docs/click-to-call-admin
"""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELECMI_BASE_URL = "https://piopiy.telecmi.com/v1/adminConnect"


async def initiate_click2call(
    agent_id: str,
    token: str,
    to: str,
    *,
    custom: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "token": token,
        "to": _normalize_phone(to),
    }
    if custom:
        payload["custom"] = custom

    logger.info(f"TeleCMI adminConnect: agent_id={agent_id}, to={to}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TELECMI_BASE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info(f"TeleCMI response: {data}")
    if data.get("code") != 200:
        error_msg = data.get("msg", "Unknown TeleCMI error")
        raise RuntimeError(f"TeleCMI error: {error_msg}")

    return data


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "").replace("+", "")
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned
