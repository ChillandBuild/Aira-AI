import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from app.routes import webhook


class _Result:
    def __init__(self, data):
        self.data = data


class _RouteTable:
    def __init__(self, name, captured_messages, existing_message_ids=(), lead_exists=True):
        self.name = name
        self.captured_messages = captured_messages
        self.existing_message_ids = existing_message_ids
        self.lead_exists = lead_exists
        self.operation = "select"
        self._last_eq_values = []

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def insert(self, row):
        self.operation = "insert"
        if self.name == "messages":
            self.captured_messages.append(row)
        return self

    def eq(self, _col, value=None, **_kwargs):
        self._last_eq_values.append(value)
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.name == "phone_numbers":
            return _Result({"tenant_id": "tenant-1"})
        if self.name == "messages" and self.operation == "select":
            msg_id = self._last_eq_values[0] if self._last_eq_values else None
            found = [{"id": "existing"}] if msg_id in self.existing_message_ids else []
            return _Result(found)
        if self.name == "messages" and self.operation == "insert":
            return _Result([{"id": "message-1"}])
        if self.name == "leads" and self.operation == "select":
            return _Result([{"id": "lead-1"}] if self.lead_exists else [])
        return _Result([])


def _route_db(captured_messages, existing_message_ids=(), lead_exists=True):
    db = MagicMock()
    db.table.side_effect = lambda name: _RouteTable(name, captured_messages, existing_message_ids, lead_exists)
    return db


def _echo_payload(echo_id="wamid.echo.1", to="919999999999", body="Sure, I'll call you back"):
    return {
        "entry": [{
            "changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "metadata": {"phone_number_id": "phone-number-1"},
                    "message_echoes": [{
                        "from": "918888888888",
                        "to": to,
                        "id": echo_id,
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
            }],
        }],
    }


async def _post_webhook(db, payload):
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=test"}
    background_tasks = MagicMock(spec=BackgroundTasks)
    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True):
        return await webhook.whatsapp_webhook(request, background_tasks)


@pytest.mark.asyncio
async def test_smb_message_echo_is_recorded_as_outbound_message():
    captured: list[dict] = []
    db = _route_db(captured)

    response = await _post_webhook(db, _echo_payload())

    assert response == {"status": "ok"}
    assert captured == [{
        "lead_id": "lead-1",
        "tenant_id": "tenant-1",
        "direction": "outbound",
        "channel": "whatsapp",
        "content": "Sure, I'll call you back",
        "is_ai_generated": False,
        "meta_message_id": "wamid.echo.1",
    }]


@pytest.mark.asyncio
async def test_smb_message_echo_is_not_duplicated_on_replay():
    captured: list[dict] = []
    db = _route_db(captured, existing_message_ids={"wamid.echo.1"})

    await _post_webhook(db, _echo_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_smb_message_echo_drops_when_no_lead_matches():
    captured: list[dict] = []
    db = _route_db(captured, lead_exists=False)

    await _post_webhook(db, _echo_payload())

    assert captured == []
