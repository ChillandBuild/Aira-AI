"""R3: a Deals-board card carries the link expiry, the lead's last activity and the
refund-needed flag, all in the one list query (a PostgREST embed of the linked intake session,
never one extra query per card)."""
from app.routes import deals
from tests.fake_supabase import FakeSupabase

ROW = {
    "id": "d1", "deal_number": 7, "stage": "awaiting_payment", "source": "form", "total_paise": 4900,
    "payment_link": None, "link_expires_at": "2026-10-04T12:32:00+00:00", "created_at": "2026-10-01T00:00:00+00:00",
    "lead_id": "lead-1", "leads": {"name": "Vivek", "phone": "+91"}, "deal_items": [],
    "intake_session_id": "s1",
    "intake_sessions": {"last_activity_at": "2026-10-02T09:00:00+00:00", "refund_needed": True},
}


def test_summary_has_the_three_board_fields():
    card = deals._summary(ROW)
    assert card["link_expires_at"] == "2026-10-04T12:32:00+00:00"
    assert card["last_activity_at"] == "2026-10-02T09:00:00+00:00"
    assert card["refund_needed"] is True


def test_the_list_query_embeds_the_linked_session_instead_of_fetching_it_per_card():
    assert "intake_sessions(last_activity_at, refund_needed)" in deals.DEAL_SELECT


def test_a_deal_without_a_session_gets_empty_values():
    card = deals._summary({**ROW, "intake_session_id": None, "intake_sessions": None})
    assert card["last_activity_at"] is None and card["refund_needed"] is False


def test_a_list_shaped_embed_is_read_too():
    card = deals._summary({**ROW, "intake_sessions": [ROW["intake_sessions"]]})
    assert card["refund_needed"] is True
    assert deals._summary({**ROW, "intake_sessions": []})["last_activity_at"] is None


def test_the_full_deal_still_shows_the_expiry_once():
    db = FakeSupabase()
    db.add("intake_sessions", id="s1", tenant_id="t1", collected_data={"name": "Vivek"})
    full = deals._full(ROW, db, "t1")
    assert full["link_expires_at"] == "2026-10-04T12:32:00+00:00"
    assert full["last_activity_at"] == "2026-10-02T09:00:00+00:00"
    assert full["intake_answers"] == {"name": "Vivek"}
