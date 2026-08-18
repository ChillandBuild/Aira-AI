import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import intake as eh


def _db_with_config(stored_json: str | None):
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": stored_json} if stored_json is not None else None
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    return db


def test_get_intake_config_returns_defaults_when_unset():
    db = _db_with_config(None)
    config = eh.get_intake_config("t-1", db=db)
    assert config == eh._DEFAULT_CONFIG


def test_get_intake_config_merges_stored_over_defaults():
    db = _db_with_config('{"enabled": true, "amount_paise": 2900}')
    config = eh.get_intake_config("t-1", db=db)
    assert config["enabled"] is True
    assert config["amount_paise"] == 2900
    assert config["fields"] == []  # default preserved
    assert config["service_noun"] == "consultation"  # default preserved


def test_save_intake_config_upserts_json_value():
    db = MagicMock()
    eh.save_intake_config("t-1", {"enabled": True, "amount_paise": 2900}, db=db)
    db.table.assert_called_with("app_settings")
    upsert_call = db.table.return_value.upsert
    upsert_call.assert_called_once()
    payload = upsert_call.call_args[0][0]
    assert payload["key"] == "intake_config"
    assert payload["tenant_id"] == "t-1"
    assert '"enabled": true' in payload["value"] or '"enabled":true' in payload["value"]


@pytest.mark.asyncio
async def test_detect_intake_intent_true_on_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": True})):
        result = await eh.detect_intake_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is True


@pytest.mark.asyncio
async def test_detect_intake_intent_false_on_no_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": False})):
        result = await eh.detect_intake_intent(
            "What are your opening hours?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


@pytest.mark.asyncio
async def test_detect_intake_intent_fails_closed_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.detect_intake_intent(
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
    """Builds a MagicMock db where .table('intake_sessions') and
    .table('leads') and .table('app_settings') and .table('messages') all
    behave plausibly for route_intake's queries."""
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "intake_sessions":
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
            # Single legacy amount_paise (no "packages" list) so the tests below
            # exercise the single-package short-circuit path, matching the
            # pre-packages flow they were written against.
            row.data = {"value": '{"enabled": true, "trigger_description": "personal question", "offer_message": "Talk to our expert?", "fields": [{"key": "name", "label": "Full name", "type": "text"}], "amount_paise": 2900, "service_noun": "consultation"}'}
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
async def test_route_intake_sends_offer_on_new_matching_intent():
    db = _session_db()
    with patch.object(eh, "detect_intake_intent", new=AsyncMock(return_value=True)), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is True
    send.assert_awaited_once()
    assert "Talk to our expert" in send.call_args[0][1]


@pytest.mark.asyncio
async def test_route_intake_ignores_when_feature_disabled():
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": '{"enabled": false}'}
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    active_row = MagicMock()
    active_row.data = []
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = active_row

    consumed = await eh.route_intake("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_intake_starts_collecting_on_affirmative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "yes, I'm Priya", db=db)
    assert consumed is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_intake_cancels_on_negative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    consumed = await eh.route_intake("lead-1", "t-1", "+91999", "no thanks", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_intake_snapshots_the_single_package_on_offer_acceptance():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()):
        await eh.route_intake("lead-1", "t-1", "+91999", "yes", db=db)
    update_patch = db.table("intake_sessions").update.call_args[0][0]
    assert update_patch["package_key"] == "standard"
    assert update_patch["package_amount_paise"] == 2900


@pytest.mark.asyncio
async def test_route_intake_moves_to_confirmation_when_all_fields_filled():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "collecting", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "I'm Priya", db=db)
    assert consumed is True
    assert "Priya" in send.call_args[0][1]  # summary shown


@pytest.mark.asyncio
async def test_route_intake_sends_payment_link_on_confirmation_yes():
    session = {
        "id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation",
        "collected_data": {"name": "Priya"}, "package_amount_paise": 2900,
    }
    db = _session_db(existing_session=session)
    with patch.object(eh, "create_payment_link", new=AsyncMock(return_value={"payment_link_url": "https://rzp.io/x", "razorpay_payment_link_id": "plink_1"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "yes correct", db=db)
    assert consumed is True
    assert "https://rzp.io/x" in send.call_args[0][1]


@pytest.mark.asyncio
async def test_route_intake_falls_back_gracefully_with_no_package_amount():
    session = {
        "id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation",
        "collected_data": {"name": "Priya"}, "package_amount_paise": None,
    }
    db = _session_db(existing_session=session)
    with patch.object(eh, "create_payment_link", new=AsyncMock()) as create_link, \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "yes correct", db=db)
    assert consumed is True
    create_link.assert_not_called()
    assert "team will send the payment link" in send.call_args[0][1]


_SESSION_ROW = {
    "id": "sess-1",
    "status": "awaiting_payment",
    "lead_id": "lead-1",
    "tenant_id": "t-1",
    "collected_data": {"name": "Priya"},
    "package_amount_paise": 2900,
    "amount_paise": 2900,
    "trigger_reason": "Will I get married this year?",
}
_LEAD_ROW = {"id": "lead-1", "phone": "+919876543210", "name": "Priya"}


def _confirm_db(session_row=None, lead_row=None, claimed_rows=None):
    """db double for confirm_intake_payment: `claimed_rows` is what the
    conditional UPDATE ... neq(status, paid) returns — [] means another
    concurrent webhook retry got there first."""
    session_row = _SESSION_ROW if session_row is None else session_row
    lead_row = _LEAD_ROW if lead_row is None else lead_row
    if claimed_rows is None:
        claimed_rows = [{**session_row, "status": "paid"}]

    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "intake_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            claimed = MagicMock()
            claimed.data = claimed_rows
            t.update.return_value.eq.return_value.neq.return_value.execute.return_value = claimed
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


def test_confirm_intake_payment_keeps_ai_live_and_marks_paid():
    """AI must stay live post-payment (see _intake_paid_prompt_block in
    ai_reply.py) so a lead asking a follow-up question isn't met with silence
    while waiting for staff to see the notify_pool alert."""
    db = _confirm_db()

    result = eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)
    assert result["phone"] == "+919876543210"
    assert result["tenant_id"] == "t-1"
    assert result["lead_id"] == "lead-1"
    assert result["customer_name"] == "Priya"
    for call in db.table("leads").update.call_args_list:
        assert "ai_enabled" not in call.args[0]


def test_confirm_intake_payment_returns_session_and_lead_for_the_bridge_push():
    db = _confirm_db()
    result = eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)
    # astro_bridge.push_consultation(session, lead, tenant_id) needs all of these
    assert result["session"]["id"] == "sess-1"
    assert result["session"]["amount_paise"] == 2900
    assert result["session"]["trigger_reason"] == "Will I get married this year?"
    assert result["session"]["collected_data"] == {"name": "Priya"}
    assert result["lead"]["phone"] == "+919876543210"


def test_confirm_intake_payment_select_covers_every_field_the_push_needs():
    db = _confirm_db()
    eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)
    columns = db.table("intake_sessions").select.call_args[0][0]
    for needed in ("id", "status", "lead_id", "tenant_id", "collected_data", "trigger_reason"):
        assert needed in columns


def test_confirm_intake_payment_update_is_gated_on_not_already_paid():
    """Without the status filter on the UPDATE itself, two Razorpay retries both
    pass the read-then-write guard: double consultation, double charge."""
    db = _confirm_db()
    eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)

    sessions = db.table("intake_sessions")
    assert sessions.update.return_value.eq.call_args[0] == ("id", "sess-1")
    assert sessions.update.return_value.eq.return_value.neq.call_args[0] == ("status", "paid")


def test_confirm_intake_payment_loses_the_race_when_update_matches_no_row():
    """The concurrent retry: the row still read as awaiting_payment, but the
    conditional UPDATE claimed nothing, so this caller must not confirm."""
    db = _confirm_db(claimed_rows=[])
    with patch.object(eh, "notify_pool") as notify:
        assert eh.confirm_intake_payment("sess-1", "pay_abc123", db=db) is None
    notify.assert_not_called()


def test_confirm_intake_payment_idempotent_when_already_paid():
    db = MagicMock()
    fetch = MagicMock()
    fetch.data = {"id": "sess-1", "status": "paid", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {}}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
    assert eh.confirm_intake_payment("sess-1", "pay_abc123", db=db) is None


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
    assert eh.get_session_tenant_id("9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b", db=db) is None


def test_get_session_tenant_id_rejects_a_non_uuid_ref_without_touching_the_db():
    """The id column is uuid-typed: a non-uuid ref reaching PostgREST raises an
    APIError, which on the public astro-reply route would surface as a 500
    instead of the intended 401."""
    db = MagicMock()
    assert eh.get_session_tenant_id("sess-nonexistent", db=db) is None
    db.table.assert_not_called()


def test_get_session_tenant_id_strips_the_followup_suffix():
    db = MagicMock()
    row = MagicMock()
    row.data = {"tenant_id": "tenant-astro-tamil"}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    sid = "9c3e0a1b-4d5e-4f60-8a7b-1c2d3e4f5a6b"
    assert eh.get_session_tenant_id(f"{sid}::f3", db=db) == "tenant-astro-tamil"
    assert db.table.return_value.select.return_value.eq.call_args[0] == ("id", sid)


def test_confirm_intake_payment_notifies_staff_pool():
    db = _confirm_db()

    with patch.object(eh, "notify_pool") as notify:
        eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)

    notify.assert_called_once()
    args = notify.call_args[0]
    assert args[0] == "t-1"
    assert args[1] == "intake_paid"
    assert "Priya" in args[3]


def test_confirm_intake_payment_notify_failure_does_not_break_confirmation():
    db = _confirm_db()

    with patch.object(eh, "notify_pool", side_effect=RuntimeError("push service down")):
        result = eh.confirm_intake_payment("sess-1", "pay_abc123", db=db)

    assert result["phone"] == "+919876543210"
    assert result["customer_name"] == "Priya"


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


def test_resolve_intake_session_transitions_paid_to_resolved():
    db = MagicMock()
    result = MagicMock()
    result.data = [{"id": "sess-1", "status": "resolved"}]
    (
        db.table.return_value.update.return_value.eq.return_value
        .eq.return_value.eq.return_value.execute.return_value
    ) = result
    assert eh.resolve_intake_session("sess-1", "t-1", db=db) is True


def test_resolve_intake_session_returns_false_when_not_paid():
    db = MagicMock()
    result = MagicMock()
    result.data = []
    (
        db.table.return_value.update.return_value.eq.return_value
        .eq.return_value.eq.return_value.execute.return_value
    ) = result
    assert eh.resolve_intake_session("sess-1", "t-1", db=db) is False


@pytest.mark.parametrize("status", ["awaiting_package_choice", "collecting", "awaiting_confirmation", "awaiting_payment"])
def test_get_in_progress_session_matches_in_progress_statuses(status):
    db = MagicMock()
    row = MagicMock()
    row.data = [{"id": "sess-1", "status": status}]
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value
        .order.return_value.limit.return_value.execute.return_value
    ) = row
    assert eh.get_in_progress_session("lead-1", "t-1", db=db) == {"id": "sess-1", "status": status}


@pytest.mark.parametrize("status", ["offer_pending", "paid", "resolved", "cancelled"])
def test_get_in_progress_session_returns_none_for_other_statuses(status):
    db = MagicMock()
    row = MagicMock()
    row.data = [{"id": "sess-1", "status": status}]
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value
        .order.return_value.limit.return_value.execute.return_value
    ) = row
    assert eh.get_in_progress_session("lead-1", "t-1", db=db) is None


def test_get_in_progress_session_returns_none_when_no_session():
    db = MagicMock()
    row = MagicMock()
    row.data = []
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value
        .order.return_value.limit.return_value.execute.return_value
    ) = row
    assert eh.get_in_progress_session("lead-1", "t-1", db=db) is None


@pytest.mark.asyncio
async def test_awaiting_confirmation_correction_updates_summary_instead_of_falling_through():
    """Live evidence 2026-08-13: a lead replied 'Time of birth is 6:30 am' to the
    summary instead of a plain yes. That's correctly not a yes, but the old code
    dropped the session entirely and let the AI answer with no context, which
    redirected the lead to the app instead of resuming the ₹29 payment flow they
    were one message from completing."""
    session = {
        "id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation",
        "collected_data": {"name": "Priya"}, "package_amount_paise": 2900, "skipped_fields": ["name"],
    }
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya Kumar"})), \
         patch.object(eh, "create_payment_link", new=AsyncMock()) as create_link, \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "actually it's Priya Kumar", db=db)
    assert consumed is True
    create_link.assert_not_called()
    assert "Priya Kumar" in send.call_args[0][1]
    update_patch = db.table("intake_sessions").update.call_args[0][0]
    assert update_patch["collected_data"]["name"] == "Priya Kumar"
    assert update_patch["skipped_fields"] == []


@pytest.mark.asyncio
async def test_awaiting_confirmation_unrelated_reply_still_falls_through_to_ai():
    session = {
        "id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation",
        "collected_data": {"name": "Priya"}, "package_amount_paise": 2900,
    }
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_intake("lead-1", "t-1", "+91999", "when will the astrologer reply?", db=db)
    assert consumed is False
    send.assert_not_awaited()
    db.table("intake_sessions").update.assert_not_called()
