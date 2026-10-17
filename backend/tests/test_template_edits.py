"""Template edits (2026-10-17).

- Meta allows editing APPROVED, REJECTED and PAUSED templates; Anril now does too.
- An edit Meta refuses (e.g. a second approved-template edit within 24 hours)
  changes nothing locally, so Anril's copy never drifts from Meta's.
- An edit made elsewhere (WhatsApp Manager) arrives as
  message_template_components_update and updates Anril's copy -- the broadcast
  screen counts {{n}} variables from it.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import templates as tpl


class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.f = db, table, "select", None, {}

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = [r for r in self.db.rows if all(r.get(k) == v for k, v in self.f.items())]
        if self.op == "update":
            for r in rows:
                r.update(self.payload)
            self.db.updates.append(self.payload)
        return _Res([dict(r) for r in rows])


class _DB:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.updates = []

    def table(self, _name):
        return _Q(self, _name)


def _template(status, **kw):
    row = {"id": "t-1", "tenant_id": "ten-1", "name": "token_inactive", "status": status,
           "meta_template_id": "meta-t-1", "body_text": "வணக்கம் {{1}}", "header_text": None,
           "header_media_type": None, "footer_text": None,
           "buttons": [{"type": "QUICK_REPLY", "text": "Stop"}, {"type": "URL", "text": "Ask", "url": "https://old"}]}
    row.update(kw)
    return row


async def _edit(db, body="Hello there, thanks for writing to us.", meta=None):
    with patch.object(tpl, "get_supabase", return_value=db), \
         patch.object(tpl, "update_template_on_meta", new=meta or AsyncMock(return_value={"success": True})):
        return await tpl.update_template("t-1", tpl.UpdateTemplate(body_text=body), tenant_id="ten-1", _ctx={})


@pytest.mark.asyncio
async def test_an_approved_template_can_be_edited():
    db = _DB([_template("APPROVED")])
    meta = AsyncMock(return_value={"success": True})
    out = await _edit(db, meta=meta)
    meta.assert_awaited_once()
    assert out["body_text"] == "Hello there, thanks for writing to us."
    assert out["status"] == "PENDING"  # back in Meta's review until re-approved


@pytest.mark.asyncio
async def test_an_edit_meta_refuses_changes_nothing_locally():
    db = _DB([_template("APPROVED")])
    refused = AsyncMock(side_effect=HTTPException(
        status_code=400,
        detail='{"error":{"message":"Invalid parameter","error_user_msg":"You can only edit an approved template once every 24 hours."}}',
    ))
    with pytest.raises(HTTPException) as e:
        await _edit(db, meta=refused)
    assert "once every 24 hours" in e.value.detail
    assert db.updates == []
    assert db.rows[0]["status"] == "APPROVED" and db.rows[0]["body_text"] == "வணக்கம் {{1}}"


@pytest.mark.asyncio
async def test_a_pending_template_still_cannot_be_edited():
    db = _DB([_template("PENDING")])
    with pytest.raises(HTTPException) as e:
        await _edit(db)
    assert e.value.status_code == 400


def test_an_edit_in_whatsapp_manager_updates_anrils_copy():
    db = _DB([_template("APPROVED")])
    tpl.apply_template_change(db, "message_template_components_update", {
        "message_template_id": "meta-t-1",
        "message_template_element": "வணக்கம் {{1}}, உங்க {{2}} offer!",
        "message_template_footer": "Reply STOP to opt out",
        "message_template_buttons": [{"message_template_button_type": "URL",
                                      "message_template_button_text": "Ask now",
                                      "message_template_button_url": "https://new"}],
    }, tenant_id="ten-1")
    row = db.rows[0]
    assert row["body_text"] == "வணக்கம் {{1}}, உங்க {{2}} offer!"
    assert row["footer_text"] == "Reply STOP to opt out"
    # Meta only reports URL/phone buttons: the quick reply is kept, the URL one replaced.
    assert row["buttons"] == [{"type": "QUICK_REPLY", "text": "Stop"},
                              {"type": "URL", "text": "Ask now", "url": "https://new"}]


def test_a_template_edit_for_another_tenant_is_not_applied():
    db = _DB([_template("APPROVED")])
    tpl.apply_template_change(db, "message_template_components_update", {
        "message_template_id": "meta-t-1", "message_template_element": "hijacked",
    }, tenant_id="someone-else")
    assert db.rows[0]["body_text"] == "வணக்கம் {{1}}"


def test_status_change_still_applies():
    db = _DB([_template("PENDING")])
    tpl.apply_template_change(db, "message_template_status_update",
                              {"message_template_id": "meta-t-1", "event": "APPROVED"}, tenant_id="ten-1")
    assert db.rows[0]["status"] == "APPROVED" and db.rows[0]["approved_at"]


# ── Only APPROVED is used anywhere ───────────────────────────────────────

@pytest.mark.parametrize("event,stored", [
    ("APPROVED", "APPROVED"), ("REINSTATED", "APPROVED"), ("PENDING", "PENDING"), ("IN_APPEAL", "PENDING"),
    ("REJECTED", "REJECTED"), ("PAUSED", "PAUSED"), ("DISABLED", "DISABLED"),
    ("ARCHIVED", "ARCHIVED"), ("DELETED", "DELETED"), ("PENDING_DELETION", "DELETED"),
])
def test_every_meta_status_event_is_recorded(event, stored):
    db = _DB([_template("APPROVED")])
    tpl.apply_template_change(db, "message_template_status_update",
                              {"message_template_id": "meta-t-1", "event": event}, tenant_id="ten-1")
    assert db.rows[0]["status"] == stored


@pytest.mark.parametrize("event", ["FLAGGED", "LOCKED", "LIMIT_EXCEEDED", "UNARCHIVED"])
def test_events_that_dont_change_sendability_leave_status_alone(event):
    db = _DB([_template("APPROVED")])
    tpl.apply_template_change(db, "message_template_status_update",
                              {"message_template_id": "meta-t-1", "event": event}, tenant_id="ten-1")
    assert db.rows[0]["status"] == "APPROVED"


def test_unknown_status_from_a_sync_counts_as_not_approved():
    assert tpl.stored_template_status("IN_APPEAL") == "PENDING"
    assert tpl.stored_template_status("SOMETHING_NEW") == "PENDING"
    assert tpl.stored_template_status(None) == "PENDING"


def test_approved_template_helper_refuses_anything_but_approved():
    from app.services.template_params import approved_template
    for status in ("PENDING", "REJECTED", "PAUSED", "DISABLED"):
        db = _DB([_template(status)])
        assert approved_template(db, "ten-1", "token_inactive") is None
    assert approved_template(_DB([_template("APPROVED")]), "ten-1", "token_inactive")["name"] == "token_inactive"


@pytest.mark.asyncio
async def test_reengagement_waits_while_its_template_is_in_review():
    from app.services import reengagement_service as rs
    rs._NO_SENDER_UNTIL.clear()
    db = _DB([_template("PENDING", name="comeback")])
    send = AsyncMock()
    with patch.object(rs, "send_template_message", send):
        with pytest.raises(rs.NoSenderAvailable):
            await rs._send_step_template(db, "ten-1", {"id": "l1", "phone": "+911"}, {"id": "s1"},
                                         template_name="comeback", template_variables=[], log_status="sent")
    send.assert_not_awaited()
