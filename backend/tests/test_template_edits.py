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
        self.db, self.table, self.op, self.payload = db, table, "select", None
        self.f, self.inf, self.gtef = {}, {}, {}

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def in_(self, col, vals):
        self.inf[col] = list(vals)
        return self

    def gte(self, col, val):
        self.gtef[col] = val
        return self

    def limit(self, _n):
        return self

    def _match(self, r):
        return (all(r.get(k) == v for k, v in self.f.items())
                and all(r.get(k) in v for k, v in self.inf.items())
                and all(str(r.get(k)) >= str(v) for k, v in self.gtef.items()))

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            row = dict(self.payload)
            row.setdefault("id", f"new-{len(rows) + 1}")
            if self.table == "template_edit_log":
                row.setdefault("edited_at", self.db.now)
            rows.append(row)
            if self.table == "message_templates":
                self.db.inserts.append(self.payload)
            return _Res([dict(row)])
        hit = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
            self.db.updates.append(self.payload)
        return _Res([dict(r) for r in hit])


class _DB:
    def __init__(self, rows):
        from datetime import datetime, timezone
        self.tables = {"message_templates": [dict(r) for r in rows]}
        self.updates = []
        self.inserts = []
        self.now = datetime.now(timezone.utc).isoformat()

    @property
    def rows(self):
        return self.tables["message_templates"]

    def table(self, name):
        return _Q(self, name)

    def edits(self):
        return self.tables.get("template_edit_log", [])


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



# ── A template that doesn't reach Meta isn't saved ───────────────────────

async def _create(db, submit):
    payload = tpl.CreateTemplate(name="new_offer", category="MARKETING", language="en",
                                 body_text="Hello there, thanks for writing to us.")
    with patch.object(tpl, "get_supabase", return_value=db),          patch.object(tpl, "get_setting", return_value="waba-1"),          patch.object(tpl, "submit_template", new=submit):
        return await tpl.create_template(payload, tenant_id="ten-1", _ctx={})


@pytest.mark.asyncio
async def test_template_meta_refuses_is_not_saved_and_meta_s_reason_is_shown():
    db = _DB([])
    refused = AsyncMock(side_effect=HTTPException(status_code=400, detail='{"error":{"error_user_msg":"Body has too many emojis."}}'))
    with pytest.raises(HTTPException) as e:
        await _create(db, refused)
    assert "too many emojis" in e.value.detail
    assert db.inserts == [] and db.updates == []


@pytest.mark.asyncio
async def test_template_when_meta_cant_be_reached_is_not_saved():
    db = _DB([])
    with pytest.raises(HTTPException) as e:
        await _create(db, AsyncMock(side_effect=ConnectionError("network down")))
    assert e.value.status_code == 502 and "Couldn't reach Meta" in e.value.detail
    assert db.inserts == []


@pytest.mark.asyncio
async def test_template_meta_accepts_is_saved_pending_with_its_meta_id():
    db = _DB([])
    out = await _create(db, AsyncMock(return_value={"id": "meta-777", "status": "PENDING"}))
    assert out["status"] == "PENDING" and out["meta_template_id"] == "meta-777"


@pytest.mark.asyncio
async def test_editing_a_template_meta_never_received_submits_it():
    """Old rows saved without reaching Meta (no meta_template_id) used to stay
    stuck: an edit only changed Anril's copy. Now saving sends it to Meta."""
    db = _DB([_template("PENDING", meta_template_id=None, meta_waba_id="waba-1")])
    submit = AsyncMock(return_value={"id": "meta-new"})
    with patch.object(tpl, "get_supabase", return_value=db),          patch.object(tpl, "submit_template", new=submit),          patch.object(tpl, "update_template_on_meta", new=AsyncMock()) as edit_on_meta:
        out = await tpl.update_template("t-1", tpl.UpdateTemplate(body_text="Hello there, thanks for writing to us."),
                                        tenant_id="ten-1", _ctx={})
    submit.assert_awaited_once()
    edit_on_meta.assert_not_awaited()
    assert out["meta_template_id"] == "meta-new" and out["status"] == "PENDING"


# ── Meta's edit limit for approved templates ─────────────────────────────

from datetime import datetime as _dt, timedelta as _td, timezone as _tz

from app.services.template_edit_limits import edit_allowance

_NOW = _dt(2026, 10, 17, 12, 0, tzinfo=_tz.utc)


def test_no_recent_edits_means_editing_is_allowed():
    a = edit_allowance([], _NOW)
    assert a["allowed"] and a["edits_30_days"] == 0 and a["limit_30_days"] == 10


def test_one_edit_in_the_last_24_hours_blocks_until_24_hours_after_it():
    a = edit_allowance([_NOW - _td(hours=2)], _NOW)
    assert not a["allowed"] and a["reason"] == "daily"
    assert a["next_allowed_at"] == (_NOW + _td(hours=22)).isoformat()


def test_ten_edits_in_30_days_block_until_the_oldest_drops_out():
    edits = [_NOW - _td(days=d) for d in range(2, 27, 2)][:10]  # 10 edits, none in the last 24h
    a = edit_allowance(edits, _NOW)
    assert not a["allowed"] and a["reason"] == "monthly"
    assert a["next_allowed_at"] == (min(edits) + _td(days=30)).isoformat()


def test_nine_edits_in_30_days_still_allow_one_more():
    a = edit_allowance([_NOW - _td(days=d) for d in range(2, 20, 2)], _NOW)  # 9 edits
    assert a["allowed"] and a["edits_30_days"] == 9


@pytest.mark.asyncio
async def test_second_edit_within_24_hours_is_blocked_before_reaching_meta():
    db = _DB([_template("APPROVED")])
    db.tables["template_edit_log"] = [{"tenant_id": "ten-1", "template_id": "t-1", "source": "anril",
                                       "edited_at": (_dt.now(_tz.utc) - _td(hours=1)).isoformat()}]
    meta = AsyncMock()
    with pytest.raises(HTTPException) as e:
        await _edit(db, meta=meta)
    assert "every 24 hours" in e.value.detail
    meta.assert_not_awaited()
    assert db.rows[0]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_an_approved_edit_is_logged_and_a_rejected_one_is_not():
    db = _DB([_template("APPROVED")])
    await _edit(db)
    assert [e["source"] for e in db.edits()] == ["anril"]
    db2 = _DB([_template("REJECTED")])
    await _edit(db2)
    assert db2.edits() == []  # Meta allows unlimited edits of rejected templates


def test_an_edit_made_in_whatsapp_manager_counts_toward_the_limit():
    db = _DB([_template("APPROVED", approved_at="2026-10-01T00:00:00+00:00")])
    tpl.apply_template_change(db, "message_template_components_update",
                              {"message_template_id": "meta-t-1", "message_template_element": "Hi"}, tenant_id="ten-1")
    assert [e["source"] for e in db.edits()] == ["meta_webhook"]


def test_metas_report_of_anrils_own_edit_is_not_counted_twice():
    db = _DB([_template("PENDING", approved_at="2026-10-01T00:00:00+00:00")])
    db.tables["template_edit_log"] = [{"tenant_id": "ten-1", "template_id": "t-1", "source": "anril",
                                       "edited_at": _dt.now(_tz.utc).isoformat()}]
    tpl.apply_template_change(db, "message_template_components_update",
                              {"message_template_id": "meta-t-1", "message_template_element": "Hi"}, tenant_id="ten-1")
    assert len(db.edits()) == 1
