"""Admin-set cost rates per (provider, model) -- migration 143. Aira funds
every provider account (not the tenant), so cost estimation reads a rate the
admin has entered, never a hardcoded/guessed public price list. A (provider,
model) pair with no configured rate must surface as "unknown", never as ₹0 --
silently zeroing it would understate spend without any indication."""
from supabase import Client


def get_rates(db: Client) -> dict[tuple[str, str], dict]:
    """Returns {(provider, model): {"input_rate_per_1k_inr": float, "output_rate_per_1k_inr": float}}."""
    rows = db.table("provider_model_rates").select(
        "provider, model, input_rate_per_1k_inr, output_rate_per_1k_inr"
    ).execute().data or []
    return {
        (r["provider"], r["model"]): {
            "input_rate_per_1k_inr": float(r["input_rate_per_1k_inr"]),
            "output_rate_per_1k_inr": float(r["output_rate_per_1k_inr"]),
        }
        for r in rows
    }


def estimate_cost(
    rates: dict[tuple[str, str], dict],
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """None means no rate configured for this (provider, model) -- callers must
    treat this as "unknown", not zero, and flag it rather than silently summing
    it in as if it cost nothing."""
    rate = rates.get((provider, model))
    if rate is None:
        return None
    return (
        (input_tokens / 1000) * rate["input_rate_per_1k_inr"]
        + (output_tokens / 1000) * rate["output_rate_per_1k_inr"]
    )


def upsert_rate(db: Client, provider: str, model: str, input_rate_per_1k_inr: float, output_rate_per_1k_inr: float) -> None:
    db.table("provider_model_rates").upsert({
        "provider": provider,
        "model": model,
        "input_rate_per_1k_inr": input_rate_per_1k_inr,
        "output_rate_per_1k_inr": output_rate_per_1k_inr,
    }, on_conflict="provider,model").execute()
