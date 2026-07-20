"""Per-tenant LLM token metering.

Records provider-reported token usage (never estimated) into
tenant_token_usage via the atomic increment_token_usage() RPC
(migration 142), one row per (tenant, IST day, purpose, provider, model).

Same contract as entitlements.meter(): TRACK-ONLY and best-effort — this must
never raise, block, cap, or break the AI call it is metering. Callers must not
branch on it. Called from inside the provider client wrappers
(groq/gemini/openai/sarvam_client.py) so call sites keep their signatures.
"""
import logging

logger = logging.getLogger(__name__)


def record_tokens(
    tenant_id: str | None,
    purpose: str,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    """Best-effort token metering. Never raises.

    input_tokens/output_tokens come straight from the provider's usage block;
    None (provider omitted the block) still records the call with zero tokens
    so call counts stay trustworthy even if a provider drops the field.
    """
    if not tenant_id:
        return
    try:
        from app.db.supabase import get_supabase

        get_supabase().rpc(
            "increment_token_usage",
            {
                "p_tenant_id": tenant_id,
                "p_purpose": purpose,
                "p_provider": provider,
                "p_model": model,
                "p_input_tokens": int(input_tokens or 0),
                "p_output_tokens": int(output_tokens or 0),
            },
        ).execute()
    except Exception as e:
        logger.warning(
            f"token metering failed (tenant={tenant_id}, purpose={purpose}, "
            f"provider={provider}, model={model}): {e}"
        )


def record_groq_sdk(tenant_id: str | None, purpose: str, model: str, resp) -> None:
    """Same as record_tokens, but reads token counts off a raw groq-sdk
    ChatCompletion response (resp.usage.prompt_tokens/completion_tokens) --
    for the several call sites that use get_groq_client() directly instead
    of groq_client.groq_chat_completion()."""
    usage = getattr(resp, "usage", None)
    record_tokens(
        tenant_id, purpose, "groq", model,
        getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None),
    )
