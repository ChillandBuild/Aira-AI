import logging
from datetime import datetime, timezone

from app.db.supabase import get_supabase
from app.services.payment_razorpay import create_payment_link

logger = logging.getLogger(__name__)


def _rupees(amount_paise: int) -> str:
    """Same convention as intake.py's _rupees -- whole rupees when exact,
    two decimals otherwise. Not imported from intake.py to avoid a cross-
    module dependency between two independent payment flows; kept identical
    on purpose, see test_quotes.py's parity check against intake._rupees."""
    if amount_paise % 100 == 0:
        return f"₹{amount_paise // 100}"
    return f"₹{amount_paise / 100:.2f}"


def quote_summary_block(items: list[dict], total_paise: int) -> str:
    """Rendered in Python, never by the LLM -- same discipline as
    intake.package_list_block: these are prices the customer will be held
    to, and a hallucinated figure is a real liability."""
    lines = [f"• {item['name']} x{item['qty']} — {_rupees(item['price_paise'] * item['qty'])}" for item in items]
    lines.append(f"Total: {_rupees(total_paise)}")
    return "\n".join(lines)


async def create_quote(
    tenant_id: str,
    lead_id: str,
    line_items: list[dict],
    customer_name: str,
    customer_phone: str,
    db=None,
) -> dict | None:
    """Creates a quote row and its payment link. line_items is
    [{catalog_item_id, name, price_paise, qty}, ...] -- prices must already
    be resolved from the real catalog_items rows by the caller (the
    send_quote tool handler in ai_reply.py reads them from items_by_id,
    which _build_catalog_context populated from the database, never from
    what the model said). Returns {quote_id, summary_text, payment_link} or
    None if every line was unusable (e.g. no priced items survived stock
    filtering)."""
    db = db or get_supabase()

    usable = [li for li in line_items if li.get("price_paise") is not None and li.get("qty", 1) > 0]
    if not usable:
        return None

    items_snapshot = [
        {
            "catalog_item_id": li.get("catalog_item_id"),
            "name": li["name"],
            "price_paise": li["price_paise"],
            "qty": li.get("qty", 1),
        }
        for li in usable
    ]
    total_paise = sum(item["price_paise"] * item["qty"] for item in items_snapshot)

    inserted = (
        db.table("quotes")
        .insert({
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "items": items_snapshot,
            "total_paise": total_paise,
            "status": "sent",
        })
        .execute()
    )
    quote_id = inserted.data[0]["id"]

    description = ", ".join(item["name"] for item in items_snapshot)[:250]
    try:
        link = await create_payment_link(
            idempotency_key=f"quote:{quote_id}:payment_link",
            notes={"quote_id": quote_id},
            amount_paise=total_paise,
            customer_name=customer_name,
            customer_phone=customer_phone,
            description=f"Quote — {description}",
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.warning(f"create_payment_link failed for quote {quote_id}: {e}")
        return None

    db.table("quotes").update({
        "payment_link": link["payment_link_url"],
        "razorpay_payment_link_id": link["razorpay_payment_link_id"],
    }).eq("id", quote_id).eq("tenant_id", tenant_id).execute()

    summary_text = quote_summary_block(items_snapshot, total_paise) + f"\n\nPay here: {link['payment_link_url']}"
    return {"quote_id": quote_id, "summary_text": summary_text, "payment_link": link["payment_link_url"]}


def get_quote_tenant_id(quote_id: str, db=None) -> str | None:
    """Look up which tenant owns a quote, so the webhook route can verify the
    Razorpay signature against that tenant's own secret. Same reasoning as
    intake.get_session_tenant_id: safe to call before the signature is
    verified -- a forged quote_id just gets a lookup miss or another
    tenant's id, and the HMAC check against that tenant's real secret still
    fails without it."""
    db = db or get_supabase()
    result = db.table("quotes").select("tenant_id").eq("id", quote_id).maybe_single().execute()
    if not result or not result.data:
        return None
    return result.data["tenant_id"]


def confirm_quote_payment(quote_id: str, razorpay_payment_id: str, db=None) -> dict | None:
    """Marks a quote paid and deducts stock for each line item that has a
    catalog_item_id -- a paid quote is a CONFIRMED sale, unlike an AI
    catalog quote (interest, not a sale, never deducts). Insufficient/
    untracked stock does not fail the payment confirmation -- the money is
    real regardless of what the stock ledger says; see decrement_stock's own
    docstring for the same reasoning applied to a manual sale.

    The UPDATE's .neq("status", "paid") is the whole point, not a style
    choice: same pattern as intake.confirm_intake_payment, so that of two
    concurrent Razorpay retries for the same payment, exactly one claims the
    row (gets it back in claimed.data) and the other is a no-op -- without
    it, both would deduct stock and send a receipt.

    Returns {tenant_id, lead_id, payment_link} for the caller to send a
    receipt, or None if the quote is unknown or already paid."""
    db = db or get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    claimed = (
        db.table("quotes")
        .update({
            "status": "paid",
            "paid_at": now_iso,
            "razorpay_payment_id": razorpay_payment_id,
        })
        .eq("id", quote_id)
        .neq("status", "paid")
        .execute()
    )
    if not claimed.data:
        logger.info(f"confirm_quote_payment: quote {quote_id} unknown or already paid, ignoring")
        return None
    row = claimed.data[0]

    from app.services.catalog_stock import decrement_stock
    for item in row.get("items") or []:
        if not item.get("catalog_item_id"):
            continue
        try:
            deducted = decrement_stock(row["tenant_id"], item["catalog_item_id"], item.get("qty", 1), db=db)
            if not deducted:
                logger.warning(
                    f"Quote {quote_id} paid but stock not deducted for item {item['catalog_item_id']} "
                    "(insufficient or untracked) -- check inventory manually"
                )
        except Exception as e:
            logger.warning(f"decrement_stock failed for quote {quote_id}, item {item.get('catalog_item_id')}: {e}")

    return {"tenant_id": row["tenant_id"], "lead_id": row["lead_id"], "payment_link": row.get("payment_link")}
