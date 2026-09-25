"""Deals: one row per sale attempt, every source (see
docs/superpowers/specs/2026-09-25-deals-crm-design.md). All stage and stock
rules live in services/deals.py; this module only validates input, scopes by
tenant and shapes responses."""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services import deals as deals_service
from app.services import deals_reports
from app.services.deals import DealError, format_deal_number

logger = logging.getLogger(__name__)
router = APIRouter()
require_deals_view = require_permission("leads.view")
require_deals_manage = require_permission("leads.manage")

DEAL_SELECT = "*, leads(id, name, phone), deal_items(id, catalog_item_id, name, qty, unit_price_paise, gst_rate, line_total_paise)"
BOARD_CARD_CAP = 100
BOARD_RECENT_DAYS = 30
DEAL_NUMBER_RE = re.compile(r"^(?:d-?)?0*(\d+)$", re.IGNORECASE)


def _summary(row: dict) -> dict:
    items = row.get("deal_items") or []
    lead = row.get("leads") or {}
    return {
        "id": row["id"],
        "deal_number": row["deal_number"],
        "deal_label": format_deal_number(row["deal_number"]),
        "stage": row["stage"],
        "source": row["source"],
        "total_paise": row["total_paise"],
        "payment_method": row.get("payment_method"),
        "payment_link": row.get("payment_link"),
        "created_at": row["created_at"],
        "won_at": row.get("won_at"),
        "lost_at": row.get("lost_at"),
        "lost_reason": row.get("lost_reason"),
        "lead": {"id": row["lead_id"], "name": lead.get("name"), "phone": lead.get("phone")},
        "item_summary": ", ".join(f"{i['name']} ×{i['qty']}" for i in items),
        "item_count": len(items),
    }


def _full(row: dict, db, tenant_id: str) -> dict:
    intake_answers = None
    if row.get("intake_session_id"):
        session = (
            db.table("intake_sessions").select("collected_data")
            .eq("id", row["intake_session_id"]).eq("tenant_id", tenant_id).maybe_single().execute()
        )
        intake_answers = (session.data or {}).get("collected_data") if session else None
    return {
        **_summary(row),
        "items": row.get("deal_items") or [],
        "notes": row.get("notes"),
        "link_expires_at": row.get("link_expires_at"),
        "razorpay_payment_id": row.get("razorpay_payment_id"),
        "intake_session_id": row.get("intake_session_id"),
        "intake_answers": intake_answers,
    }


def _load_deal(db, tenant_id: str, deal_id: str) -> dict:
    res = db.table("deals").select(DEAL_SELECT).eq("id", deal_id).eq("tenant_id", tenant_id).maybe_single().execute()
    if not res or not res.data:
        raise HTTPException(status_code=404, detail="Deal not found")
    return res.data


def _lead_ids_matching(db, tenant_id: str, q: str) -> list[str]:
    # PostgREST or() filter: strip the characters that would break its syntax.
    safe = re.sub(r"[,()*%]", "", q)[:60]
    if not safe:
        return []
    rows = (
        db.table("leads").select("id").eq("tenant_id", tenant_id)
        .or_(f"name.ilike.%{safe}%,phone.ilike.%{safe}%").limit(200).execute()
    ).data or []
    return [r["id"] for r in rows]


@router.get("/board")
def deals_board(ctx: dict = Depends(require_deals_view)):
    """Four stage columns. Won/Lost only show the last 30 days so the board is
    about what's moving now; the List tab and export hold the full history."""
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    since = (datetime.now(timezone.utc) - timedelta(days=BOARD_RECENT_DAYS)).isoformat()
    columns = {}
    for stage in deals_service.STAGES:
        base = db.table("deals").select(DEAL_SELECT).eq("tenant_id", tenant_id).eq("stage", stage)
        totals = db.table("deals").select("total_paise").eq("tenant_id", tenant_id).eq("stage", stage)
        if stage == "won":
            base, totals = base.gte("won_at", since), totals.gte("won_at", since)
        elif stage == "lost":
            base, totals = base.gte("lost_at", since), totals.gte("lost_at", since)
        cards = base.order("created_at", desc=True).limit(BOARD_CARD_CAP + 1).execute().data or []
        amounts = totals.limit(5000).execute().data or []
        columns[stage] = {
            "count": len(amounts),
            "total_paise": sum(r["total_paise"] for r in amounts),
            "deals": [_summary(r) for r in cards[:BOARD_CARD_CAP]],
            "has_more": len(cards) > BOARD_CARD_CAP,
        }
    return {"columns": columns}


@router.get("")
def list_deals(
    stage: str | None = None,
    source: str | None = None,
    q: str | None = None,
    month: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    ctx: dict = Depends(require_deals_view),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    query = db.table("deals").select(DEAL_SELECT).eq("tenant_id", tenant_id)
    if stage:
        if stage not in deals_service.STAGES:
            raise HTTPException(status_code=400, detail="Unknown stage")
        query = query.eq("stage", stage)
    if source:
        if source not in deals_service.SOURCES:
            raise HTTPException(status_code=400, detail="Unknown source")
        query = query.eq("source", source)
    if month:
        start, end = deals_reports.month_bounds(month)
        query = query.gte("created_at", start).lt("created_at", end)
    if q and q.strip():
        number = DEAL_NUMBER_RE.match(q.strip())
        if number:
            query = query.eq("deal_number", int(number.group(1)))
        else:
            lead_ids = _lead_ids_matching(db, tenant_id, q.strip())
            if not lead_ids:
                return {"data": [], "next_cursor": None}
            query = query.in_("lead_id", lead_ids)
    if cursor:
        query = query.lt("created_at", cursor)
    rows = query.order("created_at", desc=True).limit(limit + 1).execute().data or []
    page = rows[:limit]
    return {
        "data": [_summary(r) for r in page],
        "next_cursor": page[-1]["created_at"] if len(rows) > limit else None,
    }


@router.get("/stats")
def deal_stats(month: str, ctx: dict = Depends(require_deals_view)):
    return deals_reports.monthly_stats(ctx["tenant_id"], month)


@router.get("/export")
def export_deals(
    month: str,
    format: Literal["xlsx", "csv"] = "xlsx",
    ctx: dict = Depends(require_deals_view),
):
    content, media_type, filename = deals_reports.sales_register(ctx["tenant_id"], month, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/by-lead/{lead_id}")
def deals_for_lead(lead_id: str, ctx: dict = Depends(require_deals_view)):
    db = get_supabase()
    rows = (
        db.table("deals").select(DEAL_SELECT).eq("tenant_id", ctx["tenant_id"]).eq("lead_id", lead_id)
        .order("created_at", desc=True).limit(50).execute()
    ).data or []
    return {"data": [_summary(r) for r in rows]}


@router.get("/{deal_id}")
def get_deal(deal_id: str, ctx: dict = Depends(require_deals_view)):
    db = get_supabase()
    return _full(_load_deal(db, ctx["tenant_id"], deal_id), db, ctx["tenant_id"])


class DealLineIn(BaseModel):
    catalog_item_id: str | None = None
    name: str = Field("", max_length=200)
    qty: int = Field(1, ge=1, le=100000)
    unit_price_paise: int | None = Field(None, ge=0)


class NewDealIn(BaseModel):
    lead_id: str | None = None
    phone: str | None = Field(None, max_length=32)
    name: str | None = Field(None, max_length=120)
    items: list[DealLineIn] = Field(..., min_length=1, max_length=50)
    source: Literal["call", "walk_in", "manual"]
    stage: Literal["won", "awaiting_payment", "quoted"]
    payment_method: Literal["razorpay", "cash", "upi", "card", "bank_transfer", "other"] | None = None
    notes: str | None = Field(None, max_length=2000)


def _resolve_lead(db, tenant_id: str, payload: NewDealIn) -> str:
    if bool(payload.lead_id) == bool(payload.phone):
        raise HTTPException(status_code=400, detail="Give either an existing contact or a phone number")
    if payload.lead_id:
        lead = db.table("leads").select("id").eq("id", payload.lead_id).eq("tenant_id", tenant_id).maybe_single().execute()
        if not lead or not lead.data:
            raise HTTPException(status_code=404, detail="Contact not found")
        return payload.lead_id
    from app.services.inbound_lead import create_inbound_lead
    lead_id = create_inbound_lead(
        tenant_id, payload.phone, "manual", name=(payload.name or "").strip() or None,
        opt_in_source="manual", db=db,
    )
    if not lead_id:
        raise HTTPException(status_code=400, detail="That phone number doesn't look valid")
    return lead_id


@router.post("")
async def create_deal(payload: NewDealIn, ctx: dict = Depends(require_deals_manage)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    lead_id = _resolve_lead(db, tenant_id, payload)
    try:
        result = await deals_service.create_deal(
            tenant_id, lead_id, [li.model_dump() for li in payload.items], payload.source, payload.stage,
            payment_method=payload.payment_method, notes=payload.notes, created_by=ctx.get("user_id"),
            send_link=payload.stage == "awaiting_payment", db=db,
        )
    except DealError as e:
        raise HTTPException(status_code=400, detail=str(e))
    deal = _full(_load_deal(db, tenant_id, result["deal"]["id"]), db, tenant_id)
    return {
        "deal": deal,
        "payment_link": result["payment_link"],
        "message_sent": result["message_sent"],
        "stock_warnings": result["stock_warnings"],
    }


class StageIn(BaseModel):
    stage: Literal["won", "lost"]
    payment_method: Literal["razorpay", "cash", "upi", "card", "bank_transfer", "other"] | None = None
    lost_reason: str | None = Field(None, max_length=300)


@router.patch("/{deal_id}/stage")
def update_stage(deal_id: str, payload: StageIn, ctx: dict = Depends(require_deals_manage)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    _load_deal(db, tenant_id, deal_id)
    if payload.stage == "won":
        result = deals_service.mark_won(
            tenant_id, deal_id, payment_method=payload.payment_method or "cash",
            created_by=ctx.get("user_id"), db=db,
        )
    else:
        result = deals_service.mark_lost(
            tenant_id, deal_id, payload.lost_reason or "Marked lost", created_by=ctx.get("user_id"), db=db,
        )
    if result is None:
        raise HTTPException(status_code=409, detail=f"Deal is already {payload.stage}")
    return {"deal": _full(_load_deal(db, tenant_id, deal_id), db, tenant_id), "stock_warnings": result["stock_warnings"]}


@router.post("/{deal_id}/send-link")
async def send_link(deal_id: str, ctx: dict = Depends(require_deals_manage)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    _load_deal(db, tenant_id, deal_id)
    try:
        result = await deals_service.send_payment_link(tenant_id, deal_id, db=db)
    except DealError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"payment_link": result["payment_link"], "message_sent": result["message_sent"]}
