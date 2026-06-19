import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id
from app.services.booking_flow import confirm_booking
from app.services.payment_razorpay import verify_webhook_signature
from app.services.ai_reply import send_whatsapp

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()


@router.get("")
async def list_bookings(
    status: str | None = None,
    page: int = 1,
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
):
    db = get_supabase()
    query = (
        db.table("bookings")
        .select("*, leads(name, phone)")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .range((page - 1) * limit, page * limit - 1)
    )
    if status:
        query = query.eq("status", status)
    result = query.execute()
    count_query = db.table("bookings").select("id", count="exact").eq("tenant_id", tenant_id)
    if status:
        count_query = count_query.eq("status", status)
    total = count_query.execute().count or 0
    return {"data": result.data or [], "total": total, "page": page, "limit": limit}


@router.get("/{booking_id}")
async def get_booking(booking_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = (
        db.table("bookings")
        .select("*, leads(name, phone)")
        .eq("id", booking_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    return result.data


@public_router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    import json
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = entity.get("notes", {})
    booking_id = notes.get("booking_id")
    razorpay_payment_id = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
    )

    tenant_id = None
    if booking_id:
        db = get_supabase()
        booking = db.table("bookings").select("tenant_id").eq("id", booking_id).maybe_single().execute()
        if booking and booking.data:
            tenant_id = booking.data.get("tenant_id")

    if not verify_webhook_signature(raw_body, signature, tenant_id=tenant_id):
        logger.warning(f"Razorpay webhook: invalid signature for tenant={tenant_id}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = payload.get("event", "")
    if event != "payment_link.paid":
        return {"status": "ignored", "event": event}

    if not booking_id:
        logger.error("Razorpay webhook: no booking_id in notes")
        return {"status": "error", "detail": "no booking_id"}

    result = confirm_booking(booking_id, razorpay_payment_id)
    if result and result[0]:
        phone, booking_ref, devotee_name, tenant_id = result
        from app.config_dynamic import get_setting
        default_template = (
            "🎉 *Booking Confirmed!*\n\n"
            "Hello {customer_name},\n\n"
            "Your booking is confirmed.\n"
            "📋 *Reference:* {booking_ref}\n\n"
            "✅ We will be in touch with further details.\n\n"
            "Thank you. 🙏"
        )
        template = get_setting("booking_confirmation_template", tenant_id=tenant_id) or default_template
        try:
            confirmation_msg = template.format(
                customer_name=devotee_name or "Customer",
                booking_ref=booking_ref,
            )
        except Exception:
            # Fallback if the user's custom template has formatting errors
            confirmation_msg = default_template.format(
                customer_name=devotee_name or "Customer",
                booking_ref=booking_ref,
            )
        try:
            await send_whatsapp(phone, confirmation_msg, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Confirmation WA send failed for {phone}: {e}")

    return {"status": "ok"}
