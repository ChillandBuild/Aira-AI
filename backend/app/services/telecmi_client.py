"""
TeleCMI CHUB India (PIOPIY) click-to-call client.

India model: mint a per-agent login token (agentLogin, 30-day expiry), then
connect via agentConnect — TeleCMI rings the agent's registered mobile first,
then dials the lead. No app secret / user_id / callerid / webrtc here; those
belong to the global CHUB endpoint, which this account is NOT on.

Docs:
  https://doc.telecmi.com/chub-india/docs/login-token/
  https://doc.telecmi.com/chub-india/docs/click-to-call/
"""
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AGENT_LOGIN_URL = "https://piopiy.telecmi.com/v1/agentLogin"
AGENT_CONNECT_URL = "https://piopiy.telecmi.com/v1/agentConnect"

# Tokens expire after 30 days; refresh a day early. In-process cache keyed by
# (tenant_id, agent_id) so one tenant can never be served another tenant's token.
_TOKEN_TTL_SECONDS = 29 * 24 * 3600
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


async def _agent_login(agent_id: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(AGENT_LOGIN_URL, json={"id": agent_id, "password": password})
        data = resp.json()
    if data.get("code") != 200 or not data.get("token"):
        logger.error(f"TeleCMI agentLogin rejected: {data}")
        raise RuntimeError(f"TeleCMI login failed: {data.get('msg', 'unknown error')}")
    return data["token"]


async def _get_token(tenant_id: str, agent_id: str, password: str, *, force: bool = False) -> str:
    now = time.time()
    key = (tenant_id, agent_id)
    if not force:
        cached = _token_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
    token = await _agent_login(agent_id, password)
    _token_cache[key] = (token, now + _TOKEN_TTL_SECONDS)
    return token


async def _connect(token: str, to: str, custom: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"token": token, "to": _normalize_phone(to)}
    if custom:
        payload["extra_params"] = {"call_log_id": custom}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(AGENT_CONNECT_URL, json=payload)
        return resp.json()


async def initiate_click2call(
    tenant_id: str,
    agent_id: str,
    password: str,
    to: str,
    *,
    custom: str | None = None,
) -> dict[str, Any]:
    logger.info(f"TeleCMI agentConnect: tenant={tenant_id}, agent_id={agent_id}, to={to}")
    token = await _get_token(tenant_id, agent_id, password)
    data = await _connect(token, to, custom)

    # 404 = invalid number OR stale token. Re-login once and retry to rule out the token.
    if data.get("code") == 404:
        logger.info("TeleCMI agentConnect 404 — refreshing token and retrying once")
        token = await _get_token(tenant_id, agent_id, password, force=True)
        data = await _connect(token, to, custom)

    if data.get("code") != 200:
        logger.error(f"TeleCMI rejected: {data}")
        raise RuntimeError(f"TeleCMI error: {data.get('msg', 'Unknown TeleCMI error')}")
    logger.info(f"TeleCMI success: request_id={data.get('request_id')}")
    return data


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "").replace("+", "")
    if len(cleaned) == 10:
        cleaned = f"91{cleaned}"
    return cleaned
