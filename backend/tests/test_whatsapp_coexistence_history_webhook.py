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


def _history_payload(thread_phone="918888888888", messages=None):
    return {
        "entry": [{
            "changes": [{
                "field": "history",
                "value": {
                    "metadata": {"phone_number_id": "phone-number-1"},
                    "history": [{
                        "metadata": {"phase": "0", "chunk_order": "1", "progress": "100"},
                        "threads": [{
                            "id": thread_phone,
                            "messages": messages if messages is not None else [{
                                "from": thread_phone,
                                "id": "wamid.hist.1",
                                "timestamp": "1690000000",
                                "type": "text",
                                "text": {"body": "Hi, what are your charges?"},
                            }],
                        }],
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
async def test_inbound_history_message_backfilled_with_correct_direction_and_timestamp():
    captured: list[dict] = []
    db = _route_db(captured)

    response = await _post_webhook(db, _history_payload())

    assert response == {"status": "ok"}
    assert len(captured) == 1
    row = captured[0]
    assert row["lead_id"] == "lead-1"
    assert row["direction"] == "inbound"
    assert row["content"] == "Hi, what are your charges?"
    assert row["meta_message_id"] == "wamid.hist.1"
    assert row["created_at"] == "2023-07-22T04:26:40+00:00"


@pytest.mark.asyncio
async def test_outbound_history_message_detected_by_to_field():
    captured: list[dict] = []
    db = _route_db(captured)
    payload = _history_payload(messages=[{
        "from": "919999999999",
        "to": "918888888888",
        "id": "wamid.hist.2",
        "timestamp": "1690000100",
        "type": "text",
        "text": {"body": "We charge 500 per session"},
    }])

    await _post_webhook(db, payload)

    assert captured[0]["direction"] == "outbound"


@pytest.mark.asyncio
async def test_history_message_not_duplicated_on_replay():
    captured: list[dict] = []
    db = _route_db(captured, existing_message_ids={"wamid.hist.1"})

    await _post_webhook(db, _history_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_history_thread_with_no_matching_lead_is_skipped():
    captured: list[dict] = []
    db = _route_db(captured, lead_exists=False)

    await _post_webhook(db, _history_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_media_placeholder_type_is_skipped_without_error():
    captured: list[dict] = []
    db = _route_db(captured)
    payload = _history_payload(messages=[{
        "from": "918888888888",
        "id": "wamid.hist.3",
        "timestamp": "1690000200",
        "type": "media_placeholder",
    }])

    response = await _post_webhook(db, payload)

    assert response == {"status": "ok"}
    assert captured == []
