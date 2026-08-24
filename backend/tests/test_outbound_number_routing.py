# backend/tests/test_outbound_number_routing.py
"""Replies must go out from the number that received the inbound (Option 2)."""
import ast
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


def _send_whatsapp_calls(src: str) -> list[ast.Call]:
    """Every `send_whatsapp(...)` call in a source string, as AST nodes.

    Asserted structurally rather than by matching the call's source text: the
    call is routinely reflowed across lines and gains keyword arguments (it
    picked up `reply_to_message_id`, and a quick-reply-block branch, in
    2026-08), which silently broke a literal string match even though the
    wiring under test never changed."""
    return [
        node
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "send_whatsapp"
    ]


def test_generate_reply_forwards_phone_number_id_to_send_whatsapp():
    calls = _send_whatsapp_calls(_read("app/services/ai_reply.py"))

    # There is more than one text-reply dispatch (the ordinary path, plus the
    # fallback when a quick-reply block fails to send). EVERY one of them has to
    # forward the number, so this asserts over all of them -- an `any()` here
    # would stay green while one branch silently regressed.
    dispatches = [
        c for c in calls
        if {a.id for a in c.args if isinstance(a, ast.Name)} >= {"_wa_phone", "reply_text"}
    ]
    assert dispatches, "no send_whatsapp(_wa_phone, reply_text, ...) dispatch found in ai_reply.py"

    def forwards(call: ast.Call) -> bool:
        return any(
            kw.arg == "phone_number_id"
            and isinstance(kw.value, ast.Name)
            and kw.value.id == "phone_number_id"
            for kw in call.keywords
        ) and any(kw.arg == "tenant_id" for kw in call.keywords)

    offenders = [c.lineno for c in dispatches if not forwards(c)]
    assert not offenders, (
        f"send_whatsapp(_wa_phone, reply_text, ...) at line(s) {offenders} does not forward "
        "phone_number_id=phone_number_id -- those replies fall back to the app_settings "
        "default number instead of going out from the number that received the inbound"
    )


def test_webhook_threads_inbound_phone_number_id_to_reply():
    src = _read("app/routes/webhook.py")
    # background processor accepts the receiving number...
    assert "meta_phone_number_id: str" in src
    # ...is handed it on dispatch...
    assert "meta_phone_number_id=meta_phone_number_id" in src
    # ...and forwards it to the reply pipeline.
    assert "phone_number_id=meta_phone_number_id" in src
