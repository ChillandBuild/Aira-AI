# backend/app/services/groq_client.py
from groq import Groq, AsyncGroq
from app.config_dynamic import get_setting, require_tenant_setting
from app.config import settings

def get_groq_client(tenant_id: str | None = None, is_async: bool = True):
    api_key = get_setting("groq_api_key", tenant_id=tenant_id) or settings.groq_api_key
    if not api_key:
        raise RuntimeError("Groq API key not configured")
    return AsyncGroq(api_key=api_key) if is_async else Groq(api_key=api_key)


# Qwen3's thinking mode is on by default and emits a <think>...</think> block inline in
# content, eating the token budget and leaking the reasoning trace to the customer if not
# suppressed. Live-tested 2026-07-14: reasoning_format="hidden" gives a clean final answer
# for Qwen models, but is a HARD 400 error ("not supported with this model") on non-
# reasoning models like Llama 3.3 70B -- must only be passed for models that need it.
_REASONING_MODELS = {"qwen/qwen3-32b"}


def _reasoning_kwargs(model: str) -> dict:
    return {"reasoning_format": "hidden"} if model in _REASONING_MODELS else {}


async def groq_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> str:
    """No fallback to a platform key -- every client must configure their own groq_api_key
    for reply generation (operator decision, see decisions/log.md). This is stricter than
    get_groq_client's fallback, which other Groq-backed features (scoring, summaries) keep
    using unchanged."""
    api_key = require_tenant_setting("groq_api_key", tenant_id)
    client = AsyncGroq(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
        **_reasoning_kwargs(model),
    )
    return (resp.choices[0].message.content or "").strip()


async def groq_chat_completion_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> tuple[str, list[dict]]:
    api_key = require_tenant_setting("groq_api_key", tenant_id)
    client = AsyncGroq(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, tools=tools,
        **_reasoning_kwargs(model),
    )
    message = resp.choices[0].message
    content = (message.content or "").strip()
    tool_calls = [tc.model_dump() for tc in (message.tool_calls or [])]
    return content, tool_calls
