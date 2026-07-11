# backend/app/services/openrouter_client.py
import httpx

from app.config import settings

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_openrouter_api_key() -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key not configured")
    return settings.openrouter_api_key


async def openrouter_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
) -> str:
    """OpenRouter's Chat Completions API (OpenAI-compatible request/response shape).
    `model` is an OpenRouter model slug, e.g. "openai/gpt-5-mini" or
    "google/gemini-2.5-flash" or "meta-llama/llama-3.3-70b-instruct". OpenRouter
    routes to the underlying provider using the BYOK keys configured on the
    platform's openrouter.ai account -- no per-provider credentials in this app."""
    api_key = get_openrouter_api_key()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENROUTER_CHAT_URL,
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
