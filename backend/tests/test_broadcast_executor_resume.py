"""Regression test for AUDIT-2026-09.md finding C4.

Before this fix, execute_broadcast() built up every recipient row in memory
and wrote them to broadcast_recipients in one batch at the very end. A
crash/restart mid-send (a Render deploy, an OOM kill -- anything Python
can't catch with except) lost the record of every message already sent,
left the row stuck at status='running' forever, and gave no safe way to
resume it (re-running would have re-sent to everyone, since nothing marked
who'd already been messaged).

This proves two things against the real execute_broadcast():
1. Each recipient row lands in the DB as soon as it's decided, not batched.
2. Re-running the SAME broadcast_id skips phones that already have a
   recipient row, and sends only to the ones that don't -- a resume is
   safe, not a re-send-to-everyone.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import broadcast_executor


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: "FakeDB", table: str):
        self.store = store
        self.table_name = table
        self.op = None
        self.payload = None
        self.filters: dict = {}
        self.in_filters: dict = {}
        self.select_cols: str | None = None
        self.saw_gte = False
        self.saw_is = False

    def select(self, *a, **_k):
        self.op = "select"
        self.select_cols = a[0] if a else None
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, **_k):
        self.op = "upsert"
        self.payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def neq(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        self.saw_gte = True
        return self

    def in_(self, col, values):
        self.in_filters[col] = list(values)
        return self

    @property
    def not_(self):
        return self

    def is_(self, *_a, **_k):
        self.saw_is = True
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        self.store.calls.append({"table": self.table_name, "op": self.op, "payload": self.payload, "filters": dict(self.filters)})
        if self.op == "select":
            if self.table_name == "phone_numbers":
                return _Result(self.store.phone_numbers)
            if self.table_name == "message_templates":
                return _Result(self.store.templates.get(self.filters.get("name"), []))
            if self.table_name == "leads":
                if self.filters.get("opted_out") is True:
                    return _Result([r for r in self.store.leads if r["phone"] in self.store.opted_out_phones])
                if self.saw_gte or self.saw_is:
                    # suppressed (outbound_no_reply_count) / negative-reply
                    # lookups -- none of the test's leads match either.
                    return _Result([])
                # The one remaining select is the "id,phone,name" lookup that
                # builds phone_to_lead_id -- the only one that wants every lead.
                return _Result(self.store.leads)
            if self.table_name == "broadcast_recipients":
                return _Result([{"phone": p} for p in self.store.already_recorded])
            if self.table_name == "scheduled_broadcasts":
                return _Result({"abort_requested": False})
            return _Result([])
        if self.op == "update":
            if self.table_name == "scheduled_broadcasts" and self.payload.get("status") == "running":
                # CAS lock: only succeeds if not already claimed this run.
                if self.store.lock_taken:
                    return _Result([])
                self.store.lock_taken = True
                return _Result([{"id": "row-1"}])
            return _Result([{"id": "ok"}])
        if self.op in ("insert", "upsert"):
            if self.table_name == "broadcast_recipients":
                rows = self.payload if isinstance(self.payload, list) else [self.payload]
                self.store.recipient_inserts.extend(rows)
            return _Result([{"id": "new-id"}])
        return _Result([])


class FakeDB:
    def __init__(self, leads, phone_numbers, templates, already_recorded=None):
        self.calls: list[dict] = []
        self.leads = leads
        self.phone_numbers = phone_numbers
        self.templates = templates
        self.opted_out_phones: set[str] = set()
        self.already_recorded = already_recorded or []
        self.recipient_inserts: list[dict] = []
        self.lock_taken = False

    def table(self, name):
        return _Query(self, name)

    def rpc(self, *_a, **_k):
        q = _Query(self, "_rpc")
        return q


LEAD_A = {"id": "lead-a", "phone": "+911111111111", "name": "Alice"}
LEAD_B = {"id": "lead-b", "phone": "+912222222222", "name": "Bob"}

ROW = {
    "id": "broadcast-1",
    "tenant_id": "tenant-1",
    "template_name": "promo",
    "variable_mapping": [],
    "opt_in_source": "whatsapp",
    "tag_id": None,
    "leads_json": [
        {"phone": "+911111111111", "name": "Alice"},
        {"phone": "+912222222222", "name": "Bob"},
    ],
}


def _templates():
    return {"promo": [{"language": "en", "body_text": "Hello", "variations": []}]}


@pytest.mark.asyncio
async def test_recipient_rows_are_written_as_they_happen_not_batched_at_the_end():
    db = FakeDB([LEAD_A, LEAD_B], [{"id": "phone-num-1", "meta_phone_number_id": "num-1", "number": "+910000000000"}], _templates())

    with patch("app.services.broadcast_executor.get_supabase", return_value=db), \
         patch("app.services.broadcast_executor.send_template_message", new=AsyncMock(return_value={"messages": [{"id": "wamid.1"}]})), \
         patch("app.services.broadcast_executor.meter"), \
         patch("app.services.broadcast_executor.increment_send_count", new=AsyncMock()), \
         patch("app.services.broadcast_executor.new_lead_score_and_segment", return_value=(3, "C")):
        result = await broadcast_executor.execute_broadcast(dict(ROW))

    assert result["sent"] == 2
    # Two leads sent -> two SEPARATE inserts into broadcast_recipients, proving
    # each row was written as it was decided rather than one final batch call.
    recipient_insert_calls = [c for c in db.calls if c["table"] == "broadcast_recipients" and c["op"] == "insert"]
    assert len(recipient_insert_calls) == 2, f"expected 2 separate incremental inserts, got {len(recipient_insert_calls)}"
    assert {r["phone"] for r in db.recipient_inserts} == {LEAD_A["phone"], LEAD_B["phone"]}


@pytest.mark.asyncio
async def test_resuming_a_broadcast_skips_already_recorded_phones_and_never_resends():
    # Simulates re-running the SAME broadcast_id after a crash: Alice already
    # has a recipient row from before the crash: Bob does not.
    db = FakeDB(
        [LEAD_A, LEAD_B],
        [{"id": "phone-num-1", "meta_phone_number_id": "num-1", "number": "+910000000000"}],
        _templates(),
        already_recorded=[LEAD_A["phone"]],
    )

    with patch("app.services.broadcast_executor.get_supabase", return_value=db), \
         patch("app.services.broadcast_executor.send_template_message", new=AsyncMock(return_value={"messages": [{"id": "wamid.2"}]})) as mock_send, \
         patch("app.services.broadcast_executor.meter"), \
         patch("app.services.broadcast_executor.increment_send_count", new=AsyncMock()), \
         patch("app.services.broadcast_executor.new_lead_score_and_segment", return_value=(3, "C")):
        result = await broadcast_executor.execute_broadcast(dict(ROW))

    # Only Bob should have been dialled out to -- Alice must NEVER be re-sent.
    sent_phones = [call.kwargs["to_number"] for call in mock_send.await_args_list]
    assert sent_phones == [LEAD_B["phone"]], f"resumed run re-sent to an already-recorded phone: {sent_phones}"
    assert result["sent"] == 1

    recipient_insert_calls = [c for c in db.calls if c["table"] == "broadcast_recipients" and c["op"] == "insert"]
    assert len(recipient_insert_calls) == 1
    assert db.recipient_inserts[0]["phone"] == LEAD_B["phone"]
