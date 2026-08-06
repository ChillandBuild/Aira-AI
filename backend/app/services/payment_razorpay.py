# backend/app/services/payment_razorpay.py
import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)

_RAZORPAY_BASE = "https://api.razorpay.com/v1"


def _get_key_id(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_key_id", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_key_id not configured in app settings")
    return v


def _get_key_secret(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_key_secret", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_key_secret not configured in app settings")
    return v


def _get_webhook_secret(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_webhook_secret", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_webhook_secret not configured in app settings")
    return v


async def create_payment_link(
    booking_id: str,
    booking_ref: str,
    amount_paise: int,
    customer_name: str,
    customer_phone: str,
    description: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a Razorpay Payment Link and return the short URL.

    Returns dict with keys:
      - payment_link_url: str
      - razorpay_payment_link_id: str
    """
    key_id = _get_key_id(tenant_id)
    key_secret = _get_key_secret(tenant_id)

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description,
        "customer": {
            "name": customer_name,
            "contact": customer_phone,
        },
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {
            "booking_id": booking_id,
            "booking_ref": booking_ref,
        },
        "callback_url": "",
        "callback_method": "get",
    }

    async with httpx.AsyncClient(auth=(key_id, key_secret), timeout=15.0) as client:
        resp = await client.post(
            f"{_RAZORPAY_BASE}/payment_links",
            json=payload,
            headers={"X-Razorpay-Idempotency-Key": f"booking:{booking_id}:payment_link"},
        )

    if not resp.is_success:
        raise RuntimeError(
            f"Razorpay payment link creation failed: {resp.status_code} {resp.text}"
        )

    data = resp.json()
    return {
        "payment_link_url": data["short_url"],
        "razorpay_payment_link_id": data["id"],
    }


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """Verify Razorpay webhook payload using HMAC-SHA256."""
    try:
        secret = _get_webhook_secret()
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received_signature)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
