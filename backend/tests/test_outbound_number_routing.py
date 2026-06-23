# backend/tests/test_outbound_number_routing.py
"""Replies must go out from the number that received the inbound (Option 2)."""
import inspect
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from app.services.ai_reply import generate_reply, send_whatsapp

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_send_whatsapp_forwards_phone_number_id_to_meta():
    """send_whatsapp must pass the inbound phone_number_id through to Meta,
    not let it fall back to the app_settings default number."""
    sent = AsyncMock(return_value={"messages": [{"id": "wamid.OK"}]})
    with patch("app.services.meta_cloud.send_text_message", sent):
        mid = await send_whatsapp(
            "+919999999999",
            "hi there",
            tenant_id="tenant-1",
            phone_number_id="1139353809270163",
        )
    assert mid == "wamid.OK"
    assert sent.await_args.kwargs["phone_number_id"] == "1139353809270163"


@pytest.mark.asyncio
async def test_send_whatsapp_phone_number_id_defaults_to_none():
    """When no phone_number_id is supplied, the existing app_settings fallback
    behaviour is preserved (passes None through to _creds)."""
    sent = AsyncMock(return_value={"messages": [{"id": "wamid.OK"}]})
    with patch("app.services.meta_cloud.send_text_message", sent):
        await send_whatsapp("+919999999999", "hi", tenant_id="tenant-1")
    assert sent.await_args.kwargs.get("phone_number_id") is None


def test_generate_reply_accepts_phone_number_id():
    assert "phone_number_id" in inspect.signature(generate_reply).parameters


def test_generate_reply_forwards_phone_number_id_to_send_whatsapp():
    src = _read("app/services/ai_reply.py")
    assert "send_whatsapp(_wa_phone, reply_text, tenant_id=lead_data.get(\"tenant_id\"), phone_number_id=phone_number_id)" in src


def test_webhook_threads_inbound_phone_number_id_to_reply():
    src = _read("app/routes/webhook.py")
    # background processor accepts the receiving number...
    assert "meta_phone_number_id: str" in src
    # ...is handed it on dispatch...
    assert "meta_phone_number_id=meta_phone_number_id" in src
    # ...and forwards it to the reply pipeline.
    assert "phone_number_id=meta_phone_number_id" in src
