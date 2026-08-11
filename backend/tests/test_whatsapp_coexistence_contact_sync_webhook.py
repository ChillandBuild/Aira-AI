import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from app.routes import webhook


class _Result:
    def __init__(self, data):
        self.data = data


class _RouteTable:
    def __init__(self, name, captured_updates, lead_row=None):
        self.name = name
        self.captured_updates = captured_updates
        self.lead_row = lead_row
        self.operation = "select"
        self._update_payload = None
        self._eq_values = []

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def update(self, row):
        self.operation = "update"
        self._update_payload = row
        return self

    def eq(self, _col, value=None, **_kwargs):
        self._eq_values.append(value)
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.name == "phone_numbers":
            return _Result({"tenant_id": "tenant-1"})
        if self.name == "leads" and self.operation == "select":
            return _Result([self.lead_row] if self.lead_row else [])
        if self.name == "leads" and self.operation == "update":
            self.captured_updates.append({"lead_id": self._eq_values[0], **self._update_payload})
            return _Result([])
        return _Result([])


def _route_db(captured_updates, lead_row=None):
    db = MagicMock()
    db.table.side_effect = lambda name: _RouteTable(name, captured_updates, lead_row)
    return db


def _state_sync_payload(phone="919999999999", full_name="Ravi Kumar", action="add"):
    return {
        "entry": [{
            "changes": [{
                "field": "smb_app_state_sync",
                "value": {
                    "metadata": {"phone_number_id": "phone-number-1"},
                    "state_sync": [{
                        "type": "contact",
                        "contact": {"full_name": full_name, "first_name": full_name.split(" ")[0], "phone_number": phone},
                        "action": action,
                        "metadata": {"timestamp": "1700000000"},
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
async def test_matched_contact_with_blank_name_gets_enriched():
    captured: list[dict] = []
    db = _route_db(captured, lead_row={"id": "lead-1", "name": None})

    response = await _post_webhook(db, _state_sync_payload())

    assert response == {"status": "ok"}
    assert captured == [{"lead_id": "lead-1", "name": "Ravi Kumar"}]


@pytest.mark.asyncio
async def test_matched_contact_with_existing_name_is_not_overwritten():
    captured: list[dict] = []
    db = _route_db(captured, lead_row={"id": "lead-1", "name": "Already Named"})

    await _post_webhook(db, _state_sync_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_unmatched_contact_writes_nothing():
    captured: list[dict] = []
    db = _route_db(captured, lead_row=None)

    await _post_webhook(db, _state_sync_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_remove_action_writes_nothing_even_if_matched():
    captured: list[dict] = []
    db = _route_db(captured, lead_row={"id": "lead-1", "name": None})

    await _post_webhook(db, _state_sync_payload(action="remove"))

    assert captured == []
