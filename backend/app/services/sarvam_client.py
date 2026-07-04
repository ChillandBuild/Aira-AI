# backend/app/services/sarvam_client.py
import httpx

from app.config_dynamic import get_setting
from app.config import settings

SARVAM_BASE_URL = "https://api.sarvam.ai"
SARVAM_CHAT_URL = f"{SARVAM_BASE_URL}/v1/chat/completions"


def get_sarvam_api_key(tenant_id: str | None = None) -> str:
    api_key = get_setting("sarvam_api_key", tenant_id=tenant_id) or settings.sarvam_api_key
    if not api_key:
        raise RuntimeError("Sarvam API key not configured")
    return api_key


async def sarvam_chat_completion(
    messages: list[dict],
    model: str = "sarvam-30b",
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> str:
    """Sarvam's Chat Completions API (OpenAI-compatible response shape). Unlike the
    Speech-to-Text/Document Digitization endpoints (api-subscription-key header),
    this one uses standard Authorization: Bearer auth."""
    api_key = get_sarvam_api_key(tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SARVAM_CHAT_URL,
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
