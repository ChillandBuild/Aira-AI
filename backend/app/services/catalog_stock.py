import logging

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def decrement_stock(tenant_id: str, catalog_item_id: str, qty: int, db=None) -> bool:
    """Race-safe stock deduction for a CONFIRMED sale only -- a paid quote or
    a manually-logged sale, never an AI catalog quote (that's interest, not a
    sale). Uses decrement_catalog_stock() (195_catalog_stock.sql), whose WHERE
    clause guards against two simultaneous sales of the last unit both
    succeeding: the losing caller's UPDATE matches zero rows.

    Returns True if stock was decremented, False if there wasn't enough (or
    the item doesn't track stock at all -- NULL never matches the RPC's
    `stock_quantity is not null` guard). Callers must treat False as "could
    not confirm the sale reduced stock" and decide their own next step
    (typically: still record the sale, but flag it for the owner to check)."""
    db = db or get_supabase()
    result = db.rpc(
        "decrement_catalog_stock",
        {"p_item_id": catalog_item_id, "p_tenant_id": tenant_id, "p_qty": qty},
    ).execute()
    return bool(result.data)
