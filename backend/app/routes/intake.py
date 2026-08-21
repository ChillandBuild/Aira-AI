import csv
import io
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services import astro_bridge
from app.services.ai_reply import send_whatsapp
from app.services.intake import (
    alert_bridge_auth_failure,
    change_session_package,
    confirm_intake_payment,
    deliver_astro_reply,
    get_intake_config,
    get_session_tenant_id,
    record_astro_bridge_ids,
    resolve_intake_session,
)
from app.services.intake_copy import compose_payment_receipt
from app.services.intake_csv import FIXED_HEADERS, build_csv_headers, build_csv_row
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()
router = APIRouter()
require_conversations_view = require_permission("conversations.view")
require_conversations_reply = require_permission("conversations.reply")

VISIBLE_STATUSES = ["awaiting_payment", "paid"]

SESSION_COLUMNS = (
    "id, lead_id, status, collected_data, field_schema, amount_paise, "
    "amount_mismatch, package_key, package_name, package_amount_paise, "
    "payment_link, paid_at, created_at, leads(name, phone)"
)

CSV_MAX_ROWS = 5000

# Both q and cursor are interpolated into PostgREST filter-string syntax
# (or_()), not bound as query parameters, so they're validated against a
# strict allowlist before use rather than merely escaped — a value containing
# PostgREST operators/commas/parens could otherwise reshape the filter.
_SEARCH_QUERY_RE = re.compile(r"^[\w \-+@.]{1,64}$", re.UNICODE)
_CURSOR_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")
_CURSOR_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


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
        if not _SEARCH_QUERY_RE.match(q):
            raise HTTPException(status_code=400, detail="Invalid search query")
        query = query.or_(f"name.ilike.*{q}*,phone.ilike.*{q}*", foreign_table="leads")
    if cursor:
        parts = cursor.split("|")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Malformed cursor")
        created_at, last_id = parts
        if not _CURSOR_TIMESTAMP_RE.match(created_at) or not _CURSOR_ID_RE.match(last_id):
            raise HTTPException(status_code=400, detail="Malformed cursor")
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

    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="intake-{status}.csv"'},
    )


@router.get("/stats")
def intake_stats(ctx: dict = Depends(require_conversations_view)):
    """Intake dashboard: message totals, answer progress and a 14-day trend for
    this tenant. "Answered" means the astrologer's reply came back over the
    bridge (astro_last_reply_id is set); "pending" is paid but not yet answered.
    Mirrors the astrobackmatrimony adminweb "Aira Customers" stats so both teams
    read the same numbers."""
    db = get_supabase()
    rows = (
        db.table("intake_sessions")
        .select("status, amount_paise, paid_at, created_at, astro_last_reply_id")
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    ).data or []

    consultations = [r for r in rows if r.get("status") in ("paid", "resolved")]
    answered = sum(1 for r in consultations if r.get("astro_last_reply_id") is not None)
    revenue_paise = sum(int(r.get("amount_paise") or 0) for r in consultations)

    today = datetime.now(timezone.utc).date()
    per_day = {(today - timedelta(days=i)).isoformat(): 0 for i in range(13, -1, -1)}
    for r in consultations:
        stamp = str(r.get("paid_at") or r.get("created_at") or "")[:10]
        if stamp in per_day:
            per_day[stamp] += 1

    revenue_inr = revenue_paise / 100
    return {
        "totals": {
            "messages": len(consultations),
            "answered": answered,
            "pending": len(consultations) - answered,
            "awaiting_payment": sum(1 for r in rows if r.get("status") == "awaiting_payment"),
            "revenue_inr": int(revenue_inr) if revenue_inr.is_integer() else revenue_inr,
        },
        "daily": [{"date": d, "count": n} for d, n in sorted(per_day.items())],
    }


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
        phone = result["phone"]
        tenant_id = result["tenant_id"]
        lead_id = result["lead_id"]
        customer_name = result["customer_name"]

        # Best-effort: a bridge outage must not block the receipt or the paid
        # transition. The astro-push-reconcile job re-drives whatever fails here.
        try:
            pushed = await astro_bridge.push_consultation(result["session"], result["lead"], tenant_id)
            if pushed:
                record_astro_bridge_ids(session_id, tenant_id, pushed)
        except Exception as e:
            logger.error(f"Astro bridge consultation push failed for session {session_id}: {e}")

        service_noun = get_intake_config(tenant_id)["service_noun"]
        receipt = await compose_payment_receipt(
            lead_id=lead_id, tenant_id=tenant_id, customer_name=customer_name, service_noun=service_noun,
        )
        try:
            await send_whatsapp(phone, receipt, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Intake receipt send failed for {phone}: {e}")

    return {"status": "ok"}


def _astro_unauthorized() -> JSONResponse:
    # Same body for an unknown external_ref as for a bad signature: a partner that
    # can't sign must not be able to probe which session ids exist.
    return JSONResponse(status_code=401, content={"error": "Unauthorized", "code": "unauthorized"})


@public_router.post("/astro-reply")
async def astro_reply(request: Request):
    """The astrologer's answer, called by the astrobackmatrimony Django app.
    Signed with HMAC-SHA256 over the raw body using this tenant's
    astro_bridge_secret. Wire contract — see ConsultationAPIEndpoints.md."""
    raw_body = await request.body()
    signature = request.headers.get("x-astro-signature", "")

    try:
        payload = await request.json()
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "Invalid JSON", "code": "invalid_json"})

    external_ref = str(payload.get("external_ref") or "")
    tenant_id = get_session_tenant_id(external_ref) if external_ref else None
    if not tenant_id:
        logger.warning(f"Astro reply callback: unknown external_ref {external_ref!r}")
        return _astro_unauthorized()

    secret = astro_bridge.get_bridge_secret(tenant_id)
    if not astro_bridge.verify_astro_signature(raw_body, signature, secret):
        # The ref resolved to a real session, so this is the expert platform
        # calling with a mismatched secret — not a probe. Nothing else surfaces
        # this: they see "sent", the customer hears nothing. Tell staff.
        logger.warning(f"Astro reply callback: invalid signature for tenant {tenant_id}")
        alert_bridge_auth_failure(tenant_id, external_ref)
        return _astro_unauthorized()

    return await deliver_astro_reply(payload, tenant_id)
