import logging

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def record_catalog_quote(
    tenant_id: str,
    lead_id: str,
    catalog_item_id: str | None,
    item_name: str,
    amount_paise: int,
    *,
    amount_is_estimate: bool = True,
    db=None,
) -> None:
    """Visibility only, not a pipeline stage: the AI just told this lead a
    real catalog price, so it shows up on the intake Pipeline board. One row
    per lead -- a later quote on the same lead replaces it (latest item and
    amount win) rather than piling up duplicates. No stage, no "won" tracking:
    see 194_catalog_prices_and_deals.sql for why that's out of scope here.

    Never allowed to break the reply that triggered it -- callers must wrap
    this the same way maybe_assign_lead's failures are swallowed."""
    db = db or get_supabase()
    db.table("catalog_quotes").upsert(
        {
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "catalog_item_id": catalog_item_id,
            "item_name": item_name,
            "amount_paise": amount_paise,
            "amount_is_estimate": amount_is_estimate,
        },
        on_conflict="lead_id",
    ).execute()
