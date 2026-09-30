"""R3 / D4, D6: what the AI is told about a lead who comes back to an open deal. Pure prompt
text: the model judges the meaning of the message (any language), code only supplies the
facts (how long they were away, when the link expires) and the instruction."""
from datetime import datetime, timedelta, timezone

from app.services import deal_engine

CONFIG = {
    "enabled": True,
    "service_noun": "consultation",
    "fields": [{"key": "name", "label": "Full name", "type": "text"}],
    "packages": [
        {"key": "one_question", "name": "One Question", "amount_paise": 4900, "description": "x"},
        {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900, "description": "y"},
    ],
}
NOW = datetime(2026, 10, 3, 12, 30, tzinfo=timezone.utc)


def _ago(**delta) -> datetime:
    return NOW - timedelta(**delta)


def _session(**extra) -> dict:
    return {
        "status": "awaiting_payment", "package_key": "one_question", "package_name": "One Question",
        "total_amount_paise": 4900, "amount_paise": 4900, "collected_data": {"name": "Vivek"},
        "skipped_fields": [], **extra,
    }


def _prompt(session, last_seen, **kw) -> str:
    return deal_engine.deal_prompt(CONFIG, session, last_seen_at=last_seen, now=NOW, **kw)


class TestAwayLine:
    def test_days_away(self):
        state = deal_engine.deal_state_block(CONFIG, _session(), last_seen_at=_ago(days=4, hours=2), now=NOW)
        assert "Last message from them: 4 days ago" in state

    def test_hours_away(self):
        state = deal_engine.deal_state_block(CONFIG, _session(), last_seen_at=_ago(hours=5, minutes=10), now=NOW)
        assert "Last message from them: 5 hours ago" in state

    def test_a_minute_ago_reads_as_just_now(self):
        state = deal_engine.deal_state_block(CONFIG, _session(), last_seen_at=_ago(minutes=1), now=NOW)
        assert "just now" in state

    def test_accepts_a_supabase_timestamp_string(self):
        stamp = _ago(days=2, hours=1).strftime("%Y-%m-%d %H:%M:%S+00")
        assert "2 days ago" in deal_engine.deal_state_block(CONFIG, _session(), last_seen_at=stamp, now=NOW)

    def test_no_away_line_without_a_last_seen_value(self):
        assert "Last message from them" not in deal_engine.deal_state_block(CONFIG, _session(), now=NOW)


class TestLinkExpiryLine:
    def test_a_live_link_shows_its_expiry_in_indian_time(self):
        session = _session(payment_link="https://rzp.io/x", payment_link_expires_at="2026-10-04T12:32:00+00:00")
        state = deal_engine.deal_state_block(CONFIG, session, now=NOW)
        assert "valid till 4 Oct, 6:02 PM IST" in state

    def test_an_expired_link_is_reported_and_a_new_one_promised(self):
        session = _session(payment_link=None, razorpay_payment_link_id="plink_1")
        state = deal_engine.deal_state_block(CONFIG, session, now=NOW)
        assert "expired" in state.lower()
        assert "new one will be made" in state

    def test_a_stored_link_past_its_expiry_says_when_it_expired(self):
        session = _session(payment_link="https://rzp.io/x", payment_link_expires_at="2026-10-02T12:32:00+00:00")
        state = deal_engine.deal_state_block(CONFIG, session, now=NOW)
        assert "expired" in state.lower() and "2 Oct, 6:02 PM IST" in state
        assert "new one will be made" in state

    def test_no_link_yet_is_not_called_expired(self):
        state = deal_engine.deal_state_block(CONFIG, _session(status="collecting", payment_link=None), now=NOW)
        assert "expired" not in state.lower()


class TestReturningInstruction:
    def test_appears_after_a_day_away_with_an_open_deal(self):
        prompt = _prompt(_session(), _ago(days=4))
        assert "THE CUSTOMER IS BACK" in prompt
        assert "One Question" in prompt.split("THE CUSTOMER IS BACK")[1]
        assert "₹49" in prompt.split("THE CUSTOMER IS BACK")[1]
        assert "something else" in prompt.split("THE CUSTOMER IS BACK")[1]

    def test_the_model_judges_intent_and_asks_when_unsure(self):
        note = _prompt(_session(), _ago(days=4)).split("THE CUSTOMER IS BACK")[1]
        assert "clear intent" in note
        assert "unsure" in note.lower()

    def test_not_shown_under_24_hours(self):
        assert "THE CUSTOMER IS BACK" not in _prompt(_session(), _ago(hours=23, minutes=59))

    def test_shown_at_exactly_24_hours(self):
        assert "THE CUSTOMER IS BACK" in _prompt(_session(), _ago(hours=24))

    def test_not_shown_without_an_open_deal(self):
        assert "THE CUSTOMER IS BACK" not in _prompt(None, _ago(days=9))
        assert "THE CUSTOMER IS BACK" not in _prompt({"status": "offer_pending"}, _ago(days=9))

    def test_not_shown_for_a_paid_deal(self):
        assert "THE CUSTOMER IS BACK" not in _prompt(_session(status="paid"), _ago(days=9))

    def test_not_shown_when_the_away_time_is_unknown(self):
        assert "THE CUSTOMER IS BACK" not in _prompt(_session(), None)

    def test_a_bare_greeting_alone_no_longer_triggers_it(self):
        """The old rule keyed on the words 'hi'/blank; the new one keys on time away only."""
        assert "THE CUSTOMER IS BACK" not in _prompt(_session(), _ago(hours=2))


class TestCloseDealTool:
    def _tool(self):
        return next(t["function"] for t in deal_engine.deal_tools(CONFIG) if t["function"]["name"] == "close_deal")

    def test_is_a_deal_tool(self):
        assert deal_engine.TOOL_CLOSE_DEAL == "close_deal"
        assert "close_deal" in deal_engine.DEAL_TOOL_NAMES

    def test_description_demands_an_explicit_decline_and_names_the_non_declines(self):
        text = self._tool()["description"].lower()
        assert "explicit" in text
        for not_a_decline in ("later", "will think", "yosichu solren", "silence"):
            assert not_a_decline in text
        for decline in ("venam", "not interested", "cancel it"):
            assert decline in text

    def test_handover_only_replies_do_not_get_it(self):
        assert all(t["function"]["name"] != "close_deal" for t in deal_engine.handover_tools())


class TestNewBookingAndPreviousDetails:
    def test_select_offering_can_flag_a_separate_booking(self):
        tool = next(t["function"] for t in deal_engine.deal_tools(CONFIG) if t["function"]["name"] == "select_offering")
        assert tool["parameters"]["properties"]["new_booking"]["type"] == "boolean"
        assert "new_booking" not in tool["parameters"]["required"]

    def test_previous_details_are_shown_for_confirmation_never_for_silent_reuse(self):
        block = deal_engine.previous_details_block(CONFIG, {"package_name": "One Question", "collected_data": {"name": "Vivek"}})
        assert "name = Vivek" in block
        assert "confirm or correct" in block
        assert "never reuse" in block.lower()

    def test_no_previous_details_no_block(self):
        assert deal_engine.previous_details_block(CONFIG, None) == ""
        assert deal_engine.previous_details_block(CONFIG, {"collected_data": {}}) == ""

    def test_the_prompt_carries_the_previous_details_block(self):
        prompt = _prompt(None, None, previous_details={"package_name": "One Question", "collected_data": {"name": "Vivek"}})
        assert "PREVIOUS BOOKING" in prompt
