import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.expert_handoff import public_router

app = FastAPI()
app.include_router(public_router, prefix="/api/v1/expert-handoff")
client = TestClient(app)


def _payload(session_id="sess-1", event="payment_link.paid"):
    return {
        "event": event,
        "payload": {
            "payment_link": {"entity": {"notes": {"booking_id": session_id, "booking_ref": "EH-ABC123"}}},
            "payment": {"entity": {"id": "pay_abc123"}},
        },
    }


def test_webhook_rejects_invalid_signature():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=False):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "bad"})
    assert res.status_code == 400


def test_webhook_rejects_unknown_session_id():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value=None):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "whatever"})
    assert res.status_code == 400


def test_webhook_verifies_signature_against_the_sessions_own_tenant():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="tenant-astro-tamil") as get_tenant, \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True) as verify, \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=None):
        client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})
    get_tenant.assert_called_once_with("sess-1")
    assert verify.call_args.kwargs.get("tenant_id") == "tenant-astro-tamil"


def test_webhook_ignores_non_paid_events():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(event="payment_link.cancelled"), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


_CONFIRMED = {
    "phone": "+919876543210",
    "tenant_id": "t-1",
    "lead_id": "lead-1",
    "customer_name": "Priya",
    "session": {"id": "sess-1", "collected_data": {"name": "Priya"}, "amount_paise": 19900},
    "lead": {"id": "lead-1", "phone": "+919876543210", "name": "Priya"},
}


def test_webhook_confirms_payment_and_sends_receipt():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=_CONFIRMED), \
         patch("app.routes.expert_handoff.astro_bridge.push_consultation", new=AsyncMock(return_value=None)), \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock(return_value="wamid.123")) as send:
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    send.assert_awaited_once()
    assert "Priya" in send.call_args[0][1]


def test_webhook_pushes_the_paid_session_across_the_astro_bridge():
    django_response = {"success": True, "question_id": 123, "horoscope_id": "HOR-AB12CD34", "astro_user_id": 456}
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=_CONFIRMED), \
         patch("app.routes.expert_handoff.astro_bridge.push_consultation", new=AsyncMock(return_value=django_response)) as push, \
         patch("app.routes.expert_handoff.record_astro_bridge_ids") as record, \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock(return_value="wamid.123")):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})

    assert res.status_code == 200
    push.assert_awaited_once_with(_CONFIRMED["session"], _CONFIRMED["lead"], "t-1")
    record.assert_called_once_with("sess-1", "t-1", django_response)


def test_webhook_receipt_still_sent_when_the_django_bridge_is_down():
    """A Django outage must never break the paid transition or the customer's receipt."""
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=_CONFIRMED), \
         patch("app.routes.expert_handoff.astro_bridge.push_consultation", new=AsyncMock(side_effect=RuntimeError("connection refused"))), \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock(return_value="wamid.123")) as send:
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    send.assert_awaited_once()


def test_webhook_does_not_push_when_the_session_was_already_confirmed():
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=None), \
         patch("app.routes.expert_handoff.astro_bridge.push_consultation", new=AsyncMock()) as push, \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock()) as send:
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})

    assert res.status_code == 200
    push.assert_not_awaited()
    send.assert_not_awaited()


def test_webhook_missing_session_id_returns_error_status():
    payload = _payload()
    payload["payload"]["payment_link"]["entity"]["notes"] = {}
    res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=payload, headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"
