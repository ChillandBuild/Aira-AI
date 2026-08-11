# WhatsApp Coexistence Sync (Approach B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a coexistence Embedded Signup completes, pull in the client's existing WhatsApp phone contacts (to enrich already-known leads) and their pre-connection chat history (to backfill the conversation view), without creating new leads from either and without letting backfilled data touch scoring/segment/assignment.

**Architecture:** A new `request_coexistence_sync` call in `meta_cloud.py`, fired once from the existing coexistence branch in `whatsapp_embedded_signup`, triggers Meta's SMB App Data API for both sync types. Two new `elif` branches in the WhatsApp webhook's field dispatch handle the resulting `smb_app_state_sync` (contact enrichment) and `history` (message backfill) deliveries.

**Tech Stack:** FastAPI (`backend/app/`), pytest, httpx.

## Global Constraints

- Multi-tenancy: every DB read/write must be scoped by `tenant_id` (Hard Invariant 6).
- WhatsApp webhooks must already be past `X-Hub-Signature-256` verification before any field-specific logic runs — both new branches sit *inside* that already-verified path, no changes to signature checks (Hard Invariant 9).
- Unmatched contacts and unmatched history threads are never turned into new leads — a phone-book entry or old message isn't proof of opt-in, and `leads.opt_in_source` gates broadcast eligibility (Hard Invariant 7).
- Backfilled history never runs through `scoring_engine`, `maybe_assign_lead`, or `record_stage_event` — informational only, per the design's decision 2.

---

### Task 1: Trigger the SMB App Data API sync after coexistence signup

**Files:**
- Modify: `backend/app/services/meta_cloud.py` (append new function at end of file, after line 1012)
- Modify: `backend/app/routes/app_settings.py:665` (import), `:673-676` (call site)
- Test: `backend/tests/test_whatsapp_coexistence_sync_trigger.py` (new)

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `request_coexistence_sync(phone_number_id: str, access_token: str) -> None` — an async function that makes two POSTs and never raises (all failures logged).

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_request_coexistence_sync_posts_both_sync_types():
    from app.services.meta_cloud import request_coexistence_sync

    posted = []

    class _Resp:
        def json(self):
            return {"messaging_product": "whatsapp", "request_id": "req-1"}

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            posted.append((url, kwargs["json"], kwargs["headers"]))
            return _Resp()

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")

    assert len(posted) == 2
    urls = {p[0] for p in posted}
    assert urls == {"https://graph.facebook.com/v21.0/phone-1/smb_app_data"}
    sync_types = {p[1]["sync_type"] for p in posted}
    assert sync_types == {"smb_app_state_sync", "history"}
    for _url, body, headers in posted:
        assert body["messaging_product"] == "whatsapp"
        assert headers == {"Authorization": "Bearer token-1"}


@pytest.mark.asyncio
async def test_request_coexistence_sync_does_not_raise_on_http_error():
    from app.services.meta_cloud import request_coexistence_sync
    import httpx

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            raise httpx.ConnectTimeout("timed out")

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")  # must not raise


@pytest.mark.asyncio
async def test_request_coexistence_sync_logs_error_response_without_raising():
    from app.services.meta_cloud import request_coexistence_sync

    class _Resp:
        def json(self):
            return {"error": {"message": "bad token"}}

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp()

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")  # must not raise
```

Add all three functions to `backend/tests/test_whatsapp_coexistence_sync_trigger.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_sync_trigger.py -v`
Expected: FAIL — `request_coexistence_sync` doesn't exist yet (ImportError).

- [ ] **Step 3: Add the function**

Append to the end of `backend/app/services/meta_cloud.py`:

```python
async def request_coexistence_sync(phone_number_id: str, access_token: str) -> None:
    """Trigger Meta's SMB App Data API to backfill a coexistence number's existing
    phone contacts and message history. Fire-and-forget: this follows a signup
    that already succeeded, so a failed sync *request* shouldn't read as a failed
    connection -- errors are logged, never raised.
    """
    url = f"{_GRAPH_BASE}/{phone_number_id}/smb_app_data"
    headers = {"Authorization": f"Bearer {access_token}"}
    for sync_type in ("smb_app_state_sync", "history"):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={"messaging_product": "whatsapp", "sync_type": sync_type},
                    headers=headers,
                    timeout=20.0,
                )
            data = resp.json()
            if "error" in data:
                logger.warning("Coexistence %s sync request failed for %s: %s", sync_type, phone_number_id, data["error"])
            else:
                logger.info("Coexistence %s sync requested for %s: request_id=%s", sync_type, phone_number_id, data.get("request_id"))
        except httpx.HTTPError as e:
            logger.warning("Coexistence %s sync request failed for %s: %s", sync_type, phone_number_id, e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_sync_trigger.py -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Wire the call into the coexistence signup path**

In `backend/app/routes/app_settings.py`, change the import at line 665 from:

```python
    from app.services.meta_cloud import exchange_embedded_signup_code, register_phone_number
```

to:

```python
    from app.services.meta_cloud import exchange_embedded_signup_code, register_phone_number, request_coexistence_sync
```

Then change lines 673-676 from:

```python
    if payload.is_coexistence:
        # Number is already registered on the phone's WhatsApp Business app —
        # calling register_phone_number here would be wrong for this path.
        logger.info(f"Embedded Signup: coexistence path — skipping phone registration tenant={tenant_id}")
```

to:

```python
    if payload.is_coexistence:
        # Number is already registered on the phone's WhatsApp Business app —
        # calling register_phone_number here would be wrong for this path.
        logger.info(f"Embedded Signup: coexistence path — skipping phone registration tenant={tenant_id}")
        await request_coexistence_sync(payload.phone_number_id, access_token)
```

- [ ] **Step 6: Patch the existing coexistence signup test so it doesn't make a real network call**

`test_coexistence_signup_skips_phone_registration` in `backend/tests/test_whatsapp_embedded_signup_coexistence.py` exercises the `is_coexistence=True` path, which now also calls the real `request_coexistence_sync` unless mocked — that would attempt a real `httpx.AsyncClient()` POST to `graph.facebook.com` during the test run. In `backend/tests/test_whatsapp_embedded_signup_coexistence.py`, change the `with patch(...)` block inside `test_coexistence_signup_skips_phone_registration` (lines 29-34) from:

```python
    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock()) as register, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
```

to:

```python
    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock()) as register, \
         patch("app.services.meta_cloud.request_coexistence_sync", new=AsyncMock()) as sync_trigger, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
```

Then, still in that same test function, change:

```python
    register.assert_not_called()
    assert result["success"] is True
    assert result["phone_number"] == "+919999999999"
```

to:

```python
    register.assert_not_called()
    sync_trigger.assert_awaited_once_with("phone-1", "token-1")
    assert result["success"] is True
    assert result["phone_number"] == "+919999999999"
```

- [ ] **Step 7: Run the full embedded-signup test suite to check for regressions**

Run: `cd backend && pytest tests/ -k embedded_signup -v`
Expected: PASS — `test_coexistence_signup_skips_phone_registration` now also confirms the sync trigger fires with the right arguments; `test_standard_signup_still_registers_the_phone_number` is unaffected since it takes the non-coexistence branch, which never calls `request_coexistence_sync`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/meta_cloud.py backend/app/routes/app_settings.py backend/tests/test_whatsapp_coexistence_sync_trigger.py backend/tests/test_whatsapp_embedded_signup_coexistence.py
git commit -m "feat(whatsapp): trigger SMB App Data API sync on coexistence signup"
```

---

### Task 2: Handle `smb_app_state_sync` — enrich existing leads' names

**Files:**
- Modify: `backend/app/routes/webhook.py` (add a new `elif` branch immediately before `elif field == "smb_message_echoes":`, currently at line 383)
- Test: `backend/tests/test_whatsapp_coexistence_contact_sync_webhook.py` (new)

**Interfaces:**
- Consumes: `_get_tenant_id_for_meta_number(phone_number_id: str, db) -> str | None` (`webhook.py:46`, already defined).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Write the failing test**

```python
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
```

Add these to `backend/tests/test_whatsapp_coexistence_contact_sync_webhook.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_contact_sync_webhook.py -v`
Expected: FAIL — no branch handles `field == "smb_app_state_sync"` today, so `captured` stays empty for the first test.

- [ ] **Step 3: Add the handler**

In `backend/app/routes/webhook.py`, insert a new `elif` branch immediately before `elif field == "smb_message_echoes":` (currently line 383):

```python
            elif field == "smb_app_state_sync":
                meta_phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
                db = get_supabase()
                tenant_id = _get_tenant_id_for_meta_number(meta_phone_number_id, db) if meta_phone_number_id else None
                if not tenant_id:
                    logger.warning(f"No tenant for meta phone_number_id={meta_phone_number_id}, dropping smb_app_state_sync payload")
                    continue
                for entry in value.get("state_sync", []):
                    if entry.get("type") != "contact" or entry.get("action") == "remove":
                        continue
                    contact = entry.get("contact", {})
                    wa_id = contact.get("phone_number", "")
                    full_name = (contact.get("full_name") or "").strip()
                    phone = f"+{wa_id}" if wa_id and not wa_id.startswith("+") else wa_id
                    if not phone or not full_name:
                        continue

                    lead = db.table("leads").select("id,name").eq("phone", phone).eq("tenant_id", tenant_id).limit(1).execute()
                    if not lead.data:
                        continue
                    lead_row = lead.data[0]
                    if lead_row.get("name"):
                        continue

                    db.table("leads").update({"name": full_name}).eq("id", lead_row["id"]).eq("tenant_id", tenant_id).execute()
                    logger.info(f"smb_app_state_sync: enriched name for lead {lead_row['id']}")

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_contact_sync_webhook.py -v`
Expected: PASS (all four tests)

- [ ] **Step 5: Run the full webhook test suite to check for regressions**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_echo_webhook.py tests/test_whatsapp_audio_webhook.py tests/test_meta_webhook_verify.py -v`
Expected: PASS — the new branch sits before the `smb_message_echoes`/`messages` branches and doesn't change their behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/webhook.py backend/tests/test_whatsapp_coexistence_contact_sync_webhook.py
git commit -m "feat(whatsapp): enrich lead names from smb_app_state_sync contact sync"
```

---

### Task 3: Handle `history` — backfill pre-connection messages

**Files:**
- Modify: `backend/app/routes/webhook.py` (add a new `elif` branch immediately before `elif field == "smb_app_state_sync":`, added in Task 2)
- Test: `backend/tests/test_whatsapp_coexistence_history_webhook.py` (new)

**Interfaces:**
- Consumes: `_get_tenant_id_for_meta_number(phone_number_id: str, db) -> str | None` (`webhook.py:46`, already defined).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Write the failing test**

```python
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
```

Add these to `backend/tests/test_whatsapp_coexistence_history_webhook.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_history_webhook.py -v`
Expected: FAIL — no branch handles `field == "history"` today, so `captured` stays empty for the first test.

- [ ] **Step 3: Add the handler**

In `backend/app/routes/webhook.py`, insert a new `elif` branch immediately before `elif field == "smb_app_state_sync":` (added in Task 2):

```python
            elif field == "history":
                meta_phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
                db = get_supabase()
                tenant_id = _get_tenant_id_for_meta_number(meta_phone_number_id, db) if meta_phone_number_id else None
                if not tenant_id:
                    logger.warning(f"No tenant for meta phone_number_id={meta_phone_number_id}, dropping history payload")
                    continue
                for chunk in value.get("history", []):
                    for thread in chunk.get("threads", []):
                        wa_id = thread.get("id", "")
                        phone = f"+{wa_id}" if wa_id and not wa_id.startswith("+") else wa_id
                        if not phone:
                            continue

                        lead = db.table("leads").select("id").eq("phone", phone).eq("tenant_id", tenant_id).limit(1).execute()
                        if not lead.data:
                            logger.info(f"history: no lead for phone={phone} tenant={tenant_id}, skipping thread")
                            continue
                        lead_id = lead.data[0]["id"]

                        for msg in thread.get("messages", []):
                            msg_type = msg.get("type")
                            msg_id = msg.get("id", "")
                            if msg_type != "text":
                                logger.info(f"history: skipping unsupported type={msg_type}")
                                continue
                            body = (msg.get("text") or {}).get("body", "").strip()
                            timestamp = msg.get("timestamp")
                            if not body or not msg_id or not timestamp:
                                continue

                            already = db.table("messages").select("id").eq("meta_message_id", msg_id).eq("tenant_id", tenant_id).limit(1).execute()
                            if already.data:
                                continue

                            direction = "outbound" if msg.get("to") else "inbound"
                            created_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()

                            db.table("messages").insert({
                                "lead_id": lead_id,
                                "tenant_id": tenant_id,
                                "direction": direction,
                                "channel": "whatsapp",
                                "content": body,
                                "is_ai_generated": False,
                                "meta_message_id": msg_id,
                                "created_at": created_at,
                            }).execute()
                            logger.info(f"history: backfilled {direction} message for lead {lead_id}")

```

Note: `datetime` and `timezone` are already imported at the top of `webhook.py` (line 3), no new import needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_history_webhook.py -v`
Expected: PASS (all five tests)

- [ ] **Step 5: Run the full webhook test suite to check for regressions**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_contact_sync_webhook.py tests/test_whatsapp_coexistence_echo_webhook.py tests/test_whatsapp_audio_webhook.py tests/test_meta_webhook_verify.py tests/test_expert_handoff_webhook.py tests/test_webhook_expert_handoff_routing.py -v`
Expected: PASS — the new branch sits before the `smb_app_state_sync`/`smb_message_echoes`/`messages` branches and doesn't change their behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/webhook.py backend/tests/test_whatsapp_coexistence_history_webhook.py
git commit -m "feat(whatsapp): backfill message history from coexistence history sync"
```

---

## Manual verification (not automatable in this environment)

After all three tasks are merged and deployed, using the pilot client already connected via Approach A:
1. Confirm Render logs show `Coexistence smb_app_state_sync sync requested` and `Coexistence history sync requested` immediately after that client's original coexistence signup (may need re-triggering manually via `request_coexistence_sync` in a one-off script if the original signup predates this deploy, since the trigger only fires at signup time).
2. Once Meta delivers the webhooks, check that a lead with a blank name that matches one of the client's phone contacts now has a name.
3. Check that a lead who has old conversation history on the phone (before this integration existed) now shows those older messages in the dashboard conversation view, in the correct chronological order relative to messages sent after connecting.
4. Confirm no lead's score/segment changed as a result of the backfill (spot-check a couple of leads' `updated_at` on `score`/`segment` against the backfill's timing).
