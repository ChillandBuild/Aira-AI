import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import payment_razorpay as pr


def test_get_key_id_raises_when_not_configured():
    with patch.object(pr, "get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="razorpay_key_id"):
            pr._get_key_id(tenant_id="t-1")


def test_verify_webhook_signature_accepts_matching_hmac():
    with patch.object(pr, "get_setting", return_value="whsec_test"):
        body = b'{"event":"payment_link.paid"}'
        sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
        assert pr.verify_webhook_signature(body, sig) is True


def test_verify_webhook_signature_rejects_mismatched_hmac():
    with patch.object(pr, "get_setting", return_value="whsec_test"):
        assert pr.verify_webhook_signature(b"{}", "deadbeef") is False


@pytest.mark.asyncio
async def test_create_payment_link_returns_url_and_id():
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {"short_url": "https://rzp.io/abc", "id": "plink_123"}

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch.object(pr, "get_setting", side_effect=["key_id", "key_secret"]), \
         patch("httpx.AsyncClient", return_value=fake_client):
        result = await pr.create_payment_link(
            booking_id="session-1",
            booking_ref="EH-ABC123",
            amount_paise=2900,
            customer_name="Priya",
            customer_phone="+919876543210",
            description="Consultation — Priya (EH-ABC123)",
            tenant_id="t-1",
        )
    assert result == {"payment_link_url": "https://rzp.io/abc", "razorpay_payment_link_id": "plink_123"}


@pytest.mark.asyncio
async def test_create_payment_link_raises_on_failed_response():
    fake_resp = MagicMock()
    fake_resp.is_success = False
    fake_resp.status_code = 400
    fake_resp.text = "bad request"

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch.object(pr, "get_setting", side_effect=["key_id", "key_secret"]), \
         patch("httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(RuntimeError, match="Razorpay payment link creation failed"):
            await pr.create_payment_link(
                booking_id="session-1", booking_ref="EH-ABC123", amount_paise=2900,
                customer_name="Priya", customer_phone="+919876543210",
                description="x", tenant_id="t-1",
            )
