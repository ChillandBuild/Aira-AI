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
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=False):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "bad"})
    assert res.status_code == 400


def test_webhook_ignores_non_paid_events():
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(event="payment_link.cancelled"), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


def test_webhook_confirms_payment_and_sends_receipt():
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=("+919876543210", "t-1", "lead-1", "Priya")), \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock(return_value="wamid.123")) as send:
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    send.assert_awaited_once()
    assert "Priya" in send.call_args[0][1]


def test_webhook_missing_session_id_returns_error_status():
    payload = _payload()
    payload["payload"]["payment_link"]["entity"]["notes"] = {}
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=payload, headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"
