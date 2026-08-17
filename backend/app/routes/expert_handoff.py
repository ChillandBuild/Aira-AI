import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services import astro_bridge
from app.services.ai_reply import send_whatsapp
from app.services.expert_handoff import (
    confirm_expert_handoff_payment,
    deliver_astro_reply,
    get_session_tenant_id,
    record_astro_bridge_ids,
    resolve_expert_handoff_session,
)
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()
router = APIRouter()
require_conversations_view = require_permission("conversations.view")
require_conversations_reply = require_permission("conversations.reply")


@router.get("/sessions")
def list_expert_handoff_sessions(
    bucket: str = Query(...),
    ctx: dict = Depends(require_conversations_view),
):
    if bucket not in ("awaiting_payment", "paid"):
        raise HTTPException(status_code=400, detail="bucket must be 'awaiting_payment' or 'paid'")

    db = get_supabase()
    result = (
        db.table("expert_handoff_sessions")
        .select("id, lead_id, status, collected_data, amount_paise, payment_link, paid_at, created_at, leads(name, phone)")
        .eq("tenant_id", ctx["tenant_id"])
        .eq("status", bucket)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"data": result.data or []}


@router.patch("/sessions/{session_id}/resolve")
def resolve_session(session_id: str, ctx: dict = Depends(require_conversations_reply)):
    ok = resolve_expert_handoff_session(session_id, ctx["tenant_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found or not in 'paid' status")
    return {"status": "resolved"}


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
        logger.error("Expert handoff webhook: no session id in notes")
        return {"status": "error", "detail": "no session id"}

    # Signature is verified per-tenant: each tenant configures its own
    # razorpay_webhook_secret, so the tenant must be known before the HMAC
    # check runs (see get_session_tenant_id's docstring for why this lookup
    # is safe to do before the payload is trusted).
    tenant_id = get_session_tenant_id(session_id)
    if not tenant_id:
        logger.warning(f"Expert handoff webhook: unknown session id {session_id}")
        raise HTTPException(status_code=400, detail="Unknown session")

    if not verify_webhook_signature(raw_body, signature, tenant_id=tenant_id):
        logger.warning(f"Expert handoff Razorpay webhook: invalid signature for tenant {tenant_id}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = payload.get("event", "")
    if event != "payment_link.paid":
        return {"status": "ignored", "event": event}

    razorpay_payment_id = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
    )

    result = confirm_expert_handoff_payment(session_id, razorpay_payment_id)
    if result:
        try:
            pushed = await astro_bridge.push_consultation(
                result["session"], result["lead"], result["tenant_id"]
            )
            if pushed:
                record_astro_bridge_ids(session_id, result["tenant_id"], pushed)
        except Exception as e:
            logger.error(f"Astro bridge consultation push failed for session {session_id}: {e}")

        customer_name = result["customer_name"]
        receipt = (
            f"Payment received, thank you {customer_name}! 🎉\n\n"
            f"Your consultation is confirmed — our expert will be in touch here on WhatsApp shortly."
        )
        try:
            await send_whatsapp(result["phone"], receipt, tenant_id=result["tenant_id"])
        except Exception as e:
            logger.error(f"Expert handoff receipt send failed for {result['phone']}: {e}")

    return {"status": "ok"}


def _astro_unauthorized() -> JSONResponse:
    # Same body for an unknown external_ref as for a bad signature: a partner that
    # can't sign must not be able to probe which session ids exist.
    return JSONResponse(status_code=401, content={"error": "Unauthorized", "code": "unauthorized"})


@public_router.post("/astro-reply")
async def astro_reply(request: Request):
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
        logger.warning(f"Astro reply callback: invalid signature for tenant {tenant_id}")
        return _astro_unauthorized()

    return await deliver_astro_reply(payload, tenant_id)
