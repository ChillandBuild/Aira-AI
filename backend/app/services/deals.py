"""Deals: one row per sale attempt, from every source (AI chat, intake form,
call, walk-in, manual, marketplaces). See
docs/superpowers/specs/2026-09-25-deals-crm-design.md and 204_deals.sql.

This module is the ONLY place that moves a deal between stages or touches
stock, so the rules live in one spot:
  - stock deducts on WON only, and a won deal later marked lost returns it;
  - prices are snapshotted onto deal_items when written, never re-read live;
  - a stock problem never fails a sale -- the money is real regardless of what
    the ledger says, so callers get stock_warnings instead of an error.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

STAGES = ("quoted", "awaiting_payment", "won", "lost")
SOURCES = ("whatsapp", "form", "call", "walk_in", "manual", "indiamart", "justdial")
PAYMENT_METHODS = ("razorpay", "cash", "upi", "card", "bank_transfer", "other")
# Matches payment_razorpay's link expiry, so link_expires_at is what the
# customer actually sees.
LINK_TTL = timedelta(hours=24)
LOW_STOCK_THRESHOLD = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_deal_number(db, tenant_id: str) -> int:
    """next_deal_number returns a scalar; PostgREST may hand it back bare or
    wrapped in a list/row depending on client version -- accept all three."""
    data = db.rpc("next_deal_number", {"p_tenant_id": tenant_id}).execute().data
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict):
        data = next(iter(data.values()), None)
    if data is None:
        raise DealError("Couldn't allocate a deal number")
    return int(data)


def format_deal_number(n: int) -> str:
    return f"D-{n:04d}"


def _rupees(amount_paise: int) -> str:
    """Same convention as intake._rupees: whole rupees when exact."""
    if amount_paise % 100 == 0:
        return f"₹{amount_paise // 100:,}"
    return f"₹{amount_paise / 100:,.2f}"


def quote_summary_block(lines: list[dict], total_paise: int) -> str:
    """Rendered in Python, never by the LLM: these are prices the customer
    will be held to, and a hallucinated figure is a real liability."""
    rows = [f"• {li['name']} x{li['qty']} — {_rupees(li['line_total_paise'])}" for li in lines]
    rows.append(f"Total: {_rupees(total_paise)}")
    return "\n".join(rows)


def get_deal_tenant_id(deal_id: str, db=None) -> str | None:
    """Which tenant owns a deal, so the Razorpay webhook can verify the
    signature against that tenant's secret. Safe before the payload is
    trusted: a forged id is a miss or another tenant's id, and the HMAC check
    against that tenant's real secret still fails."""
    db = db or get_supabase()
    res = db.table("deals").select("tenant_id").eq("id", deal_id).maybe_single().execute()
    if not res or not res.data:
        return None
    return res.data["tenant_id"]


# ---------------------------------------------------------------- stock

def adjust_stock(
    tenant_id: str,
    item_id: str,
    delta: int,
    reason: str,
    *,
    note: str | None = None,
    created_by: str | None = None,
    deal_id: str | None = None,
    db=None,
) -> dict:
    """Thin wrapper over apply_stock_movement (204_deals.sql), which changes the
    count and logs the movement in one statement."""
    db = db or get_supabase()
    res = db.rpc(
        "apply_stock_movement",
        {
            "p_tenant_id": tenant_id,
            "p_item_id": item_id,
            "p_delta": delta,
            "p_reason": reason,
            "p_deal_id": deal_id,
            "p_note": note,
            "p_created_by": created_by,
        },
    ).execute()
    row = (res.data or [{}])[0] if isinstance(res.data, list) else (res.data or {})
    return {
        "ok": bool(row.get("ok")),
        "tracked": bool(row.get("tracked")),
        "quantity_after": row.get("quantity_after"),
    }


def held_quantities(tenant_id: str, item_ids: list[str], db=None) -> dict[str, int]:
    """Units promised to customers who have a payment link but haven't paid:
    sum of qty on awaiting_payment deals. Computed, never stored, so it can't
    drift when a link expires or is paid. One inner-joined query filtered in
    Python -- passing deal or item id lists would blow the URL length limit
    for a busy tenant."""
    if not item_ids:
        return {}
    db = db or get_supabase()
    wanted = set(item_ids)
    rows = (
        db.table("deal_items")
        .select("catalog_item_id, qty, deals!inner(stage)")
        .eq("tenant_id", tenant_id)
        .eq("deals.stage", "awaiting_payment")
        .limit(5000)
        .execute()
    ).data or []
    held: dict[str, int] = {}
    for r in rows:
        item_id = r.get("catalog_item_id")
        if item_id in wanted:
            held[item_id] = held.get(item_id, 0) + (r.get("qty") or 0)
    return held


def _deduct_for_deal(tenant_id: str, deal_id: str, created_by: str | None, db, *, direction: int) -> list[dict]:
    """direction=-1 sells (reason 'sale'), +1 returns (reason 'return').
    Returns warnings for lines whose stock couldn't be moved."""
    items = (
        db.table("deal_items")
        .select("catalog_item_id, name, qty")
        .eq("deal_id", deal_id)
        .eq("tenant_id", tenant_id)
        .execute()
    ).data or []
    warnings: list[dict] = []
    reason = "sale" if direction < 0 else "return"
    for item in items:
        if not item.get("catalog_item_id"):
            continue
        try:
            result = adjust_stock(
                tenant_id, item["catalog_item_id"], direction * item["qty"], reason,
                deal_id=deal_id, created_by=created_by, db=db,
            )
            if not result["ok"]:
                warnings.append({
                    "catalog_item_id": item["catalog_item_id"],
                    "name": item["name"],
                    "available": result["quantity_after"],
                })
        except Exception as e:
            logger.warning(f"Stock {reason} failed for deal {deal_id}, item {item['catalog_item_id']}: {e}")
            warnings.append({"catalog_item_id": item["catalog_item_id"], "name": item["name"], "available": None})
    return warnings


# ---------------------------------------------------------------- lines

class DealError(ValueError):
    """A caller mistake (unknown item, missing price) -- routes turn it into a 400."""


def _resolve_lines(tenant_id: str, lines: list[dict], db) -> list[dict]:
    """Fill missing price / GST from the real catalog row (tenant-scoped), so
    a caller -- including the AI tool handler -- can never invent a price."""
    item_ids = [li["catalog_item_id"] for li in lines if li.get("catalog_item_id")]
    catalog: dict[str, dict] = {}
    if item_ids:
        rows = (
            db.table("catalog_items")
            .select("id, name, price_paise, gst_rate")
            .eq("tenant_id", tenant_id)
            .in_("id", item_ids)
            .execute()
        ).data or []
        catalog = {r["id"]: r for r in rows}

    resolved = []
    for li in lines:
        qty = int(li.get("qty") or 1)
        if qty < 1:
            raise DealError("Quantity must be at least 1")
        item_id = li.get("catalog_item_id")
        item = catalog.get(item_id) if item_id else None
        if item_id and not item:
            raise DealError("Product not found")
        name = (li.get("name") or (item or {}).get("name") or "").strip()
        if not name:
            raise DealError("Each line needs a product name")
        price = li.get("unit_price_paise")
        if price is None and item:
            price = item.get("price_paise")
        if price is None:
            raise DealError(f"No price for {name}")
        if price < 0:
            raise DealError("Price must not be negative")
        gst = li.get("gst_rate")
        if gst is None and item:
            gst = item.get("gst_rate")
        resolved.append({
            "catalog_item_id": item_id,
            "name": name,
            "qty": qty,
            "unit_price_paise": int(price),
            "gst_rate": float(gst) if gst is not None else None,
            "line_total_paise": int(price) * qty,
        })
    if not resolved:
        raise DealError("A deal needs at least one item")
    return resolved


def _deal_total(tenant_id: str, lines: list[dict], db) -> int:
    """What the customer pays. When the tenant's prices EXCLUDE GST, the tax is
    added on top here, so the payment link charges the right amount; line
    totals stay pre-tax for the export's taxable-value column."""
    subtotal = sum(li["line_total_paise"] for li in lines)
    from app.services.business_details import prices_include_gst
    if prices_include_gst(tenant_id, db):
        return subtotal
    tax = sum(round(li["line_total_paise"] * li["gst_rate"] / 100) for li in lines if li.get("gst_rate"))
    return subtotal + tax


def _insert_items(tenant_id: str, deal_id: str, lines: list[dict], db) -> list[dict]:
    rows = [{**li, "deal_id": deal_id, "tenant_id": tenant_id} for li in lines]
    return db.table("deal_items").insert(rows).execute().data or []


# ---------------------------------------------------------------- create

async def create_deal(
    tenant_id: str,
    lead_id: str,
    lines: list[dict],
    source: str,
    stage: str = "quoted",
    *,
    payment_method: str | None = None,
    notes: str | None = None,
    created_by: str | None = None,
    intake_session_id: str | None = None,
    send_link: bool = False,
    db=None,
) -> dict:
    """Create a deal with its lines. stage='won' deducts stock now;
    send_link=True creates the Razorpay link and moves it to awaiting_payment
    (and messages the customer on WhatsApp)."""
    db = db or get_supabase()
    if source not in SOURCES:
        raise DealError(f"Unknown source {source}")
    if stage not in STAGES or stage == "lost":
        raise DealError(f"A new deal can't start as {stage}")
    if payment_method and payment_method not in PAYMENT_METHODS:
        raise DealError(f"Unknown payment method {payment_method}")

    resolved = _resolve_lines(tenant_id, lines, db)
    row = {
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "deal_number": _next_deal_number(db, tenant_id),
        "stage": "quoted" if stage == "awaiting_payment" else stage,
        "source": source,
        "total_paise": _deal_total(tenant_id, resolved, db),
        "payment_method": payment_method,
        "notes": notes,
        "created_by": created_by,
        "intake_session_id": intake_session_id,
    }
    if stage == "won":
        row["won_at"] = _now_iso()
        row["payment_method"] = payment_method or "cash"
    deal = db.table("deals").insert(row).execute().data[0]
    items = _insert_items(tenant_id, deal["id"], resolved, db)

    result = {"deal": deal, "items": items, "payment_link": None, "message_sent": False, "stock_warnings": []}
    if stage == "won":
        result["stock_warnings"] = _deduct_for_deal(tenant_id, deal["id"], created_by, db, direction=-1)
    elif stage == "awaiting_payment" or send_link:
        # The AI's send_quote tool passes send_link=False: the link goes out in
        # its own reply text, so a second WhatsApp message would duplicate it.
        link = await send_payment_link(tenant_id, deal["id"], send_whatsapp_message=send_link, db=db)
        result["payment_link"] = link["payment_link"]
        result["message_sent"] = link["message_sent"]
        result["deal"] = {**deal, **link.get("deal_patch", {})}
    return result


# ---------------------------------------------------------------- payment link

def _lead_contact(tenant_id: str, lead_id: str, db) -> dict:
    res = db.table("leads").select("name, phone").eq("id", lead_id).eq("tenant_id", tenant_id).maybe_single().execute()
    return (res.data if res else None) or {}


async def send_payment_link(tenant_id: str, deal_id: str, *, send_whatsapp_message: bool = True, db=None) -> dict:
    """Create the Razorpay link (notes.deal_id routes the webhook back here),
    move the deal to awaiting_payment, and optionally message the customer.
    A freeform WhatsApp send fails outside the 24h window -- that is reported
    as message_sent=False with the link, so staff can share it themselves."""
    db = db or get_supabase()
    deal = (
        db.table("deals").select("*").eq("id", deal_id).eq("tenant_id", tenant_id).maybe_single().execute()
    )
    if not deal or not deal.data:
        raise DealError("Deal not found")
    deal = deal.data
    if deal["stage"] in ("won", "lost"):
        raise DealError(f"Deal is already {deal['stage']}")
    items = (
        db.table("deal_items").select("name, qty, line_total_paise").eq("deal_id", deal_id).eq("tenant_id", tenant_id).execute()
    ).data or []
    contact = _lead_contact(tenant_id, deal["lead_id"], db)
    phone = contact.get("phone") or ""
    customer_name = contact.get("name") or phone

    from app.services.payment_razorpay import create_payment_link
    link = await create_payment_link(
        idempotency_key=f"deal:{deal_id}:payment_link",
        notes={"deal_id": deal_id},
        amount_paise=deal["total_paise"],
        customer_name=customer_name,
        customer_phone=phone,
        description=f"{format_deal_number(deal['deal_number'])} — " + ", ".join(i["name"] for i in items)[:200],
        tenant_id=tenant_id,
    )
    patch = {
        "stage": "awaiting_payment",
        "payment_link": link["payment_link_url"],
        "razorpay_payment_link_id": link.get("razorpay_payment_link_id"),
        "link_expires_at": (datetime.now(timezone.utc) + LINK_TTL).isoformat(),
    }
    db.table("deals").update(patch).eq("id", deal_id).eq("tenant_id", tenant_id).execute()

    message_sent = False
    if send_whatsapp_message and phone:
        text = quote_summary_block(items, deal["total_paise"]) + f"\n\nPay here: {link['payment_link_url']}"
        try:
            from app.services.ai_reply import send_whatsapp
            await send_whatsapp(phone, text, tenant_id=tenant_id)
            message_sent = True
        except Exception as e:
            logger.info(f"Deal {deal_id}: payment link WhatsApp send failed (likely outside 24h window): {e}")
    return {"payment_link": link["payment_link_url"], "message_sent": message_sent, "deal_patch": patch}


# ---------------------------------------------------------------- won / lost

def mark_won(
    tenant_id: str,
    deal_id: str,
    *,
    payment_method: str,
    razorpay_payment_id: str | None = None,
    created_by: str | None = None,
    db=None,
) -> dict | None:
    """The .neq("stage", "won") claim is the whole point: of two concurrent
    Razorpay retries, exactly one gets the row back and deducts stock; the
    other is a no-op. Returns None if unknown or already won."""
    db = db or get_supabase()
    if payment_method not in PAYMENT_METHODS:
        raise DealError(f"Unknown payment method {payment_method}")
    patch = {"stage": "won", "won_at": _now_iso(), "payment_method": payment_method, "lost_at": None, "lost_reason": None}
    if razorpay_payment_id:
        patch["razorpay_payment_id"] = razorpay_payment_id
    claimed = (
        db.table("deals").update(patch).eq("id", deal_id).eq("tenant_id", tenant_id).neq("stage", "won").execute()
    )
    if not claimed.data:
        return None
    warnings = _deduct_for_deal(tenant_id, deal_id, created_by, db, direction=-1)
    return {"deal": claimed.data[0], "stock_warnings": warnings}


def mark_lost(tenant_id: str, deal_id: str, reason: str, *, created_by: str | None = None, db=None) -> dict | None:
    """A won deal marked lost is a refund/cancelled sale: its stock comes back."""
    db = db or get_supabase()
    current = db.table("deals").select("stage").eq("id", deal_id).eq("tenant_id", tenant_id).maybe_single().execute()
    if not current or not current.data or current.data["stage"] == "lost":
        return None
    was_won = current.data["stage"] == "won"
    claimed = (
        db.table("deals")
        .update({"stage": "lost", "lost_at": _now_iso(), "lost_reason": (reason or "").strip() or None})
        .eq("id", deal_id)
        .eq("tenant_id", tenant_id)
        .neq("stage", "lost")
        .execute()
    )
    if not claimed.data:
        return None
    warnings = _deduct_for_deal(tenant_id, deal_id, created_by, db, direction=1) if was_won else []
    return {"deal": claimed.data[0], "stock_warnings": warnings}


# ---------------------------------------------------------------- automatic writers

def upsert_quoted_deal(tenant_id: str, lead_id: str, line: dict, db=None) -> None:
    """The AI told this lead a real catalog price: keep ONE open quoted deal
    per lead (latest item wins) so the board shows the interest without a
    new card per message. Never raises -- it must not break the reply."""
    try:
        db = db or get_supabase()
        resolved = _resolve_lines(tenant_id, [line], db)
        total = _deal_total(tenant_id, resolved, db)
        open_quote = (
            db.table("deals")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .eq("stage", "quoted")
            .eq("source", "whatsapp")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if open_quote:
            deal_id = open_quote[0]["id"]
            db.table("deal_items").delete().eq("deal_id", deal_id).eq("tenant_id", tenant_id).execute()
            _insert_items(tenant_id, deal_id, resolved, db)
            db.table("deals").update({"total_paise": total}).eq("id", deal_id).eq("tenant_id", tenant_id).execute()
            return
        deal = db.table("deals").insert({
            "tenant_id": tenant_id, "lead_id": lead_id, "deal_number": _next_deal_number(db, tenant_id),
            "stage": "quoted", "source": "whatsapp", "total_paise": total,
        }).execute().data[0]
        _insert_items(tenant_id, deal["id"], resolved, db)
    except Exception as e:
        logger.warning(f"upsert_quoted_deal failed for lead {lead_id}: {e}")


def _intake_lines(session: dict) -> list[dict]:
    lines = []
    package_amount = session.get("package_amount_paise")
    if session.get("package_name") and package_amount is not None:
        lines.append({"name": session["package_name"], "qty": 1, "unit_price_paise": package_amount})
    for addon in session.get("selected_addons") or []:
        if addon.get("name") and addon.get("amount_paise") is not None:
            lines.append({"name": addon["name"], "qty": 1, "unit_price_paise": addon["amount_paise"]})
    if not lines:
        amount = session.get("total_amount_paise") or session.get("amount_paise")
        if amount:
            lines.append({"name": session.get("package_name") or "Consultation", "qty": 1, "unit_price_paise": amount})
    return lines


def sync_intake_session(session: dict, db=None) -> None:
    """Mirror the intake (form) flow onto its deal, keyed by intake_session_id.
    The intake state machine stays the source of truth for the conversation;
    this only keeps the Deals board and sales export complete. Never raises."""
    try:
        db = db or get_supabase()
        status = session.get("status")
        if status not in ("awaiting_payment", "paid", "cancelled"):
            return
        tenant_id = session["tenant_id"]
        existing = (
            db.table("deals").select("id, stage").eq("intake_session_id", session["id"]).eq("tenant_id", tenant_id).limit(1).execute()
        ).data or []

        if status == "awaiting_payment":
            lines = _resolve_lines(tenant_id, _intake_lines(session), db) if _intake_lines(session) else []
            if not lines:
                return
            total = session.get("total_amount_paise") or session.get("amount_paise") or sum(li["line_total_paise"] for li in lines)
            fields = {
                "stage": "awaiting_payment", "total_paise": total, "payment_link": session.get("payment_link"),
                "link_expires_at": (datetime.now(timezone.utc) + LINK_TTL).isoformat(),
            }
            if existing:
                deal_id = existing[0]["id"]
                if existing[0]["stage"] == "won":
                    return
                db.table("deals").update({**fields, "lost_at": None, "lost_reason": None}).eq("id", deal_id).eq("tenant_id", tenant_id).execute()
                db.table("deal_items").delete().eq("deal_id", deal_id).eq("tenant_id", tenant_id).execute()
            else:
                deal_id = db.table("deals").insert({
                    **fields, "tenant_id": tenant_id, "lead_id": session["lead_id"],
                    "deal_number": _next_deal_number(db, tenant_id),
                    "source": "form", "intake_session_id": session["id"],
                }).execute().data[0]["id"]
            _insert_items(tenant_id, deal_id, lines, db)
            return

        if not existing:
            return
        deal_id = existing[0]["id"]
        if status == "paid":
            mark_won(tenant_id, deal_id, payment_method="razorpay",
                     razorpay_payment_id=session.get("razorpay_payment_id"), db=db)
        elif status == "cancelled" and existing[0]["stage"] != "won":
            mark_lost(tenant_id, deal_id, "Link expired or cancelled", db=db)
    except Exception as e:
        logger.warning(f"sync_intake_session failed for session {session.get('id')}: {e}")
