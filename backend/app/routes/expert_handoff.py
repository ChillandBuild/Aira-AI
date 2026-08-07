import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services.ai_reply import send_whatsapp
from app.services.expert_handoff import confirm_expert_handoff_payment, get_session_tenant_id
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()
router = APIRouter()
require_conversations_view = require_permission("conversations.view")


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
        phone, tenant_id, lead_id, customer_name = result
        receipt = (
            f"Payment received, thank you {customer_name}! 🎉\n\n"
            f"Your consultation is confirmed — our expert will be in touch here on WhatsApp shortly."
        )
        try:
            await send_whatsapp(phone, receipt, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Expert handoff receipt send failed for {phone}: {e}")

    return {"status": "ok"}
