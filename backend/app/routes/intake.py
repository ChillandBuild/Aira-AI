import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services.ai_reply import send_whatsapp
from app.services.intake import (
    change_session_package,
    confirm_intake_payment,
    get_intake_config,
    get_session_tenant_id,
    resolve_intake_session,
)
from app.services.intake_csv import FIXED_HEADERS, build_csv_headers, build_csv_row
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()
router = APIRouter()
require_conversations_view = require_permission("conversations.view")
require_conversations_reply = require_permission("conversations.reply")

VISIBLE_STATUSES = ["awaiting_payment", "paid", "resolved"]

SESSION_COLUMNS = (
    "id, lead_id, status, collected_data, field_schema, amount_paise, "
    "amount_mismatch, package_key, package_name, package_amount_paise, "
    "payment_link, paid_at, created_at, leads(name, phone)"
)

CSV_MAX_ROWS = 5000


def _statuses_for(status: str) -> list[str]:
    if status == "all":
        return VISIBLE_STATUSES
    if status in VISIBLE_STATUSES:
        return [status]
    raise HTTPException(
        status_code=400,
        detail=f"status must be 'all' or one of {VISIBLE_STATUSES}",
    )


def _build_query(db, tenant_id: str, status: str, package: str | None, q: str | None, cursor: str | None, limit: int):
    query = (
        db.table("intake_sessions")
        .select(SESSION_COLUMNS)
        .eq("tenant_id", tenant_id)
        .in_("status", _statuses_for(status))
    )
    if package:
        query = query.eq("package_key", package)
    if q:
        # Matches the lead's name or phone. PostgREST needs the embedded-table
        # syntax here because name/phone live on `leads`, not on the session.
        escaped = q.replace(",", "")
        query = query.or_(f"name.ilike.*{escaped}*,phone.ilike.*{escaped}*", foreign_table="leads")
    if cursor:
        parts = cursor.split("|")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Malformed cursor")
        created_at, last_id = parts
        # Keyset, not offset: rows arriving mid-scroll would make offset paging
        # duplicate and skip rows.
        query = query.or_(
            f"created_at.lt.{created_at},and(created_at.eq.{created_at},id.lt.{last_id})"
        )
    return query.order("created_at", desc=True).order("id", desc=True).limit(limit)


@router.get("/sessions")
def list_intake_sessions(
    status: str = Query("all"),
    package: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    ctx: dict = Depends(require_conversations_view),
):
    db = get_supabase()
    result = _build_query(db, ctx["tenant_id"], status, package, q, cursor, limit).execute()
    rows = result.data or []
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = f"{last['created_at']}|{last['id']}"
    return {"data": rows, "next_cursor": next_cursor}


@router.get("/sessions.csv")
def export_intake_sessions_csv(
    status: str = Query("all"),
    package: str | None = Query(None),
    q: str | None = Query(None),
    ctx: dict = Depends(require_conversations_view),
):
    """Honours the active filter and search; ignores the client's column picker,
    which is a viewing preference, not a data one."""
    db = get_supabase()
    result = _build_query(db, ctx["tenant_id"], status, package, q, None, CSV_MAX_ROWS).execute()
    rows = result.data or []
    if len(rows) == CSV_MAX_ROWS:
        logger.warning(
            f"Intake CSV for tenant {ctx['tenant_id']} hit the {CSV_MAX_ROWS}-row cap"
        )

    headers = build_csv_headers(rows)
    field_keys = [key for key, _ in headers]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIXED_HEADERS + [label for _, label in headers])
    for row in rows:
        writer.writerow(build_csv_row(row, field_keys))
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="intake-{status}.csv"'},
    )


@router.patch("/sessions/{session_id}/resolve")
def resolve_session(session_id: str, ctx: dict = Depends(require_conversations_reply)):
    ok = resolve_intake_session(session_id, ctx["tenant_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found or not in 'paid' status")
    return {"status": "resolved"}


class PackageChange(BaseModel):
    package_key: str


@router.patch("/sessions/{session_id}/package")
async def change_package(
    session_id: str,
    payload: PackageChange,
    ctx: dict = Depends(require_conversations_reply),
):
    updated = await change_session_package(session_id, ctx["tenant_id"], payload.package_key)
    if updated is None:
        raise HTTPException(
            status_code=400,
            detail="Session not found, already paid, or unknown package",
        )
    return updated


@public_router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = entity.get("notes", {})
    session_id = notes.get("booking_id")  # payment_razorpay.py's notes key is literally "booking_id"

    if not session_id:
        logger.error("Intake webhook: no session id in notes")
        return {"status": "error", "detail": "no session id"}

    # Signature is verified per-tenant: each tenant configures its own
    # razorpay_webhook_secret, so the tenant must be known before the HMAC
    # check runs (see get_session_tenant_id's docstring for why this lookup
    # is safe to do before the payload is trusted).
    tenant_id = get_session_tenant_id(session_id)
    if not tenant_id:
        logger.warning(f"Intake webhook: unknown session id {session_id}")
        raise HTTPException(status_code=400, detail="Unknown session")

    if not verify_webhook_signature(raw_body, signature, tenant_id=tenant_id):
        logger.warning(f"Intake Razorpay webhook: invalid signature for tenant {tenant_id}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = payload.get("event", "")
    if event != "payment_link.paid":
        return {"status": "ignored", "event": event}

    razorpay_payment_id = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
    )
    amount_paid_paise = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("amount")
    )

    result = confirm_intake_payment(session_id, razorpay_payment_id, amount_paid_paise=amount_paid_paise)
    if result:
        phone, tenant_id, lead_id, customer_name = result
        service_noun = get_intake_config(tenant_id)["service_noun"]
        receipt = (
            f"Payment received, thank you {customer_name}! 🎉\n\n"
            f"Your {service_noun} is confirmed — our expert will be in touch here on WhatsApp shortly."
        )
        try:
            await send_whatsapp(phone, receipt, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Intake receipt send failed for {phone}: {e}")

    return {"status": "ok"}
