import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.ai_reply import send_whatsapp
from app.services.expert_handoff import confirm_expert_handoff_payment
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()


@public_router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    if not verify_webhook_signature(raw_body, signature):
        logger.warning("Expert handoff Razorpay webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event", "")
    if event != "payment_link.paid":
        return {"status": "ignored", "event": event}

    entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = entity.get("notes", {})
    session_id = notes.get("booking_id")  # payment_razorpay.py's notes key is literally "booking_id"
    razorpay_payment_id = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
    )

    if not session_id:
        logger.error("Expert handoff webhook: no session id in notes")
        return {"status": "error", "detail": "no session id"}

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
