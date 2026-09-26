"""The model round-trip for the AI-native deal engine (services/deal_turn.py)."""
import asyncio
import json

from app.services import deal_actions, deal_turn

CTX = deal_actions.DealContext(
    config={"enabled": True, "fields": [], "service_noun": "consultation",
            "packages": [{"key": "one_question", "name": "One Question", "amount_paise": 4900}]},
    db=object(), lead_id="lead-1", tenant_id="t-1", phone="+91000",
)
BASE = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]


class Script:
    """Feeds converse_once a queue of model replies and a queue of tool outcomes."""

    def __init__(self, monkeypatch, responses, outcomes, text_responses=()):
        self.responses = list(responses)
        self.text_responses = list(text_responses)
        self.outcomes = list(outcomes)
        self.seen_messages: list[list[dict]] = []
        self.seen_last_text: list[str] = []
        monkeypatch.setattr(deal_actions, "apply_tool_calls", self._apply)
        monkeypatch.setattr(deal_turn, "_state_line", lambda ctx: "DEAL STATE stub")

    async def llm(self, messages, tools, max_tokens, tenant_id):
        self.seen_messages.append(messages)
        self.tool_names = [t["function"]["name"] for t in tools]
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def llm_text(self, messages, max_tokens, tenant_id):
        """The text-only call: no tools are offered, so nothing can be called again."""
        self.seen_messages.append(messages)
        response = self.text_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def _apply(self, tool_calls, ctx, *, last_assistant_text="", auto_link=False, customer_message=""):
        self.seen_last_text.append(last_assistant_text)
        return self.outcomes.pop(0)

    def run(self, messages=None, other_tools=(), **kw):
        return asyncio.run(deal_turn.converse_once(
            messages or BASE, list(other_tools), CTX, tenant_id="t-1",
            llm_with_tools=self.llm, llm=self.llm_text, **kw))


def _call(name, **args):
    return {"function": {"name": name, "arguments": json.dumps(args)}}


OK = deal_actions.Outcome()


class TestSingleRound:
    def test_plain_reply_uses_one_model_call(self, monkeypatch):
        script = Script(monkeypatch, [("Sure!", [])], [OK])
        text, _calls, outcome = script.run()
        assert text == "Sure!" and len(script.seen_messages) == 1 and outcome.menu is None

    def test_appends_the_real_link_after_the_models_text(self, monkeypatch):
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/1")
        script = Script(monkeypatch, [("Here you go", [_call("create_payment_link")])], [linked])
        text, _c, _o = script.run()
        assert text == "Here you go\nhttps://rzp.io/l/1" and len(script.seen_messages) == 1

    def test_caller_can_append_the_link_itself(self, monkeypatch):
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/1")
        script = Script(monkeypatch, [("Here you go", [_call("create_payment_link")])], [linked])
        text, _c, outcome = script.run(append_link=False)
        assert text == "Here you go" and outcome.payment_link == "https://rzp.io/l/1"

    def test_other_tools_are_passed_alongside_the_deal_tools(self, monkeypatch):
        script = Script(monkeypatch, [("ok", [])], [OK])
        other = [{"type": "function", "function": {"name": "recommend_catalog_item", "parameters": {}}}]
        script.run(other_tools=other)
        assert "select_offering" in script.tool_names and "recommend_catalog_item" in script.tool_names

    def test_handover_note_is_added_to_the_system_prompt_when_the_guard_fired(self, monkeypatch):
        script = Script(monkeypatch, [("ok", [])], [OK])
        script.run(handover_opened=True)
        system = script.seen_messages[0][0]["content"]
        assert "has just been alerted" in system and system.startswith("s")

    def test_no_handover_note_by_default(self, monkeypatch):
        script = Script(monkeypatch, [("ok", [])], [OK])
        script.run()
        assert script.seen_messages[0][0]["content"] == "s"

    def test_previous_assistant_message_is_given_to_the_menu_guard(self, monkeypatch):
        messages = [*BASE, {"role": "assistant", "content": "Pick\n\n[49 Rs]  [99Rs]"}, {"role": "user", "content": "ok"}]
        script = Script(monkeypatch, [("Sure", [_call("show_options", of="packages")])], [OK])
        script.run(messages)
        assert script.seen_last_text == ["Pick\n\n[49 Rs]  [99Rs]"]

    def test_first_round_model_failure_propagates(self, monkeypatch):
        script = Script(monkeypatch, [RuntimeError("llm down")], [])
        try:
            script.run()
        except RuntimeError:
            return
        raise AssertionError("expected the failure to propagate so the caller's fallback runs")


class TestSecondRound:
    def test_refusal_gets_a_second_round_that_carries_the_reason(self, monkeypatch):
        refused = deal_actions.Outcome(refusals=("create_payment_link refused: still needed: birth_date",))
        script = Script(monkeypatch, [("Here is your link!", [_call("create_payment_link")]), ("What is your date of birth?", [])], [refused])
        text, _c, outcome = script.run()
        assert text == "What is your date of birth?" and outcome.refusals == ()
        note = script.seen_messages[1][-1]["content"]
        assert "birth_date" in note and "DEAL STATE stub" in note

    def test_refused_link_is_never_appended(self, monkeypatch):
        refused = deal_actions.Outcome(refusals=("x",))
        script = Script(monkeypatch, [("Here is your link!", [_call("create_payment_link")]), ("Need one more detail", [])], [refused])
        text, _c, _o = script.run()
        assert "http" not in text

    def test_empty_text_after_select_lets_the_model_send_the_link_next(self, monkeypatch):
        selected = deal_actions.Outcome()
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/9")
        script = Script(
            monkeypatch,
            [("", [_call("select_offering", key="one_question")]), ("Great choice!", [_call("create_payment_link")])],
            [selected, linked],
        )
        text, calls, outcome = script.run()
        assert text == "Great choice!\nhttps://rzp.io/l/9" and outcome.payment_link == "https://rzp.io/l/9"
        assert [c["function"]["name"] for c in calls] == ["select_offering", "create_payment_link"]

    def test_menu_with_no_text_gets_a_text_only_round_and_keeps_the_menu(self, monkeypatch):
        menu = {"kind": "buttons", "options": ["49 Rs", "99Rs"], "buttons": []}
        script = Script(
            monkeypatch, [("", [_call("show_options", of="packages")])],
            [deal_actions.Outcome(menu=menu)], text_responses=["Which one suits you?"],
        )
        text, _c, outcome = script.run()
        assert text == "Which one suits you?" and outcome.menu == menu
        assert "already attached" in script.seen_messages[1][-1]["content"]

    def test_link_with_no_text_gets_a_text_only_round_not_a_bare_link(self, monkeypatch):
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/1")
        script = Script(
            monkeypatch, [("", [_call("create_payment_link")])], [linked],
            text_responses=["Idho link, pay panna udane kelvi kekkalaam."],
        )
        text, _c, _o = script.run()
        assert text == "Idho link, pay panna udane kelvi kekkalaam.\nhttps://rzp.io/l/1"

    def test_silent_tool_rounds_end_with_a_final_text_only_call(self, monkeypatch):
        """Live finding: this provider writes no text on any turn where it calls a tool."""
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/9")
        script = Script(
            monkeypatch,
            [("", [_call("select_offering", key="one_question")]), ("", [_call("create_payment_link")])],
            [OK, linked], text_responses=["Super choice! Idho link."],
        )
        text, _c, outcome = script.run()
        assert text == "Super choice! Idho link.\nhttps://rzp.io/l/9" and outcome.payment_link
        assert len(script.seen_messages) == 3
        assert "Do not call any tool" in script.seen_messages[2][-1]["content"]

    def test_final_text_call_failure_leaves_the_text_empty_for_the_caller_fallback(self, monkeypatch):
        script = Script(
            monkeypatch, [("", [_call("select_offering", key="x")]), ("", [])], [OK, OK],
            text_responses=[RuntimeError("llm down")],
        )
        text, _c, _o = script.run()
        assert text == ""

    def test_placeholder_the_model_wrote_is_removed_before_the_real_link(self, monkeypatch):
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/1")
        script = Script(monkeypatch, [("Idho link:\n\n[Payment Link]\n\nPay panunga", [_call("create_payment_link")])], [linked])
        text, _c, _o = script.run()
        assert "[Payment Link]" not in text and text.endswith("https://rzp.io/l/1")
        assert "\n\n\n" not in text

    def test_stale_price_in_the_draft_triggers_a_rewrite(self, monkeypatch):
        script = Script(monkeypatch, [("Consultations start at ₹29", []), ("One Question is ₹49", [])], [OK, OK])
        text, _c, outcome = script.run()
        assert text == "One Question is ₹49" and outcome.refusals == ()
        assert "₹29" in script.seen_messages[1][-1]["content"]

    def test_a_correct_price_needs_no_second_round(self, monkeypatch):
        script = Script(monkeypatch, [("One Question is ₹49", [])], [OK])
        script.run()
        assert len(script.seen_messages) == 1

    def test_near_identical_repeat_of_the_last_message_gets_a_rewrite(self, monkeypatch):
        last = "Ungal concern-ah team-kitta sollirukken, avanga check pannuvanga."
        messages = [*BASE, {"role": "assistant", "content": last}, {"role": "user", "content": "hello?"}]
        script = Script(monkeypatch, [(last, []), ("Puriyudhu, konjam neram aagum.", [])], [OK, OK])
        text, _c, _o = script.run(messages)
        assert text == "Puriyudhu, konjam neram aagum."
        assert "already said" in script.seen_messages[1][-1]["content"]

    def test_repeat_of_an_older_reply_is_also_caught(self, monkeypatch):
        old = "Unga payment vishayatha enga team check pannitu inga reply pannuvanga."
        messages = [*BASE, {"role": "assistant", "content": old}, {"role": "user", "content": "?"},
                    {"role": "assistant", "content": "Sorry for the wait."}, {"role": "user", "content": "hello??"}]
        script = Script(monkeypatch, [(old, []), ("Innum konjam neram, naan follow up panren.", [])], [OK, OK])
        text, _c, _o = script.run(messages)
        assert text != old

    def test_short_repeats_are_not_flagged(self, monkeypatch):
        messages = [*BASE, {"role": "assistant", "content": "Okay 👍"}, {"role": "user", "content": "ok"}]
        script = Script(monkeypatch, [("Okay 👍", [])], [OK])
        script.run(messages)
        assert len(script.seen_messages) == 1

    def test_at_most_two_model_calls(self, monkeypatch):
        refused = deal_actions.Outcome(refusals=("x",))
        script = Script(monkeypatch, [("a", [_call("create_payment_link")]), ("b", [_call("create_payment_link")])], [refused, refused])
        script.run()
        assert len(script.seen_messages) == 2

    def test_second_round_failure_keeps_the_first_draft(self, monkeypatch):
        refused = deal_actions.Outcome(refusals=("x",))
        script = Script(monkeypatch, [("draft", [_call("create_payment_link")]), RuntimeError("llm down")], [refused])
        text, _c, _o = script.run()
        assert text == "draft"


class TestPaymentUrlsFromTheModel:
    def test_model_written_payment_url_is_stripped_and_the_turns_link_attached(self, monkeypatch):
        linked = deal_actions.Outcome(payment_link="https://rzp.io/l/new")
        script = Script(monkeypatch, [("Idho link https://rzp.io/l/old", [_call("create_payment_link")])], [linked])
        text, _c, _o = script.run()
        assert "rzp.io/l/old" not in text and text.endswith("https://rzp.io/l/new")

    def test_copied_old_link_without_a_new_one_forces_a_rewrite(self, monkeypatch):
        script = Script(monkeypatch, [("Idho payment link: https://rzp.io/l/old", [_call("select_offering", key="x")]),
                                      ("Sari, 99 option-ku maathiten. Link anupava?", [])], [OK])
        text, _c, _o = script.run()
        assert "rzp.io" not in text and "do not write" in script.seen_messages[1][-1]["content"].lower()

    def test_business_links_are_left_alone(self):
        assert deal_turn.strip_payment_urls("App: https://astrotamil.co.in/app/") == ("App: https://astrotamil.co.in/app/", False)
        assert deal_turn.strip_payment_urls("Pay https://rzp.io/l/x now")[1] is True
        assert deal_turn.strip_payment_urls("Pay https://razorpay.me/@shop")[1] is True


class TestStripPlaceholders:
    def test_removes_bracketed_and_angle_link_placeholders(self):
        assert deal_turn.strip_placeholders("Pay here [Payment Link] now") == "Pay here now"
        assert deal_turn.strip_placeholders("Pay <link> now") == "Pay now"
        assert deal_turn.strip_placeholders("[URL]") == ""

    def test_leaves_normal_brackets_alone(self):
        assert deal_turn.strip_placeholders("Pick [49 Rs] or [99Rs]") == "Pick [49 Rs] or [99Rs]"


class TestCaptureDetails:
    def _ctx_with_session(self, monkeypatch, session):
        monkeypatch.setattr(deal_actions, "_session", lambda ctx: session)
        saved = []

        async def fake_apply(calls, ctx, **kw):
            saved.append(json.loads(calls[0]["function"]["arguments"])["fields"])
            return deal_actions.Outcome()

        monkeypatch.setattr(deal_actions, "apply_tool_calls", fake_apply)
        return saved

    CFG = {**CTX.config, "fields": [{"key": "name", "label": "Full name", "type": "text"},
                                     {"key": "birth_date", "label": "Date of birth", "type": "date"}]}

    def _ctx(self):
        return deal_actions.DealContext(config=self.CFG, db=object(), lead_id="l", tenant_id="t-1", phone="+91")

    def _run(self, session, monkeypatch, extractor):
        saved = self._ctx_with_session(monkeypatch, session)
        result = asyncio.run(deal_turn.capture_details(self._ctx(), "Ravi 12-03-1994", extractor=extractor))
        return result, saved

    def test_reads_recent_customer_messages_not_just_the_last(self, monkeypatch):
        session = {"status": "collecting", "package_key": "p", "collected_data": {}, "skipped_fields": []}
        seen = []

        async def extractor(message, fields, collected, tenant_id):
            seen.append(message)
            return {}

        saved = self._ctx_with_session(monkeypatch, session)
        asyncio.run(deal_turn.capture_details(self._ctx(), "1 year one", extractor=extractor,
                                              earlier=["my son Karthik is in 12th", "hi"]))
        assert "Karthik" in seen[0] and "1 year one" in seen[0] and saved == []

    def test_saves_only_the_newly_extracted_values(self, monkeypatch):
        session = {"status": "collecting", "package_key": "p", "collected_data": {"name": "Ravi"}, "skipped_fields": []}

        async def extractor(message, fields, collected, tenant_id):
            return {"name": "Ravi", "birth_date": "12-03-1994"}

        result, saved = self._run(session, monkeypatch, extractor)
        assert result == {"birth_date": "12-03-1994"} and saved == [{"birth_date": "12-03-1994"}]

    def test_does_nothing_without_a_selected_offering(self, monkeypatch):
        async def extractor(*a):
            raise AssertionError("must not run")

        result, saved = self._run({"status": "offer_pending", "collected_data": {}}, monkeypatch, extractor)
        assert result == {} and saved == []

    def test_does_nothing_when_every_detail_is_already_there(self, monkeypatch):
        session = {"status": "awaiting_confirmation", "package_key": "p",
                   "collected_data": {"name": "R", "birth_date": "1"}, "skipped_fields": []}

        async def extractor(*a):
            raise AssertionError("must not run")

        assert self._run(session, monkeypatch, extractor)[0] == {}

    def test_does_nothing_for_a_paid_session(self, monkeypatch):
        session = {"status": "paid", "package_key": "p", "collected_data": {}, "skipped_fields": []}

        async def extractor(*a):
            raise AssertionError("must not run")

        assert self._run(session, monkeypatch, extractor)[0] == {}

    def test_extractor_failure_is_swallowed(self, monkeypatch):
        session = {"status": "collecting", "package_key": "p", "collected_data": {}, "skipped_fields": []}

        async def extractor(*a):
            raise RuntimeError("llm down")

        result, saved = self._run(session, monkeypatch, extractor)
        assert result == {} and saved == []


class TestHandoverLineTwice:
    LINE = "Indha issue ku support team assistance useful ah irukkalam."

    def _messages(self, earlier):
        return [*BASE, {"role": "assistant", "content": earlier}, {"role": "user", "content": "tell me the GST number"}]

    def test_reaching_for_the_line_again_opens_a_handover_and_rewrites(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        script = Script(monkeypatch, [(self.LINE + " Ennala thara mudiyadhu.", []),
                                      ("GST number ennaala sariya solla mudiyala, team-ku solliten, avanga reply pannuvanga.", [])], [])
        text, _c, outcome = script.run(self._messages(self.LINE + " App la contact pannalam."), handover_line=self.LINE)
        assert outcome.handover and opened and "twice" in opened[0]
        assert self.LINE not in text and "do not repeat it" in script.seen_messages[1][-1]["content"]

    def test_line_said_long_ago_still_counts(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        messages = [*BASE, {"role": "assistant", "content": self.LINE}, {"role": "user", "content": "ok"},
                    {"role": "assistant", "content": "Sure, anything else?"}, {"role": "user", "content": "gst?"}]
        script = Script(monkeypatch, [(self.LINE, []), ("Team-ku solliten.", [])], [])
        script.run(messages, handover_line=self.LINE)
        assert opened

    def test_saying_it_once_does_not(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        script = Script(monkeypatch, [(self.LINE, [])], [])
        _t, _c, outcome = script.run(handover_line=self.LINE)
        assert not outcome.handover and not opened

    def test_no_configured_line_means_no_backstop(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        script = Script(monkeypatch, [("x is fine here", [])], [])
        script.run(self._messages("x is fine here"), handover_line="")
        assert not opened


class TestGuards:
    def test_payment_complaint_opens_a_handover_before_the_model_runs(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        assert deal_turn.pre_turn_guards(CTX, "While I paid the money also") is True
        assert opened and "paid" in opened[0].lower()

    def test_ordinary_message_opens_nothing(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        assert deal_turn.pre_turn_guards(CTX, "how do I pay?") is False and not opened


class _NoRows:
    def table(self, _name):
        return self

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=[])


class TestBuildContext:
    def test_no_packages_still_gives_a_context_without_package_selling(self, monkeypatch):
        from app.services import intake
        monkeypatch.setattr(intake, "get_intake_config", lambda tenant_id, db=None: {"enabled": True, "packages": []})
        ctx = deal_turn.build_context(_NoRows(), "t-1", "lead-1", "+91000")
        assert ctx is not None and ctx.offerings_enabled is False

    def test_packages_on_whatsapp_enable_package_selling(self, monkeypatch):
        from app.services import intake
        monkeypatch.setattr(intake, "get_intake_config", lambda tenant_id, db=None: CTX.config)
        ctx = deal_turn.build_context(_NoRows(), "t-1", "lead-1", "+91000")
        assert ctx.offerings_enabled and ctx.lead_id == "lead-1" and ctx.config is CTX.config

    def test_packages_are_not_sold_on_other_channels(self, monkeypatch):
        from app.services import intake
        monkeypatch.setattr(intake, "get_intake_config", lambda tenant_id, db=None: CTX.config)
        assert deal_turn.build_context(_NoRows(), "t-1", "lead-1", None, channel="instagram").offerings_enabled is False

    def test_config_read_failure_degrades_to_no_package_selling(self, monkeypatch):
        from app.services import intake

        def boom(tenant_id, db=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(intake, "get_intake_config", boom)
        ctx = deal_turn.build_context(_NoRows(), "t-1", "lead-1", "+91000")
        assert ctx.offerings_enabled is False and ctx.config == {}


class TestNoPackageTools:
    def test_without_packages_the_model_can_still_bring_a_person_in(self, monkeypatch):
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="p", offerings_enabled=False)
        seen_tools = []

        async def with_tools(messages, tools, max_tokens, tenant_id):
            seen_tools.append([t["function"]["name"] for t in tools])
            return "Hello there, how can I help today?", []

        async def text_llm(messages, max_tokens, tenant_id):
            raise AssertionError("the words came in the first call")

        text, calls, _o = asyncio.run(deal_turn.converse_once(BASE, [], ctx, tenant_id="t", llm_with_tools=with_tools, llm=text_llm))
        assert text == "Hello there, how can I help today?" and calls == []
        assert seen_tools == [["hand_to_human", "offer_choices"]]


class TestProductsAttached:
    def test_photo_only_turn_gets_words_from_a_tool_free_call(self, monkeypatch):
        cat_ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="p",
                                           catalog={"sku": {"name": "Runner X"}}, offerings_enabled=False)
        monkeypatch.setattr(deal_actions, "apply_tool_calls",
                            lambda calls, ctx, **kw: _async(deal_actions.Outcome(image_item_ids=("sku",))))
        prompts = []

        async def with_tools(messages, tools, max_tokens, tenant_id):
            return "", [_call("recommend_catalog_item", item_id="sku")]

        async def text_llm(messages, max_tokens, tenant_id):
            prompts.append(messages[-1]["content"])
            return "Idho Runner X, romba comfortable 👟"

        other = [{"type": "function", "function": {"name": "recommend_catalog_item", "parameters": {}}}]
        text, _c, outcome = asyncio.run(deal_turn.converse_once(
            BASE, other, cat_ctx, tenant_id="t", llm_with_tools=with_tools, llm=text_llm))
        assert text == "Idho Runner X, romba comfortable 👟" and outcome.image_item_ids == ("sku",)
        assert "Photos of Runner X" in prompts[0]


async def _coro(value):
    return value


def _async(value):
    return _coro(value)


class TestMenuLogText:
    def test_log_text_lists_the_options(self):
        text = deal_turn.menu_log_text("Pick one", {"options": ["49 Rs", "99Rs"]})
        assert text == "Pick one\n\n[49 Rs]  [99Rs]"


class TestSombreMessages:
    def test_emoji_removed_when_the_customer_is_grieving_or_angry(self):
        for msg in ("my father passed away last week", "your shoes are garbage you cheats",
                    "worst customer support", "she is in hospital, very serious", "அப்பா இறந்துவிட்டார்"):
            assert deal_turn.sombre(msg), msg
        assert deal_turn.without_emoji("So sorry for your loss 🙏😊 we are here.") == "So sorry for your loss we are here."

    def test_ordinary_messages_keep_emoji(self):
        for msg in ("hi", "how much is the cake?", "ok 👍"):
            assert not deal_turn.sombre(msg), msg

    def test_converse_strips_emoji_for_a_sombre_message(self, monkeypatch):
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "my father passed away"}]
        script = Script(monkeypatch, [("Romba varuthama irukku 🙏 unga kooda irukkom 😊", [])], [])
        text, _c, _o = script.run(messages)
        assert "🙏" not in text and "😊" not in text and text.startswith("Romba varuthama irukku")


class TestChoicesGoOutTappable:
    """Options Aira offers in words always leave as buttons on WhatsApp (services/choices.py)."""

    def _run(self, monkeypatch, draft, ctx, outcome=OK):
        async def llm(messages, tools, max_tokens, tenant_id):
            return draft, []

        async def llm_text(messages, max_tokens, tenant_id):
            return ""

        monkeypatch.setattr(deal_turn, "_state_line", lambda ctx: "DEAL STATE stub")
        return asyncio.run(deal_turn.converse_once(BASE, [], ctx, tenant_id="t-1", llm_with_tools=llm, llm=llm_text))

    def test_choices_line_becomes_buttons_and_leaves_the_text(self, monkeypatch):
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
        text, _c, outcome = self._run(monkeypatch, "Morning or evening?\nCHOICES: Morning | Evening", ctx)
        assert text == "Morning or evening?"
        assert outcome.menu["kind"] == "buttons" and outcome.menu["options"] == ["Morning", "Evening"]

    def test_forgotten_marker_list_still_becomes_buttons(self, monkeypatch):
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
        text, _c, outcome = self._run(monkeypatch, "Which batch suits you?\n1. Weekday\n2. Weekend", ctx)
        assert outcome.menu["options"] == ["Weekday", "Weekend"] and "1." not in text

    def test_channel_without_buttons_gets_the_options_written_out(self, monkeypatch):
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=False)
        text, _c, outcome = self._run(monkeypatch, "Which slot?\nCHOICES: Morning | Evening", ctx)
        assert outcome.menu is None and text.endswith("1. Morning\n2. Evening") and "CHOICES" not in text

    def test_only_a_marker_still_sends_a_body(self, monkeypatch):
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
        text, _c, outcome = self._run(monkeypatch, "CHOICES: Yes | No", ctx)
        assert text == deal_turn.CHOICE_BODY_FALLBACK and outcome.menu["options"] == ["Yes", "No"]


class TestChoiceBackstops:
    def _ctx(self, **kw):
        return deal_actions.DealContext(config=kw.pop("config", {}), db=object(), lead_id="l", tenant_id="t",
                                        phone="", buttons_enabled=True, **kw)

    def _run(self, monkeypatch, ctx, draft, calls=(), messages=None):
        async def llm(messages, tools, max_tokens, tenant_id):
            return draft, list(calls)

        async def llm_text(messages, max_tokens, tenant_id):
            return ""

        monkeypatch.setattr(deal_turn, "_state_line", lambda ctx: "DEAL STATE stub")
        monkeypatch.setattr(deal_actions, "apply_tool_calls", lambda calls, ctx, **kw: _async(OK))
        return asyncio.run(deal_turn.converse_once(messages or BASE, [], ctx, tenant_id="t", llm_with_tools=llm, llm=llm_text))

    def test_offer_choices_tool_supplies_the_message_and_buttons(self, monkeypatch):
        call = _call("offer_choices", message="Which day suits you?", options=["Tuesday", "Wednesday"])
        text, _c, outcome = self._run(monkeypatch, self._ctx(), "", [call])
        assert text == "Which day suits you?" and outcome.menu["options"] == ["Tuesday", "Wednesday"]

    def test_inline_options_in_the_question_get_buttons(self, monkeypatch):
        text, _c, outcome = self._run(monkeypatch, self._ctx(), "Thanks Priya. What time would you prefer: Morning, Afternoon, or Evening?")
        assert outcome.menu["options"] == ["Morning", "Afternoon", "Evening"]
        assert text.endswith("Morning, Afternoon, or Evening?")

    def test_question_about_a_choice_detail_gets_its_options(self, monkeypatch):
        config = {"enabled": True, "packages": [{"key": "cut", "name": "Haircut", "amount_paise": 30000}],
                  "fields": [{"key": "slot", "label": "Preferred time", "type": "choice", "options": ["Morning", "Evening"]}]}
        monkeypatch.setattr(deal_actions, "_session", lambda ctx: {"package_key": "cut", "collected_data": {}})
        _t, _c, outcome = self._run(monkeypatch, self._ctx(config=config), "What time suits you tomorrow?")
        assert outcome.menu["options"] == ["Morning", "Evening"]

    def test_question_naming_two_packages_gets_the_package_menu(self, monkeypatch):
        config = {"enabled": True, "fields": [], "packages": [
            {"key": "one", "name": "One Question", "amount_paise": 4900, "button_label": "49 Rs"},
            {"key": "two", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs"}]}
        _t, _c, outcome = self._run(monkeypatch, self._ctx(config=config),
                                    "One Question is ₹49 and Detailed Question is ₹99. Which one do you want?")
        assert outcome.menu["options"] == ["49 Rs", "99Rs"]

    def test_same_package_menu_is_not_resent(self, monkeypatch):
        config = {"enabled": True, "fields": [], "packages": [
            {"key": "one", "name": "One Question", "amount_paise": 4900, "button_label": "49 Rs"},
            {"key": "two", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs"}]}
        history = [{"role": "system", "content": "s"}, {"role": "assistant", "content": "Pick\n\n[49 Rs]  [99Rs]"},
                   {"role": "user", "content": "hmm"}]
        _t, _c, outcome = self._run(monkeypatch, self._ctx(config=config),
                                    "One Question or Detailed Question, which feels right?", messages=history)
        assert outcome.menu is None

    def test_plain_statement_gets_no_buttons(self, monkeypatch):
        _t, _c, outcome = self._run(monkeypatch, self._ctx(), "Your order ships tomorrow morning.")
        assert outcome.menu is None


class TestTeamClaimsAreMadeTrue:
    def test_saying_the_team_is_checking_opens_a_handover(self, monkeypatch):
        opened = []
        monkeypatch.setattr(deal_actions, "open_handover", lambda ctx, reason: opened.append(reason))
        ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="")

        async def llm(messages, tools, max_tokens, tenant_id):
            return "I don't know that. I'm checking with my team and they will reply here.", []

        text, _c, outcome = asyncio.run(deal_turn.converse_once(BASE, [], ctx, tenant_id="t", llm_with_tools=llm, llm=llm))
        assert opened == [deal_turn.TEAM_CLAIM_REASON] and outcome.handover

    def test_claiming_the_team_answered_is_refused(self):
        assert deal_turn._team_answer_refusals("I've checked with the team, and we don't have parking.")
        assert deal_turn._team_answer_refusals("The team confirmed it's fine.")
        assert not deal_turn._team_answer_refusals("Our team offers haircuts and spa.")


def test_asking_to_see_options_attaches_the_package_menu():
    ctx = deal_actions.DealContext(
        config={"enabled": True, "fields": [], "packages": [
            {"key": "one", "name": "One Question", "amount_paise": 4900, "button_label": "49 Rs"},
            {"key": "two", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs"}]},
        db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
    menu, shown = deal_turn._package_menu("Neenga ingaye pay pannalaam. Options paakanuma?", ctx, "")
    assert menu["options"] == ["49 Rs", "99Rs"] and not shown


class TestAskedAgain:
    def test_same_question_after_no_answer_brings_a_person(self):
        msgs = [{"role": "system", "content": "s"},
                {"role": "user", "content": "Is there parking for a tempo traveller?"},
                {"role": "assistant", "content": "Sorry, I don't have information about parking."},
                {"role": "user", "content": "Please check, is there parking for a tempo traveller?"}]
        assert deal_turn._asked_again(msgs, "")

    def test_a_new_question_is_not_asked_again(self):
        msgs = [{"role": "system", "content": "s"},
                {"role": "user", "content": "Is there parking?"},
                {"role": "assistant", "content": "I don't know, sorry."},
                {"role": "user", "content": "What are your timings on Sunday?"}]
        assert not deal_turn._asked_again(msgs, "")

    def test_repeat_after_a_real_answer_is_not_a_handover(self):
        msgs = [{"role": "system", "content": "s"},
                {"role": "user", "content": "What time do you open?"},
                {"role": "assistant", "content": "We open at 10am, Tuesday to Sunday."},
                {"role": "user", "content": "what time do you open"}]
        assert not deal_turn._asked_again(msgs, "")


class TestMenuFits:
    CTX = deal_actions.DealContext(
        config={"enabled": True, "fields": [], "packages": [
            {"key": "checkup", "name": "Check-up", "amount_paise": 50000},
            {"key": "rct", "name": "Root canal", "amount_paise": 500000}]},
        db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
    MENU = {"kind": "buttons", "options": ["Check-up", "Root canal"], "buttons": []}

    def test_menu_under_a_question_about_the_name_is_dropped(self):
        assert not deal_turn._menu_fits("Great! Could you share your full name and a preferred day?", self.MENU, self.CTX)

    def test_menu_under_which_one_is_kept(self):
        assert deal_turn._menu_fits("Which one suits you?", self.MENU, self.CTX)

    def test_menu_under_a_question_with_its_own_options_is_dropped(self):
        assert not deal_turn._menu_fits("Which time works: morning or evening?", self.MENU, self.CTX)

    def test_intro_without_a_question_keeps_the_menu(self):
        assert deal_turn._menu_fits("Here's what we offer 👇", self.MENU, self.CTX)


def test_named_category_opens_its_own_options():
    packages = [{"key": "crash", "name": "Crash Course", "amount_paise": 1},
                {"key": "long_term", "name": "Long Term", "options": [{"key": "y1", "name": "1 Year", "amount_paise": 2}]}]
    assert deal_actions._named_category(packages, "long-term course details")["key"] == "long_term"
    assert deal_actions._named_category(packages, "what courses do you have") is None
