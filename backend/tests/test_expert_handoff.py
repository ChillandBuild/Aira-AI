import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.expert_handoff import public_router
from app.services import expert_handoff as eh


def _db_with_config(stored_json: str | None):
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": stored_json} if stored_json is not None else None
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    return db


def test_get_expert_handoff_config_returns_defaults_when_unset():
    db = _db_with_config(None)
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config == eh._DEFAULT_CONFIG


def test_get_expert_handoff_config_merges_stored_over_defaults():
    db = _db_with_config('{"enabled": true, "amount_paise": 2900}')
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config["enabled"] is True
    assert config["amount_paise"] == 2900
    assert config["fields"] == []  # default preserved


def test_save_expert_handoff_config_upserts_json_value():
    db = MagicMock()
    eh.save_expert_handoff_config("t-1", {"enabled": True, "amount_paise": 2900}, db=db)
    db.table.assert_called_with("app_settings")
    upsert_call = db.table.return_value.upsert
    upsert_call.assert_called_once()
    payload = upsert_call.call_args[0][0]
    assert payload["key"] == "expert_handoff_config"
    assert payload["tenant_id"] == "t-1"
    assert '"enabled": true' in payload["value"] or '"enabled":true' in payload["value"]


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_true_on_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": True})):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is True


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_false_on_no_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": False})):
        result = await eh.detect_expert_handoff_intent(
            "What are your opening hours?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_fails_closed_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


_FIELDS = [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "birthplace", "label": "Birthplace", "type": "text"},
]


def test_missing_field_labels_returns_unfilled_only():
    collected = {"name": "Priya"}
    assert eh.missing_field_labels(_FIELDS, collected) == ["Date of birth", "Birthplace"]


def test_missing_field_labels_empty_when_all_filled():
    collected = {"name": "Priya", "date_of_birth": "5 March 1995", "birthplace": "Chennai"}
    assert eh.missing_field_labels(_FIELDS, collected) == []


@pytest.mark.asyncio
async def test_extract_fields_merges_new_values_over_existing():
    llm_response = {"name": "Priya", "date_of_birth": "5 March 1995"}
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value=llm_response)):
        result = await eh.extract_fields(
            "I'm Priya, born 5 March 1995",
            fields=_FIELDS,
            collected_data={"birthplace": "Chennai"},  # already had this from an earlier turn
            tenant_id="t-1",
        )
    assert result == {"birthplace": "Chennai", "name": "Priya", "date_of_birth": "5 March 1995"}


@pytest.mark.asyncio
async def test_extract_fields_ignores_unknown_keys_from_llm():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"name": "Priya", "favorite_color": "blue"})):
        result = await eh.extract_fields("I'm Priya", fields=_FIELDS, collected_data={}, tenant_id="t-1")
    assert result == {"name": "Priya"}
    assert "favorite_color" not in result


@pytest.mark.asyncio
async def test_extract_fields_returns_unchanged_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.extract_fields("random unrelated text", fields=_FIELDS, collected_data={"name": "Priya"}, tenant_id="t-1")
    assert result == {"name": "Priya"}


def _session_db(existing_session=None, lead=None):
    """Builds a MagicMock db where .table('expert_handoff_sessions') and
    .table('leads') and .table('app_settings') and .table('messages') all
    behave plausibly for route_expert_handoff's queries."""
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            active_row = MagicMock()
            active_row.data = [existing_session] if existing_session else []
            t.select.return_value.eq.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = active_row

            insert_result = MagicMock()
            created = {**(existing_session or {}), "id": "sess-1", "status": "offer_pending", "collected_data": {}}
            insert_result.data = [created]
            t.insert.return_value.execute.return_value = insert_result

            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "app_settings":
            row = MagicMock()
            row.data = {"value": '{"enabled": true, "trigger_description": "personal question", "offer_message": "Talk to our expert?", "fields": [{"key": "name", "label": "Full name", "type": "text"}], "amount_paise": 2900}'}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
        elif name == "leads":
            row = MagicMock()
            row.data = lead or {"id": "lead-1", "ai_enabled": True}
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "messages":
            t.insert.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector
    return db


@pytest.mark.asyncio
async def test_route_expert_handoff_sends_offer_on_new_matching_intent():
    db = _session_db()
    with patch.object(eh, "detect_expert_handoff_intent", new=AsyncMock(return_value=True)), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is True
    send.assert_awaited_once()
    assert "Talk to our expert" in send.call_args[0][1]


@pytest.mark.asyncio
async def test_route_expert_handoff_ignores_when_feature_disabled():
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": '{"enabled": false}'}
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    active_row = MagicMock()
    active_row.data = []
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = active_row

    consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_expert_handoff_starts_collecting_on_affirmative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "yes, I'm Priya", db=db)
    assert consumed is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_expert_handoff_cancels_on_negative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "no thanks", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_expert_handoff_moves_to_confirmation_when_all_fields_filled():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "collecting", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "I'm Priya", db=db)
    assert consumed is True
    assert "Priya" in send.call_args[0][1]  # summary shown


@pytest.mark.asyncio
async def test_route_expert_handoff_sends_payment_link_on_confirmation_yes():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation", "collected_data": {"name": "Priya"}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "create_payment_link", new=AsyncMock(return_value={"payment_link_url": "https://rzp.io/x", "razorpay_payment_link_id": "plink_1"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "yes correct", db=db)
    assert consumed is True
    assert "https://rzp.io/x" in send.call_args[0][1]


_SESSION_ROW = {
    "id": "sess-1",
    "status": "awaiting_payment",
    "lead_id": "lead-1",
    "tenant_id": "t-1",
    "collected_data": {"name": "Priya"},
    "amount_paise": 19900,
    "trigger_reason": "Will I get married this year?",
}
_LEAD_ROW = {"id": "lead-1", "phone": "+919876543210", "name": "Priya"}


def _confirm_db(session_row=None, lead_row=None, claimed_rows=None):
    """db double for confirm_expert_handoff_payment: `claimed_rows` is what the
    conditional UPDATE ... eq(status, awaiting_payment) returns — [] means another
    concurrent webhook retry got there first."""
    session_row = _SESSION_ROW if session_row is None else session_row
    lead_row = _LEAD_ROW if lead_row is None else lead_row
    if claimed_rows is None:
        claimed_rows = [{**session_row, "status": "paid"}]

    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            claimed = MagicMock()
            claimed.data = claimed_rows
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value = claimed
        elif name == "leads":
            fetch = MagicMock()
            fetch.data = lead_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector
    return db


def test_confirm_expert_handoff_payment_keeps_ai_live_and_marks_paid():
    """AI must stay live post-payment (see _expert_handoff_paid_prompt_block in
    ai_reply.py) so a lead asking a follow-up question isn't met with silence
    while waiting for staff to see the notify_pool alert."""
    db = _confirm_db()

    result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)
    assert result["phone"] == "+919876543210"
    assert result["tenant_id"] == "t-1"
    assert result["lead_id"] == "lead-1"
    assert result["customer_name"] == "Priya"
    for call in db.table("leads").update.call_args_list:
        assert "ai_enabled" not in call.args[0]


def test_confirm_expert_handoff_payment_returns_session_and_lead_for_the_bridge_push():
    db = _confirm_db()
    result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)
    # astro_bridge.push_consultation(session, lead, tenant_id) needs all of these
    assert result["session"]["id"] == "sess-1"
    assert result["session"]["amount_paise"] == 19900
    assert result["session"]["trigger_reason"] == "Will I get married this year?"
    assert result["session"]["collected_data"] == {"name": "Priya"}
    assert result["lead"]["phone"] == "+919876543210"


def test_confirm_expert_handoff_payment_select_covers_every_field_the_push_needs():
    db = _confirm_db()
    eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)
    columns = db.table("expert_handoff_sessions").select.call_args[0][0]
    for needed in ("id", "status", "lead_id", "tenant_id", "collected_data", "amount_paise", "trigger_reason"):
        assert needed in columns


def test_confirm_expert_handoff_payment_update_is_gated_on_awaiting_payment():
    """Without the status filter on the UPDATE itself, two Razorpay retries both
    pass the read-then-write guard: double consultation, double charge."""
    db = _confirm_db()
    eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)

    sessions = db.table("expert_handoff_sessions")
    assert sessions.update.return_value.eq.call_args[0] == ("id", "sess-1")
    assert sessions.update.return_value.eq.return_value.eq.call_args[0] == ("status", "awaiting_payment")


def test_confirm_expert_handoff_payment_loses_the_race_when_update_matches_no_row():
    """The concurrent retry: the row still read as awaiting_payment, but the
    conditional UPDATE claimed nothing, so this caller must not confirm."""
    db = _confirm_db(claimed_rows=[])
    with patch.object(eh, "notify_pool") as notify:
        assert eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db) is None
    notify.assert_not_called()


def test_confirm_expert_handoff_payment_idempotent_when_already_paid():
    db = MagicMock()
    fetch = MagicMock()
    fetch.data = {"id": "sess-1", "status": "paid", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {}}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
    assert eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db) is None


def test_get_session_tenant_id_returns_tenant_for_known_session():
    db = MagicMock()
    row = MagicMock()
    row.data = {"tenant_id": "tenant-astro-tamil"}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    assert eh.get_session_tenant_id("9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b", db=db) == "tenant-astro-tamil"


def test_get_session_tenant_id_returns_none_for_unknown_session():
    db = MagicMock()
    row = MagicMock()
    row.data = None
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    assert eh.get_session_tenant_id("sess-nonexistent", db=db) is None


def test_confirm_expert_handoff_payment_notifies_staff_pool():
    db = _confirm_db()

    with patch.object(eh, "notify_pool") as notify:
        eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)

    notify.assert_called_once()
    args = notify.call_args[0]
    assert args[0] == "t-1"
    assert args[1] == "expert_handoff_paid"
    assert "Priya" in args[3]


def test_confirm_expert_handoff_payment_notify_failure_does_not_break_confirmation():
    db = _confirm_db()

    with patch.object(eh, "notify_pool", side_effect=RuntimeError("push service down")):
        result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)

    assert result["phone"] == "+919876543210"
    assert result["customer_name"] == "Priya"


def test_record_astro_bridge_ids_persists_django_ids_on_the_session():
    db = MagicMock()
    eh.record_astro_bridge_ids(
        "sess-1",
        "t-1",
        {"success": True, "question_id": 123, "horoscope_id": "HOR-AB12CD34", "astro_user_id": 456},
        db=db,
    )
    patch_payload = db.table.return_value.update.call_args[0][0]
    assert patch_payload == {
        "astro_question_id": 123,
        "astro_horoscope_id": "HOR-AB12CD34",
        "astro_user_id": 456,
    }


def test_record_astro_bridge_ids_skips_update_when_django_returned_nothing():
    db = MagicMock()
    eh.record_astro_bridge_ids("sess-1", "t-1", {"success": True}, db=db)
    db.table.return_value.update.assert_not_called()


def test_get_paid_unresolved_session_returns_session_when_paid():
    db = MagicMock()
    row = MagicMock()
    row.data = [{"id": "sess-1"}]
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value
        .eq.return_value.order.return_value.limit.return_value.execute.return_value
    ) = row
    assert eh.get_paid_unresolved_session("lead-1", "t-1", db=db) == {"id": "sess-1"}


def test_get_paid_unresolved_session_returns_none_when_no_paid_session():
    db = MagicMock()
    row = MagicMock()
    row.data = []
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value
        .eq.return_value.order.return_value.limit.return_value.execute.return_value
    ) = row
    assert eh.get_paid_unresolved_session("lead-1", "t-1", db=db) is None


def test_resolve_expert_handoff_session_transitions_paid_to_resolved():
    db = MagicMock()
    result = MagicMock()
    result.data = [{"id": "sess-1", "status": "resolved"}]
    (
        db.table.return_value.update.return_value.eq.return_value
        .eq.return_value.eq.return_value.execute.return_value
    ) = result
    assert eh.resolve_expert_handoff_session("sess-1", "t-1", db=db) is True


def test_resolve_expert_handoff_session_returns_false_when_not_paid():
    db = MagicMock()
    result = MagicMock()
    result.data = []
    (
        db.table.return_value.update.return_value.eq.return_value
        .eq.return_value.eq.return_value.execute.return_value
    ) = result
    assert eh.resolve_expert_handoff_session("sess-1", "t-1", db=db) is False


# --- Direction B: the astrologer's reply coming back from Django ---------------

_ASTRO_PAYLOAD = {
    "external_ref": "9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b",
    "question_id": 123,
    "reply_id": 789,
    "reply_text": "Jupiter favours you after May.",
    "reply_image_url": "https://spaces.example.com/replies/123/image_ab.jpg",
    "reply_voice_url": "https://spaces.example.com/replies/123/voice_cd.mp3",
    "astrologer_name": "Guru Swami",
    "replied_at": "2026-08-13T18:00:00Z",
}


def _hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _reply_db(session=None, lead=None, claimed=None, meta_number="1111111111"):
    """db double for deliver_astro_reply. `claimed` is what the conditional
    astro_last_reply_id UPDATE returns — [] means this reply_id was already handled."""
    session = {"id": "9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b", "lead_id": "lead-1", "tenant_id": "t-1", "astro_last_reply_id": None} if session is None else session
    lead = {"id": "lead-1", "phone": "+919876543210", "last_inbound_at": _hours_ago(2)} if lead is None else lead
    claimed = [{"id": "9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b"}] if claimed is None else claimed

    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            claimed_result = MagicMock()
            claimed_result.data = claimed
            t.update.return_value.eq.return_value.eq.return_value.or_.return_value.execute.return_value = claimed_result
        elif name == "leads":
            fetch = MagicMock()
            fetch.data = lead
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
        elif name == "phone_numbers":
            rows = MagicMock()
            rows.data = [{"meta_phone_number_id": meta_number}] if meta_number else []
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = rows
        elif name == "messages":
            t.insert.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector
    return db


@pytest.mark.asyncio
async def test_deliver_astro_reply_sends_text_then_image_then_voice():
    db = _reply_db()
    order = []

    async def fake_text(*a, **kw):
        order.append(("text", kw.get("phone_number_id")))
        return "wamid.text"

    async def fake_media(phone, url, wa_type, tenant_id, phone_number_id):
        order.append((wa_type, phone_number_id))
        return f"wamid.{wa_type}"

    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(side_effect=fake_text)), \
         patch.object(eh, "_send_astro_media", new=AsyncMock(side_effect=fake_media)):
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result == {"ok": True, "delivered": ["text", "image", "voice"], "failed": []}
    assert [kind for kind, _ in order] == ["text", "image", "audio"]
    assert {pid for _, pid in order} == {"1111111111"}


@pytest.mark.asyncio
async def test_deliver_astro_reply_logs_every_part_with_expert_handoff_reply_source():
    db = _reply_db()
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(return_value="wamid.text")), \
         patch.object(eh, "_send_astro_media", new=AsyncMock(return_value="wamid.media")):
        await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    rows = [c[0][0] for c in db.table("messages").insert.call_args_list]
    assert len(rows) == 3
    assert {r["reply_source"] for r in rows} == {"expert_handoff"}
    assert {r["direction"] for r in rows} == {"outbound"}
    assert {r["lead_id"] for r in rows} == {"lead-1"}
    assert rows[0]["content"] == "Jupiter favours you after May."
    assert rows[1]["content"] == _ASTRO_PAYLOAD["reply_image_url"]
    assert rows[2]["content"] == _ASTRO_PAYLOAD["reply_voice_url"]


@pytest.mark.asyncio
async def test_deliver_astro_reply_dedupes_on_reply_id():
    db = _reply_db(claimed=[])
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock()) as send, \
         patch.object(eh, "_send_astro_media", new=AsyncMock()) as media:
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result == {"ok": True, "duplicate": True}
    send.assert_not_awaited()
    media.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_astro_reply_claims_the_reply_id_before_sending_anything():
    db = _reply_db()
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(return_value="wamid.text")), \
         patch.object(eh, "_send_astro_media", new=AsyncMock(return_value="wamid.media")):
        await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    sessions = db.table("expert_handoff_sessions")
    assert sessions.update.call_args[0][0] == {"astro_last_reply_id": 789}
    or_filter = sessions.update.return_value.eq.return_value.eq.return_value.or_.call_args[0][0]
    # .lt (not .neq): a replayed OLDER reply after a newer one must also dedupe.
    assert or_filter == "astro_last_reply_id.is.null,astro_last_reply_id.lt.789"


@pytest.mark.asyncio
async def test_deliver_astro_reply_refuses_to_send_outside_the_24h_window():
    """Failing loudly beats the astrologer seeing 'delivered' while the customer gets nothing."""
    db = _reply_db(lead={"id": "lead-1", "phone": "+919876543210", "last_inbound_at": _hours_ago(30)})
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock()) as send, \
         patch.object(eh, "_send_astro_media", new=AsyncMock()) as media, \
         patch.object(eh, "notify_pool") as notify:
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result == {"ok": True, "delivered": [], "outside_24h_window": True}
    send.assert_not_awaited()
    media.assert_not_awaited()
    notify.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_astro_reply_treats_a_lead_that_never_messaged_as_outside_the_window():
    db = _reply_db(lead={"id": "lead-1", "phone": "+919876543210", "last_inbound_at": None})
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock()) as send, \
         patch.object(eh, "notify_pool"):
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result["outside_24h_window"] is True
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_astro_reply_skips_empty_text_and_absent_media():
    db = _reply_db()
    payload = {**_ASTRO_PAYLOAD, "reply_text": "", "reply_image_url": None}
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock()) as send, \
         patch.object(eh, "_send_astro_media", new=AsyncMock(return_value="wamid.media")) as media:
        result = await eh.deliver_astro_reply(payload, "t-1", db=db)

    assert result["delivered"] == ["voice"]
    send.assert_not_awaited()
    assert media.await_args[0][2] == "audio"


@pytest.mark.asyncio
async def test_deliver_astro_reply_still_sends_voice_when_image_upload_fails():
    db = _reply_db()

    async def flaky(phone, url, wa_type, tenant_id, phone_number_id):
        if wa_type == "image":
            raise RuntimeError("spaces 404")
        return "wamid.audio"

    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(return_value="wamid.text")), \
         patch.object(eh, "_send_astro_media", new=AsyncMock(side_effect=flaky)):
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result["delivered"] == ["text", "voice"]
    assert result["failed"] == ["image"]


@pytest.mark.asyncio
async def test_deliver_astro_reply_marks_text_failed_when_send_returns_no_message_id():
    db = _reply_db()
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(return_value=None)), \
         patch.object(eh, "_send_astro_media", new=AsyncMock(return_value="wamid.media")):
        result = await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)

    assert result["failed"] == ["text"]
    assert result["delivered"] == ["image", "voice"]
    assert len(db.table("messages").insert.call_args_list) == 2


@pytest.mark.asyncio
async def test_deliver_astro_reply_drops_a_reply_without_a_usable_reply_id():
    db = _reply_db()
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock()) as send:
        result = await eh.deliver_astro_reply({**_ASTRO_PAYLOAD, "reply_id": None}, "t-1", db=db)
    assert result["reason"] == "missing_reply_id"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_astro_reply_falls_back_to_tenant_default_number_when_pool_is_empty():
    db = _reply_db(meta_number=None)
    with patch("app.services.ai_reply.send_whatsapp", new=AsyncMock(return_value="wamid.text")) as send, \
         patch.object(eh, "_send_astro_media", new=AsyncMock(return_value="wamid.media")):
        await eh.deliver_astro_reply(_ASTRO_PAYLOAD, "t-1", db=db)
    assert send.await_args.kwargs["phone_number_id"] is None


def _fake_http_get(content: bytes = b"BYTES"):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx), client


@pytest.mark.asyncio
async def test_send_astro_media_downloads_then_uploads_to_meta_and_sends():
    client_factory, client = _fake_http_get(b"JPEGDATA")
    with patch("app.services.expert_handoff.httpx.AsyncClient", client_factory), \
         patch("app.services.meta_cloud.upload_media_to_meta", new=AsyncMock(return_value="media-1")) as upload, \
         patch("app.services.meta_cloud.send_media_message", new=AsyncMock(return_value={"messages": [{"id": "wamid.img"}]})) as send:
        mid = await eh._send_astro_media(
            "+919876543210", "https://x/replies/1/image_ab.jpg", "image", "t-1", "1111111111"
        )

    assert mid == "wamid.img"
    client.get.assert_awaited_once()
    assert upload.await_args.kwargs["file_bytes"] == b"JPEGDATA"
    assert upload.await_args.kwargs["mime_type"] == "image/jpeg"
    assert upload.await_args.kwargs["phone_number_id"] == "1111111111"
    assert send.await_args.kwargs["media_id"] == "media-1"
    assert send.await_args.kwargs["wa_type"] == "image"
    assert "caption" not in send.await_args.kwargs


@pytest.mark.asyncio
async def test_send_astro_media_sends_voice_as_audio_with_no_caption_or_filename():
    client_factory, _ = _fake_http_get(b"MP3DATA")
    with patch("app.services.expert_handoff.httpx.AsyncClient", client_factory), \
         patch("app.services.meta_cloud.upload_media_to_meta", new=AsyncMock(return_value="media-2")), \
         patch("app.services.meta_cloud.send_media_message", new=AsyncMock(return_value={"messages": [{"id": "wamid.aud"}]})) as send:
        await eh._send_astro_media(
            "+919876543210", "https://x/replies/1/voice_cd.mp3", "audio", "t-1", None
        )

    assert send.await_args.kwargs["wa_type"] == "audio"
    assert "caption" not in send.await_args.kwargs
    assert "filename" not in send.await_args.kwargs


def test_media_mime_maps_django_reply_urls_to_meta_accepted_types():
    assert eh._media_mime("https://x/replies/1/image_ab.jpg", "image") == ("image/jpeg", "reply.jpg")
    assert eh._media_mime("https://x/replies/1/image_ab.png", "image") == ("image/png", "reply.png")
    assert eh._media_mime("https://x/replies/1/image_ab.jpeg?sig=1", "image") == ("image/jpeg", "reply.jpg")
    assert eh._media_mime("https://x/replies/1/voice_cd.mp3", "audio") == ("audio/mpeg", "reply.mp3")
    assert eh._media_mime("https://x/replies/1/voice_cd.ogg", "audio") == ("audio/ogg", "reply.ogg")
    assert eh._media_mime("https://x/replies/1/voice_cd", "audio") == ("audio/mpeg", "reply.mp3")


# --- POST /api/v1/expert-handoff/astro-reply ----------------------------------

_SECRET = "s3cr3t"

_astro_app = FastAPI()
_astro_app.include_router(public_router, prefix="/api/v1/expert-handoff")
_astro_client = TestClient(_astro_app)


def _signed(body: bytes, secret: str = _SECRET) -> dict:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Astro-Signature": f"sha256={digest}", "Content-Type": "application/json"}


def test_astro_reply_route_accepts_a_correctly_signed_callback():
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=_SECRET), \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock(return_value={"ok": True, "delivered": ["text"], "failed": []})) as deliver:
        res = _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert deliver.await_args[0][1] == "t-1"


def test_astro_reply_route_rejects_a_bad_signature_with_401():
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=_SECRET), \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock()) as deliver:
        res = _astro_client.post(
            "/api/v1/expert-handoff/astro-reply",
            content=body,
            headers={"X-Astro-Signature": "sha256=deadbeef", "Content-Type": "application/json"},
        )

    assert res.status_code == 401
    assert res.json() == {"error": "Unauthorized", "code": "unauthorized"}
    deliver.assert_not_awaited()


def test_astro_reply_route_verifies_against_the_signing_tenants_own_secret():
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="tenant-astro-tamil") as get_tenant, \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=_SECRET) as secret, \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock(return_value={"ok": True})):
        _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))

    get_tenant.assert_called_once_with("9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b")
    secret.assert_called_once_with("tenant-astro-tamil")


def test_astro_reply_route_returns_the_same_401_for_an_unknown_external_ref():
    """Unknown session and bad signature must be indistinguishable — otherwise the
    endpoint is an oracle for which session ids exist."""
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value=None), \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock()) as deliver:
        res = _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))

    assert res.status_code == 401
    assert res.json() == {"error": "Unauthorized", "code": "unauthorized"}
    deliver.assert_not_awaited()


def test_astro_reply_route_signs_over_the_exact_raw_bytes_not_a_reserialised_body():
    """Django signs the bytes it puts on the wire; re-serialising the parsed JSON
    changes whitespace and key order and would fail every real callback."""
    body = b'{"external_ref": "9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b",   "reply_id": 789,\n  "reply_text": "hi"}'
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=_SECRET), \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock(return_value={"ok": True})):
        res = _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))

    assert res.status_code == 200


def test_astro_reply_route_rejects_a_body_that_is_not_json():
    body = b"not json at all"
    res = _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_json"


def test_astro_reply_route_rejects_a_missing_signature_header():
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=_SECRET):
        res = _astro_client.post(
            "/api/v1/expert-handoff/astro-reply", content=body, headers={"Content-Type": "application/json"}
        )
    assert res.status_code == 401


def test_astro_reply_route_rejects_when_the_tenant_has_no_bridge_secret_configured():
    body = json.dumps(_ASTRO_PAYLOAD).encode()
    with patch("app.routes.expert_handoff.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.expert_handoff.astro_bridge.get_bridge_secret", return_value=None), \
         patch("app.routes.expert_handoff.deliver_astro_reply", new=AsyncMock()) as deliver:
        res = _astro_client.post("/api/v1/expert-handoff/astro-reply", content=body, headers=_signed(body))
    assert res.status_code == 401
    deliver.assert_not_awaited()
