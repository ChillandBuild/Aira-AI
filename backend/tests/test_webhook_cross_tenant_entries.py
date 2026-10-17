"""Regression test for AUDIT-2026-09.md finding C2.

The webhook verifies the X-Hub-Signature-256 against ONE tenant (the tenant
owning the first phone_number_id in the payload), then used to process every
change entry under whichever tenant its OWN phone_number_id resolved to --
with no check that it matched the signed tenant. A tenant that knows its own
app secret could sign a payload correctly for itself, but smuggle in a second
change entry naming another tenant's phone_number_id, and that entry would be
written under the victim tenant with no valid signature ever checked for it.

This test builds exactly that payload -- entry[0] for tenant-a (whose secret
signed the request), entry[1] for tenant-b -- and asserts tenant-b's data is
never touched.
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import webhook


PHONE_NUMBER_TENANT = {
    "phone-number-a": "tenant-a",
    "phone-number-b": "tenant-b",
}


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    """Minimal fake table: resolves phone_numbers -> tenant_id, and records
    every write (insert/update) it receives, tagged with whichever table it
    was called on, so the test can assert nothing landed under tenant-b."""

    def __init__(self, name: str, writes: list[tuple[str, dict]]):
        self.name = name
        self.writes = writes
        self._eq = {}
        self._op = "select"
        self._inserted_row = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def limit(self, *_a, **_k):
        return self

    def maybe_single(self):
        return self

    def order(self, *_a, **_k):
        return self

    def insert(self, row):
        self._op = "insert"
        row = dict(row) if isinstance(row, dict) else row
        self.writes.append((self.name, row))
        if self.name == "leads":
            self._inserted_row = {**row, "id": f"new-lead-{row.get('tenant_id')}"}
        return self

    def update(self, row):
        self._op = "update"
        self.writes.append((self.name, dict(row) if isinstance(row, dict) else row))
        return self

    def upsert(self, row, **_k):
        self._op = "upsert"
        self.writes.append((self.name, dict(row) if isinstance(row, dict) else row))
        return self

    def execute(self):
        if self.name == "phone_numbers" and self._op == "select":
            phone_id = self._eq.get("meta_phone_number_id")
            tenant = PHONE_NUMBER_TENANT.get(phone_id)
            return _Result({"tenant_id": tenant} if tenant else None)
        if self.name == "leads" and self._op == "insert" and self._inserted_row is not None:
            return _Result([self._inserted_row])
        # Any other table/op: no matching rows, so downstream lookups (leads
        # select, messages insert, etc.) come back empty rather than crashing
        # the handler -- this test only needs to see WHICH tenant was written.
        return _Result([])


def _db(writes: list[tuple[str, dict]]):
    db = MagicMock()
    db.table.side_effect = lambda name: _Table(name, writes)
    return db


def _malicious_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "phone-number-a"},
                        "messages": [{
                            "id": "wamid.a.1",
                            "from": "911111111111",
                            "type": "text",
                            "text": {"body": "hi from my own tenant"},
                        }],
                    },
                }],
            },
            {
                # Smuggled: names tenant-b's number, riding on tenant-a's signature.
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "phone-number-b"},
                        "messages": [{
                            "id": "wamid.b.1",
                            "from": "922222222222",
                            "type": "text",
                            "text": {"body": "forged message into tenant-b"},
                        }],
                    },
                }],
            },
        ],
    }


@pytest.mark.asyncio
async def test_second_entry_naming_another_tenant_is_dropped():
    writes: list[tuple[str, dict]] = []
    db = _db(writes)
    payload = _malicious_payload()

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=doesnt-matter-here"}
    background_tasks = MagicMock(spec=BackgroundTasks)

    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True), \
         patch("app.services.assignment.get_supabase", return_value=db):
        # verify_meta_signature is mocked to True for whichever tenant it's
        # called with -- exactly modelling "tenant-a's own secret correctly
        # signs a payload tenant-a controls the content of." The assignment
        # patch matters: the legitimate tenant-a entry's new-lead path calls
        # maybe_assign_lead(), which fetches ITS OWN supabase client rather
        # than using the one passed into the webhook handler -- without this
        # patch that call reaches the real network with a non-UUID tenant_id
        # (caught here in review; confirmed via SQL that no row landed).
        await webhook.whatsapp_webhook(request, background_tasks)

    # entry[1] must never have scheduled any background work or touched any
    # table under tenant-b's identity.
    background_tasks.add_task.assert_called_once()
    task_kwargs = background_tasks.add_task.call_args.kwargs
    assert task_kwargs["tenant_id"] == "tenant-a"

    tenant_b_writes = [w for (_table, w) in writes if isinstance(w, dict) and w.get("tenant_id") == "tenant-b"]
    assert tenant_b_writes == [], f"tenant-b was written to via a payload signed by tenant-a: {tenant_b_writes}"


@pytest.mark.asyncio
async def test_quality_update_for_another_tenants_number_is_dropped():
    """Same trick against phone_number_quality_update (no lead/message
    writes, but it can still flip another tenant's number RED)."""
    writes: list[tuple[str, dict]] = []
    db = _db(writes)
    payload = {
        "entry": [
            {
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "phone-number-a"},
                        "messages": [{
                            "id": "wamid.a.2",
                            "from": "911111111111",
                            "type": "text",
                            "text": {"body": "hi"},
                        }],
                    },
                }],
            },
            {
                "changes": [{
                    "field": "phone_number_quality_update",
                    "value": {
                        "phone_number_id": "phone-number-b",
                        "quality_rating": "RED",
                        "current_limit": "TIER_50",
                    },
                }],
            },
        ],
    }

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=doesnt-matter-here"}
    background_tasks = MagicMock(spec=BackgroundTasks)

    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True), \
         patch("app.services.assignment.get_supabase", return_value=db), \
         patch("app.routes.webhook.update_number_quality", new=AsyncMock(return_value=None)) as update_quality:
        # return_value=None mimics "no matching phone_numbers row" so that,
        # even in the unpatched (red) run, the code takes its own early-out
        # and never reaches handle_quality_red() -- which fetches ITS OWN
        # unmocked supabase client (app/services/failover.py) and would
        # otherwise hit the real network. The assertion below only cares
        # whether update_number_quality was invoked at all.
        await webhook.whatsapp_webhook(request, background_tasks)

    update_quality.assert_not_called()


def _capability_payload(waba_id, limit="TIER_10K"):
    return {"object": "whatsapp_business_account", "entry": [{
        "id": waba_id, "time": 1739321024,
        "changes": [{"field": "business_capability_update",
                     "value": {"max_daily_conversations_per_business": limit, "max_phone_numbers_per_waba": 25}}],
    }]}


def _waba_db(owner_by_waba):
    """app_settings lookup: meta_waba_id -> owning tenant(s)."""
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "app_settings":
            def by_value(_col, waba):
                q = MagicMock()
                q.execute.return_value = MagicMock(data=[{"tenant_id": tid} for tid in owner_by_waba.get(waba, [])])
                return q
            t.select.return_value.eq.return_value.eq.side_effect = by_value
        return t
    db.table.side_effect = table
    return db


async def _post(payload, db):
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=doesnt-matter-here"}
    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True) as verify, \
         patch("app.routes.webhook.set_portfolio_limit") as set_limit:
        await webhook.whatsapp_webhook(request, MagicMock(spec=BackgroundTasks))
    return verify, set_limit


@pytest.mark.asyncio
async def test_limit_raise_applies_to_the_wabas_own_tenant():
    """business_capability_update has no phone number -- the tenant comes from
    the WABA id, and the signature is still checked against that tenant."""
    verify, set_limit = await _post(_capability_payload("waba-a"), _waba_db({"waba-a": ["tenant-a"]}))
    assert verify.call_args.args[2] == "tenant-a"
    set_limit.assert_called_once_with("tenant-a", 10000)


@pytest.mark.asyncio
async def test_limit_raise_for_a_shared_or_unknown_waba_is_dropped():
    """Never guess whose WABA it is: shared or unknown -> nothing changes."""
    _, set_limit = await _post(_capability_payload("waba-shared"), _waba_db({"waba-shared": ["tenant-a", "tenant-b"]}))
    set_limit.assert_not_called()
    _, set_limit = await _post(_capability_payload("waba-nobody"), _waba_db({}))
    set_limit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_delivery_is_removed_from_the_limit_count():
    """Meta counts delivered messages only: a template reported failed stops counting."""
    deletes = []

    class _Del:
        def __init__(self):
            self.filters = {}

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def execute(self):
            deletes.append(dict(self.filters))
            return MagicMock(data=[])

    db = MagicMock()
    base_table = db.table

    def table(name):
        t = base_table(name)
        if name == "template_send_log":
            t.delete.side_effect = lambda: _Del()
        return t
    db.table = MagicMock(side_effect=table)

    payload = {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "phone-number-a"},
        "statuses": [{"id": "wamid.FAILED1", "status": "failed", "errors": [{"code": 131026, "title": "Message undeliverable"}]}],
    }}]}]}
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=doesnt-matter-here"}
    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook._get_tenant_id_for_meta_number", return_value="tenant-a"), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True):
        await webhook.whatsapp_webhook(request, MagicMock(spec=BackgroundTasks))
    assert {"meta_message_id": "wamid.FAILED1", "tenant_id": "tenant-a"} in deletes


@pytest.mark.asyncio
async def test_template_events_on_the_whatsapp_webhook_are_applied():
    """Meta sends every WABA field to the app's one callback URL, so template
    status changes and edits must be handled here too -- for the signed tenant only."""
    payload = {"entry": [{"id": "waba-a", "changes": [{"field": "message_template_components_update",
               "value": {"message_template_id": "meta-t-1", "message_template_element": "Hi {{1}}"}}]}]}
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=doesnt-matter-here"}
    with patch("app.routes.webhook.get_supabase", return_value=MagicMock()), \
         patch("app.routes.webhook._get_tenant_id_for_waba", return_value=None), \
         patch("app.routes.templates.tenant_for_template_payload", return_value="tenant-a"), \
         patch("app.routes.templates.apply_template_change") as apply, \
         patch("app.routes.webhook.verify_meta_signature", return_value=True) as verify:
        await webhook.whatsapp_webhook(request, MagicMock(spec=BackgroundTasks))
    assert verify.call_args.args[2] == "tenant-a"
    apply.assert_called_once()
    assert apply.call_args.args[1] == "message_template_components_update"
    assert apply.call_args.kwargs["tenant_id"] == "tenant-a"
