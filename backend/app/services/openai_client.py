# backend/app/services/openai_client.py
import httpx

from app.config_dynamic import require_tenant_setting
from app.services.token_meter import record_tokens

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _record(tenant_id: str | None, purpose: str, model: str, data: dict) -> None:
    usage = data.get("usage") or {}
    record_tokens(
        tenant_id, purpose, "openai", model,
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
    )


def _completion_payload(messages: list[dict], model: str, temperature: float, max_tokens: int) -> dict:
    """GPT-5 family models reject 'temperature' (other than the default of 1) and
    'max_tokens' (renamed to 'max_completion_tokens') -- see decisions/log.md. They also
    spend max_completion_tokens on hidden reasoning before writing a reply, which can
    exhaust the whole budget and return empty content -- reasoning_effort=minimal keeps
    that reasoning pass short enough to leave room for the actual chat reply."""
    payload = {"messages": messages, "model": model}
    if model.startswith("gpt-5"):
        payload["max_completion_tokens"] = max_tokens
        # Dotted point releases (gpt-5.1, gpt-5.4, ...) replaced "minimal" with "none" as
        # the lowest reasoning_effort value and reject "minimal"; the original gpt-5 /
        # gpt-5-mini / gpt-5-nano family is the reverse -- accepts "minimal", rejects
        # "none". Confirmed live against both families.
        payload["reasoning_effort"] = "none" if model.startswith("gpt-5.") else "minimal"
    else:
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
    return payload


async def openai_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
    purpose: str = "unknown",
) -> str:
    """OpenAI's Chat Completions API. No fallback to a platform key -- every client must
    configure their own openai_api_key (operator decision, see decisions/log.md)."""
    api_key = require_tenant_setting("openai_api_key", tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=_completion_payload(messages, model, temperature, max_tokens),
        )
        resp.raise_for_status()
        data = resp.json()
    _record(tenant_id, purpose, model, data)
    return (data["choices"][0]["message"]["content"] or "").strip()


async def openai_chat_completion_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
    purpose: str = "unknown",
) -> tuple[str, list[dict]]:
    api_key = require_tenant_setting("openai_api_key", tenant_id)
    payload = _completion_payload(messages, model, temperature, max_tokens)
    payload["tools"] = tools
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    _record(tenant_id, purpose, model, data)
    message = data["choices"][0]["message"]
    content = (message.get("content") or "").strip()
    tool_calls = message.get("tool_calls") or []
    return content, tool_calls
