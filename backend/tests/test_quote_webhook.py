"""Tests for the quote_id branch of POST /razorpay-webhook -- a quote's
payment link carries notes={"quote_id": ...} instead of the intake flow's
notes={"booking_id": ...}, and must route to confirm_quote_payment, not
confirm_intake_payment, without ever touching the bookings/intake_sessions
tables. Mirrors test_expert_handoff_webhook.py's structure for the sibling
booking_id path.
"""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.intake import public_router

app = FastAPI()
app.include_router(public_router, prefix="/api/v1/intake")
client = TestClient(app)


def _quote_payload(quote_id="quote-1", event="payment_link.paid"):
    return {
        "event": event,
        "payload": {
            "payment_link": {"entity": {"notes": {"quote_id": quote_id}}},
            "payment": {"entity": {"id": "pay_abc123", "amount": 320000}},
        },
    }


def test_no_session_or_quote_id_is_an_error():
    payload = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"notes": {}}}}}
    res = client.post("/api/v1/intake/razorpay-webhook", json=payload, headers={"x-razorpay-signature": "x"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"


def test_unknown_quote_id_is_400():
    with patch("app.services.quotes.get_quote_tenant_id", return_value=None):
        res = client.post(
            "/api/v1/intake/razorpay-webhook", json=_quote_payload(), headers={"x-razorpay-signature": "x"}
        )
    assert res.status_code == 400


def test_verifies_signature_against_the_quotes_own_tenant():
    with patch("app.services.quotes.get_quote_tenant_id", return_value="tenant-1") as get_tenant, \
         patch("app.routes.intake.verify_webhook_signature", return_value=True) as verify, \
         patch("app.services.quotes.confirm_quote_payment", return_value=None):
        client.post("/api/v1/intake/razorpay-webhook", json=_quote_payload(), headers={"x-razorpay-signature": "ok"})
    get_tenant.assert_called_once_with("quote-1")
    assert verify.call_args.kwargs.get("tenant_id") == "tenant-1"


def test_non_paid_event_for_a_quote_is_ignored():
    with patch("app.services.quotes.get_quote_tenant_id", return_value="tenant-1"), \
         patch("app.routes.intake.verify_webhook_signature", return_value=True):
        res = client.post(
            "/api/v1/intake/razorpay-webhook",
            json=_quote_payload(event="payment_link.expired"),
            headers={"x-razorpay-signature": "ok"},
        )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


def test_paid_quote_confirms_payment_and_sends_a_receipt():
    with patch("app.services.quotes.get_quote_tenant_id", return_value="tenant-1"), \
         patch("app.routes.intake.verify_webhook_signature", return_value=True), \
         patch("app.services.quotes.confirm_quote_payment", return_value={
             "tenant_id": "tenant-1", "lead_id": "lead-1", "payment_link": "https://rzp.io/abc",
         }), \
         patch("app.routes.intake.get_supabase") as mock_get_db, \
         patch("app.routes.intake.send_whatsapp", new=AsyncMock(return_value="wamid.1")) as send:
        mock_get_db.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            "phone": "+919876543210", "name": "Priya",
        }
        res = client.post(
            "/api/v1/intake/razorpay-webhook", json=_quote_payload(), headers={"x-razorpay-signature": "ok"}
        )

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    send.assert_awaited_once()
    assert send.call_args[0][0] == "+919876543210"


def test_second_delivery_of_the_same_paid_event_sends_no_duplicate_receipt():
    """confirm_quote_payment itself is the race guard (see test_quotes.py) --
    this just confirms the route respects a None result instead of sending
    a receipt for nothing."""
    with patch("app.services.quotes.get_quote_tenant_id", return_value="tenant-1"), \
         patch("app.routes.intake.verify_webhook_signature", return_value=True), \
         patch("app.services.quotes.confirm_quote_payment", return_value=None), \
         patch("app.routes.intake.send_whatsapp", new=AsyncMock()) as send:
        res = client.post(
            "/api/v1/intake/razorpay-webhook", json=_quote_payload(), headers={"x-razorpay-signature": "ok"}
        )

    assert res.status_code == 200
    send.assert_not_awaited()
