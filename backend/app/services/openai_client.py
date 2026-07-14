# backend/app/services/openai_client.py
import httpx

from app.config_dynamic import require_tenant_setting

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


async def openai_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> str:
    """OpenAI's Chat Completions API. No fallback to a platform key -- every client must
    configure their own openai_api_key (operator decision, see decisions/log.md)."""
    api_key = require_tenant_setting("openai_api_key", tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def openai_chat_completion_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> tuple[str, list[dict]]:
    api_key = require_tenant_setting("openai_api_key", tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    message = data["choices"][0]["message"]
    content = (message.get("content") or "").strip()
    tool_calls = message.get("tool_calls") or []
    return content, tool_calls
