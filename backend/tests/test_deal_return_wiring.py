"""R3 / D4, D6 wiring: the system prompt for a lead who comes back is built from the deal's idle
clock as it was BEFORE their message, the old greeting-keyword rule is gone, and an earlier
booking's details are offered back only from the same tenant's finished sessions."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services import ai_reply, intake
from tests.fake_supabase import FakeSupabase

CONFIG = {
    "enabled": True, "service_noun": "consultation",
    "fields": [{"key": "name", "label": "Full name", "type": "text"}],
    "packages": [{"key": "one_question", "name": "One Question", "amount_paise": 4900, "description": "x"}],
}
OPEN_DEAL = {
    "status": "awaiting_payment", "package_key": "one_question", "package_name": "One Question",
    "total_amount_paise": 4900, "amount_paise": 4900, "collected_data": {"name": "Vivek"}, "skipped_fields": [],
}


def _ago(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def _build(message, *, session, last_seen_at, db=None):
    db = db or FakeSupabase()
    with patch.object(ai_reply, "_build_base_prompt", return_value="BASE"), \
         patch.object(ai_reply, "_fetch_conversation_summary", return_value=""), \
         patch.object(ai_reply, "_fetch_call_context", return_value=None), \
         patch.object(ai_reply, "_resolve_reply_language_mode", return_value="mirror"), \
         patch("app.config_dynamic.get_setting", return_value=""), \
         patch("app.services.business_details.get_business_details", return_value={}), \
         patch.object(intake, "get_intake_config", return_value=CONFIG), \
         patch.object(intake, "_get_active_session", return_value=session):
        return ai_reply.build_reply_system_prompt(
            db, "lead-1", "t-1", {"phone": "+910000000000"}, message, "whatsapp",
            last_seen_at=last_seen_at, persist=False,
        )[0]


def test_a_lead_back_after_days_with_an_open_deal_gets_the_return_instruction():
    prompt = _build("hi", session=OPEN_DEAL, last_seen_at=_ago(days=4))
    assert "THE CUSTOMER IS BACK after 4 days" in prompt
    assert "Last message from them: 4 days ago" in prompt


def test_the_instruction_is_language_free_so_tamil_and_tanglish_reach_it_too():
    for message in ("வணக்கம்", "hi anna", "epdi irukku", "👍"):
        assert "THE CUSTOMER IS BACK" in _build(message, session=OPEN_DEAL, last_seen_at=_ago(days=2))


def test_a_bare_greeting_within_a_day_no_longer_triggers_it():
    assert "THE CUSTOMER IS BACK" not in _build("hi", session=OPEN_DEAL, last_seen_at=_ago(hours=3))


def test_no_open_deal_no_return_instruction():
    assert "THE CUSTOMER IS BACK" not in _build("hi", session=None, last_seen_at=_ago(days=9))


def test_an_unknown_idle_clock_asks_nothing():
    assert "THE CUSTOMER IS BACK" not in _build("hi", session=OPEN_DEAL, last_seen_at=None)


def test_earlier_booking_details_are_offered_for_confirmation_when_no_deal_is_open():
    db = FakeSupabase()
    db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="cancelled",
           package_name="One Question", collected_data={"name": "Vivek"})
    prompt = _build("i want another one", session=None, last_seen_at=None, db=db)
    assert "PREVIOUS BOOKING (their earlier" in prompt and "Full name = Vivek" in prompt


def test_no_previous_booking_block_while_a_deal_is_open():
    db = FakeSupabase()
    db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="cancelled",
           package_name="One Question", collected_data={"name": "Vivek"})
    assert "PREVIOUS BOOKING (their earlier" not in _build("hi", session=OPEN_DEAL, last_seen_at=None, db=db)


class TestPreviousBookingLookup:
    def test_is_scoped_to_the_tenant_and_the_lead(self):
        db = FakeSupabase()
        db.add("intake_sessions", tenant_id="t-2", lead_id="lead-1", status="cancelled", collected_data={"name": "Other"})
        db.add("intake_sessions", tenant_id="t-1", lead_id="lead-9", status="cancelled", collected_data={"name": "Other"})
        assert intake.previous_booking(db, "t-1", "lead-1") is None

    def test_skips_open_sessions_and_empty_ones(self):
        db = FakeSupabase()
        db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="cancelled", collected_data={"name": "Old"})
        db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="cancelled", collected_data={})
        db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="collecting", collected_data={"name": "Live"})
        assert intake.previous_booking(db, "t-1", "lead-1")["collected_data"] == {"name": "Old"}

    def test_never_raises(self):
        class Boom:
            def table(self, _):
                raise RuntimeError("db down")
        assert intake.previous_booking(Boom(), "t-1", "lead-1") is None


def test_the_clock_is_read_before_progress_writes_move_it():
    """generate_reply reads it first: capture_details -> _update_session then restarts it."""
    db = FakeSupabase()
    row = db.add("intake_sessions", tenant_id="t-1", lead_id="lead-1", status="collecting",
                 last_activity_at=_ago(days=4), collected_data={})
    original = row["last_activity_at"]
    before = intake.note_lead_message(db, "t-1", "lead-1")
    with patch.object(intake, "_sync_deal"):
        intake._update_session(row["id"], {"collected_data": {"name": "Vivek"}}, db)
    assert before == original
    assert db.rows("intake_sessions")[0]["last_activity_at"] > before


def test_a_message_restarts_the_clock_even_when_the_ai_will_not_reply():
    """A lead talking to a human (or AI switched off) is still active: the deal must not idle-close."""
    import asyncio

    db = FakeSupabase()
    db.add("leads", id="lead-1", tenant_id="t-1", ai_enabled=False, segment="C", phone="+910000000000")
    db.add("app_settings", tenant_id="t-1", key="ai_auto_reply_enabled", value="false")
    seen = []
    with patch.object(ai_reply, "get_supabase", return_value=db), \
         patch.object(intake, "note_lead_message", side_effect=lambda *a: seen.append(a) or None):
        asyncio.run(ai_reply.generate_reply(lead_id="lead-1", message="hello"))
    assert seen == [(db, "t-1", "lead-1")]


def test_a_blocked_lead_does_not_touch_anything():
    import asyncio

    db = FakeSupabase()
    db.add("leads", id="lead-1", tenant_id="t-1", blocked_at="2026-01-01T00:00:00+00:00")
    seen = []
    with patch.object(ai_reply, "get_supabase", return_value=db), \
         patch.object(intake, "note_lead_message", side_effect=lambda *a: seen.append(a) or None):
        asyncio.run(ai_reply.generate_reply(lead_id="lead-1", message="hello"))
    assert seen == []
