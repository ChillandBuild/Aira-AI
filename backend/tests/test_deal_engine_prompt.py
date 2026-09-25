"""Prompt blocks and tool schemas for the AI-native deal engine (services/deal_engine.py).

Design: docs/plans/ai-native-conversation.md. Everything here is pure: config in, text out.
"""
from app.services import deal_engine

CONFIG = {
    "enabled": True,
    "service_noun": "consultation",
    "fields": [
        {"key": "name", "label": "Full name", "type": "text"},
        {"key": "birth_date", "label": "Date of birth", "type": "date"},
    ],
    "packages": [
        {"key": "one_question", "name": "One Question", "amount_paise": 4900,
         "description": "Simple question", "button_label": "49 Rs"},
        {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900,
         "description": "Life situation", "active": True,
         "addons": [{"key": "report", "name": "Written report", "amount_paise": 2000}]},
        {"key": "retired", "name": "Old Package", "amount_paise": 100, "active": False},
    ],
}


NO_DETAILS_CONFIG = {**CONFIG, "fields": []}


class TestIsEnabled:
    def test_needs_enabled_flag_and_an_active_package(self):
        assert deal_engine.is_enabled(CONFIG)
        assert not deal_engine.is_enabled({**CONFIG, "enabled": False})
        assert not deal_engine.is_enabled({**CONFIG, "packages": [], "amount_paise": 0})


class TestOfferingsBlock:
    def test_lists_active_offerings_with_config_prices(self):
        block = deal_engine.offerings_block(CONFIG)
        assert "One Question" in block and "₹49" in block
        assert "Detailed Question" in block and "₹99" in block
        assert "Written report" in block and "+₹20" in block

    def test_hides_inactive_offerings(self):
        assert "Old Package" not in deal_engine.offerings_block(CONFIG)

    def test_shows_button_label_and_key(self):
        block = deal_engine.offerings_block(CONFIG)
        assert "one_question" in block and "49 Rs" in block


class TestRequiredDetailsBlock:
    def test_lists_fields_from_config(self):
        block = deal_engine.required_details_block(CONFIG["fields"])
        assert "name" in block and "Full name" in block and "birth_date" in block

    def test_says_none_needed_when_no_fields(self):
        assert "none" in deal_engine.required_details_block([]).lower()


class TestDealState:
    def test_no_session_means_nothing_chosen(self):
        state = deal_engine.deal_state_block(CONFIG, None)
        assert "nothing chosen yet" in state.lower()

    def test_shows_missing_details_and_payment_not_sent(self):
        session = {
            "status": "collecting", "package_key": "one_question", "package_name": "One Question",
            "total_amount_paise": 4900, "collected_data": {"name": "Ravi"}, "skipped_fields": [],
        }
        state = deal_engine.deal_state_block(CONFIG, session)
        assert "One Question" in state and "₹49" in state
        assert "name = Ravi" in state
        assert "birth_date" in state.split("still needed")[1]
        assert "not sent" in state.lower()

    def test_skipped_detail_is_not_counted_as_missing(self):
        session = {
            "status": "collecting", "package_key": "one_question", "package_name": "One Question",
            "total_amount_paise": 4900, "collected_data": {"name": "Ravi"}, "skipped_fields": ["birth_date"],
        }
        state = deal_engine.deal_state_block(CONFIG, session)
        assert "ready for the payment link" in state.lower()

    def test_paid_session_says_paid(self):
        session = {"status": "paid", "package_key": "one_question", "package_name": "One Question",
                   "total_amount_paise": 4900, "collected_data": {}, "skipped_fields": []}
        assert "PAID" in deal_engine.deal_state_block(CONFIG, session)

    def test_link_sent_but_unpaid(self):
        session = {"status": "awaiting_payment", "package_key": "one_question", "package_name": "One Question",
                   "total_amount_paise": 4900, "amount_paise": 4900, "payment_link": "https://rzp.io/l/x",
                   "collected_data": {"name": "R", "birth_date": "1"}, "skipped_fields": []}
        state = deal_engine.deal_state_block(CONFIG, session)
        assert "link sent" in state.lower() and "not paid" in state.lower()
        assert "https://rzp.io" not in state  # the model must never see a URL it could copy


class TestMissingDetails:
    def test_missing_excludes_collected_and_skipped(self):
        fields = CONFIG["fields"]
        assert deal_engine.missing_details(fields, {"name": "R"}, []) == ["birth_date"]
        assert deal_engine.missing_details(fields, {"name": "R"}, ["birth_date"]) == []
        assert deal_engine.missing_details(fields, {}, []) == ["name", "birth_date"]
        assert deal_engine.missing_details([], {}, []) == []


class TestRules:
    def test_offerings_override_stale_knowledge_prices(self):
        prompt = deal_engine.deal_prompt(CONFIG, None)
        assert "OFFERINGS is right" in prompt

    def test_no_details_means_link_in_the_same_turn_as_selection(self):
        prompt = deal_engine.deal_prompt(NO_DETAILS_CONFIG, None)
        assert "same turn, right after select_offering" in prompt and "REQUIRED DETAILS: none" in prompt

    def test_sells_in_chat_instead_of_pointing_to_the_app(self):
        assert "right here in this chat" in deal_engine.deal_prompt(CONFIG, None)

    def test_returning_customer_continues_from_the_deal_state(self):
        assert "continue from exactly where it" in deal_engine.deal_prompt(CONFIG, None)

    def test_handover_line_is_not_repeated_word_for_word(self):
        assert "do not repeat that line word for word" in deal_engine.deal_prompt(CONFIG, None)

    def test_tapped_option_is_called_out(self):
        assert "one_question" in deal_engine.deal_prompt(CONFIG, None, tapped_key="one_question")

    def test_prompt_never_contains_a_url(self):
        session = {"status": "awaiting_payment", "package_key": "one_question", "package_name": "One Question",
                   "total_amount_paise": 4900, "amount_paise": 4900, "payment_link": "https://rzp.io/l/x",
                   "collected_data": {}, "skipped_fields": []}
        assert "https://" not in deal_engine.deal_prompt(CONFIG, session)


class TestTools:
    def test_tool_names_are_the_contract(self):
        names = {t["function"]["name"] for t in deal_engine.deal_tools(CONFIG)}
        assert names == {
            "show_options", "select_offering", "save_details", "skip_detail",
            "create_payment_link", "hand_to_human",
        }

    def test_select_offering_key_is_limited_to_active_configured_keys(self):
        tools = {t["function"]["name"]: t for t in deal_engine.deal_tools(CONFIG)}
        enum = tools["select_offering"]["function"]["parameters"]["properties"]["key"]["enum"]
        assert enum == ["one_question", "detailed"]

    def test_save_details_has_no_amount_or_url_parameter(self):
        tools = {t["function"]["name"]: t for t in deal_engine.deal_tools(CONFIG)}
        params = tools["create_payment_link"]["function"]["parameters"]["properties"]
        assert params == {}


class TestUnknownPrices:
    def test_offering_prices_are_fine(self):
        assert deal_engine.unknown_prices("One Question is ₹49 and Detailed is ₹99.", CONFIG, "") == []

    def test_offering_plus_addon_total_is_fine(self):
        assert deal_engine.unknown_prices("With the report that is ₹119 in total.", CONFIG, "") == []

    def test_stale_price_is_flagged(self):
        assert deal_engine.unknown_prices("Consultations start at ₹29.", CONFIG, "") == [29.0]

    def test_button_style_amount_is_recognised(self):
        assert deal_engine.unknown_prices("Try the 75 Rs plan", CONFIG, "") == [75.0]

    def test_amount_the_customer_just_said_may_be_repeated(self):
        assert deal_engine.unknown_prices("Sorry, I cannot do ₹20.", CONFIG, "can you do 20 rupees") == []

    def test_words_ending_in_rs_are_not_rupees(self):
        text = "Covers 11th and 12th, offers 3 batches, hours 7 to 12"
        assert deal_engine.unknown_prices(text, CONFIG, "") == []

    def test_text_without_prices_is_clean(self):
        assert deal_engine.unknown_prices("Vanakkam! How can I help?", CONFIG, "") == []

    def test_a_lone_comma_in_the_message_does_not_crash(self):
        assert deal_engine.unknown_prices("Fine", CONFIG, "Ravi, born 1994, 6:30") == []


class TestRefundRequests:
    def test_refund_and_cancel_requests_count_as_payment_concerns(self):
        for msg in ("I want refund, I changed my mind", "give my money back", "cancel my order please",
                    "cancel booking and return amount"):
            assert deal_engine.is_payment_complaint(msg), msg

    def test_cancel_without_money_context_is_not(self):
        assert not deal_engine.is_payment_complaint("cancel that, I meant the other package")


class TestPaymentComplaint:
    def test_detects_paid_but_no_answer(self):
        assert deal_engine.is_payment_complaint("While I paid the money also")
        assert deal_engine.is_payment_complaint("Already na 116 pay pana")
        assert deal_engine.is_payment_complaint("what is the status of my payment")

    def test_ordinary_buying_talk_is_not_a_complaint(self):
        assert not deal_engine.is_payment_complaint("how do I pay?")
        assert not deal_engine.is_payment_complaint("49 Rs")


class TestPriceGuardScope:
    def test_no_structured_prices_means_no_guard(self):
        assert deal_engine.unknown_prices("It costs ₹89 lakh.", {"packages": []}, "") == []

    def test_catalog_prices_and_multiples_are_allowed(self):
        extra = deal_engine.price_multiples([249900])
        assert deal_engine.unknown_prices("2 pairs come to ₹4,998", {"packages": []}, "", extra) == []
        assert deal_engine.unknown_prices("Only ₹999 today", {"packages": []}, "", extra) == [999.0]

    def test_order_totals_are_allowed(self):
        assert deal_engine.unknown_prices("Your order of ₹7,497 is pending", CONFIG, "", {7497.0}) == []


class TestOrdersBlock:
    DEALS = [
        {"deal_number": 12, "stage": "awaiting_payment", "total_paise": 499800, "payment_link": "https://rzp.io/l/x",
         "items": [{"name": "Runner X", "qty": 2}]},
        {"deal_number": 9, "stage": "won", "total_paise": 99900, "items": [{"name": "Comfort Sandal", "qty": 1}]},
        {"deal_number": 7, "stage": "quoted", "total_paise": 249900, "items": [{"name": "Runner X", "qty": 1}]},
    ]

    def test_empty_when_no_orders(self):
        assert deal_engine.orders_block([]) == ""

    def test_lists_each_order_with_items_total_and_payment_state(self):
        block = deal_engine.orders_block(self.DEALS)
        assert "D-0012" in block and "Runner X × 2" in block and "₹4998" in block
        assert "payment link sent, not paid" in block.lower()
        assert "PAID" in block and "Comfort Sandal" in block
        assert "price mentioned, no link yet" in block.lower()

    def test_never_shows_a_url(self):
        assert "https://" not in deal_engine.orders_block(self.DEALS)


class TestBusinessFactsBlock:
    def test_lists_only_the_details_that_are_set(self):
        block = deal_engine.business_facts_block({
            "legal_name": "Astro Tamil Pvt Ltd", "address": "12 North St", "city": "Madurai", "state": "Tamil Nadu",
            "pincode": "625001", "gstin": "33ABCDE1234F1Z5", "email": "", "phone": "+91 90000 00000",
            "prices_include_gst": True,
        })
        assert "Astro Tamil Pvt Ltd" in block and "33ABCDE1234F1Z5" in block
        assert "12 North St, Madurai, Tamil Nadu 625001" in block and "+91 90000 00000" in block
        assert "Email" not in block
        assert "include GST" in block

    def test_prices_excluding_gst_is_explained(self):
        block = deal_engine.business_facts_block({"legal_name": "Shop", "prices_include_gst": False})
        assert "exclude GST" in block

    def test_empty_when_nothing_is_set(self):
        assert deal_engine.business_facts_block({}) == ""
        assert deal_engine.business_facts_block({"legal_name": "", "gstin": ""}) == ""


class TestNextStep:
    BASE = {"package_key": "one_question", "package_name": "One Question", "total_amount_paise": 4900,
            "skipped_fields": []}

    def _state(self, **kw):
        return deal_engine.deal_state_block(CONFIG, {**self.BASE, **kw})

    def test_nothing_chosen_means_help_them_choose(self):
        assert "Next step: help them choose" in deal_engine.deal_state_block(CONFIG, None)

    def test_missing_detail_names_the_next_one_to_ask(self):
        state = self._state(status="collecting", collected_data={"name": "Ravi"})
        assert "Next step: ask for Date of birth" in state

    def test_all_details_means_send_the_link(self):
        state = self._state(status="awaiting_confirmation", collected_data={"name": "R", "birth_date": "1"})
        assert "Next step: send the payment link" in state

    def test_link_sent_means_gentle_reminder_only(self):
        state = self._state(status="awaiting_payment", payment_link="x", amount_paise=4900,
                            collected_data={"name": "R", "birth_date": "1"})
        assert "Next step: the link was already sent" in state

    def test_paid_means_do_not_sell(self):
        state = self._state(status="paid", collected_data={})
        assert "Next step: they have paid" in state


def test_human_touch_block_is_in_every_reply_prompt():
    from app.services import ai_reply
    assert "HUMAN TOUCH" in ai_reply._HUMAN_TOUCH_BLOCK
    import inspect
    assert "_HUMAN_TOUCH_BLOCK" in inspect.getsource(ai_reply.build_reply_system_prompt)


class TestReturningGreeting:
    SESSION = {"status": "collecting", "package_key": "one_question", "package_name": "One Question",
               "total_amount_paise": 4900, "collected_data": {"name": "Ravi"}, "skipped_fields": []}

    def test_greeting_with_a_deal_in_progress_asks_to_resume(self):
        prompt = deal_engine.deal_prompt(CONFIG, self.SESSION, returning=True)
        assert prompt.rstrip().endswith("Date of birth.") and "welcome them back" in prompt

    def test_no_resume_note_without_a_deal(self):
        assert "welcome them back in one short line" not in deal_engine.deal_prompt(CONFIG, None, returning=True)

    def test_no_resume_note_once_paid(self):
        paid = {**self.SESSION, "status": "paid"}
        assert "welcome them back in one short line" not in deal_engine.deal_prompt(CONFIG, paid, returning=True)


class TestBlankMessage:
    def test_emoji_or_punctuation_only_counts_as_blank(self):
        for msg in ("?", "??", "👍", "🙏🙏", "...", " ? "):
            assert deal_engine.is_blank_message(msg), msg
        for msg in ("hi", "ok", "49 Rs", "yes"):
            assert not deal_engine.is_blank_message(msg), msg
