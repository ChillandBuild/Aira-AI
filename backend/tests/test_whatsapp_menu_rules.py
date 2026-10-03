"""The WhatsApp menu rules: two options are reply buttons, three or more are a list, one link is a
URL button. Every Meta limit is applied before sending, in the customer's language."""
import asyncio

import pytest

from app.services import choices, deal_actions, deal_turn, meta_cloud

BASE = [{"role": "system", "content": "s"}, {"role": "user", "content": "Ippo ethathum offer poitu irukka"}]

THURSDAY_PACKAGES = """Aama, namma kitta pala consultation options irukku. Ungalukku edhula interest irukku-nu sollunga, naan explain panren:

🔹 *Oru Kelvi* – ₹1 (Oru kelvikku astrologer voice reply)
🔹 *Detailed* – ₹99 (Life situation pathi detailed voice reply)
🔹 *Marriage Porutham* – ₹99 (Jathaga porutham report)

Edhu venum-nu sollunga, help panren. 😊"""

THURSDAY_CONFIRM = """Sari, "Oru Kelvi" option select pannikalam. 😊

Munnaadiye neenga kudutha indha details-ah confirm pannikonga:
Name: Prem
Gender: Male

Idhu correct-ah? Illa edhavadhu maathano? Sollunga, proceed pannalam."""

PACKAGES = {"enabled": True, "fields": [], "packages": [
    {"key": "kelvi", "name": "Oru Kelvi", "amount_paise": 100},
    {"key": "detailed", "name": "Detailed", "amount_paise": 9900},
    {"key": "porutham", "name": "Marriage Porutham", "amount_paise": 9900}]}


def _run(monkeypatch, draft, config=None, calls=(), llm_text=None, customer=None):
    ctx = deal_actions.DealContext(config=config or {}, db=object(), lead_id="l", tenant_id="t", phone="",
                                   buttons_enabled=True)

    async def llm(messages, tools, max_tokens, tenant_id):
        return draft, list(calls)

    async def text_llm(messages, max_tokens, tenant_id):
        return llm_text or ""

    async def apply(calls, ctx, **kw):
        return deal_actions.Outcome()

    monkeypatch.setattr(deal_turn, "_state_line", lambda ctx: "DEAL STATE stub")
    monkeypatch.setattr(deal_actions, "apply_tool_calls", apply)
    messages = BASE if customer is None else [BASE[0], {"role": "user", "content": customer}]
    return asyncio.run(deal_turn.converse_once(messages, [], ctx, tenant_id="t", llm_with_tools=llm, llm=text_llm))


class TestThursdayRegressions:
    """2026-10-01 9:55 PM: both replies went out as plain text."""

    def test_packages_laid_out_without_a_question_mark_get_the_list(self, monkeypatch):
        _text, _calls, outcome = _run(monkeypatch, THURSDAY_PACKAGES, config=PACKAGES)
        assert outcome.menu["kind"] == "list"
        assert outcome.menu["options"] == ["Oru Kelvi", "Detailed", "Marriage Porutham"]

    def test_tanglish_confirmation_gets_yes_no_buttons(self, monkeypatch):
        _text, _calls, outcome = _run(monkeypatch, THURSDAY_CONFIRM)
        assert outcome.menu["kind"] == "buttons" and outcome.menu["options"] == ["Yes", "No"]

    def test_the_package_descriptions_stay_in_the_message(self, monkeypatch):
        text, _calls, _outcome = _run(monkeypatch, THURSDAY_PACKAGES, config=PACKAGES)
        assert "Oru kelvikku astrologer voice reply" in text


class TestFormatRule:
    def test_two_options_are_reply_buttons(self):
        menu = choices.build_menu(["Yes", "No"])
        assert menu["kind"] == "buttons" and [b["title"] for b in menu["buttons"]] == ["Yes", "No"]

    def test_three_options_are_a_list_even_when_short(self):
        menu = choices.build_menu(["Morning", "Noon", "Evening"])
        assert menu["kind"] == "list" and len(menu["sections"][0]["rows"]) == 3

    def test_two_options_with_a_long_title_fall_to_a_list(self):
        menu = choices.build_menu(["Marriage Porutham Report Detailed", "Yes"])
        assert menu["kind"] == "list"

    def test_more_than_ten_options_keep_ten_rows(self):
        menu = choices.build_menu([f"Option {i}" for i in range(15)])
        assert len(menu["sections"][0]["rows"]) == 10

    def test_long_row_titles_are_cut_to_24_and_keep_their_words_as_description(self):
        menu = choices.build_menu(["A" * 40, "B" * 40, "C"])
        row = menu["sections"][0]["rows"][0]
        assert len(row["title"]) <= 24 and row["description"] == "A" * 40

    def test_rows_that_collapse_to_the_same_title_stay_distinct(self):
        menu = choices.build_menu(["Priority Mail Express Option One", "Priority Mail Express Option Two", "x"])
        titles = [r["title"] for r in menu["sections"][0]["rows"]]
        assert len(set(titles)) == 3 and all(len(t) <= 24 for t in titles)

    def test_row_descriptions_are_cut_to_72(self):
        menu = choices.build_menu(["A" * 200, "B", "C"])
        assert len(menu["sections"][0]["rows"][0]["description"]) <= 72


class TestListLabelFollowsTheCustomerLanguage:
    @pytest.mark.parametrize("text,expected", [
        ("Edhu venum-nu sollunga, help panren. Unga kelvi enna", "Options paarunga"),
        ("உங்களுக்கு எது வேண்டும்?", "தேர்வுகள்"),
        ("आपको कौन सा चाहिए?", "विकल्प देखें"),
        ("Which one do you want?", "Options"),
    ])
    def test_label_by_script_and_tanglish(self, text, expected):
        assert choices.list_label_for(text) == expected

    def test_every_label_fits_the_20_character_limit(self):
        assert all(0 < len(v) <= 20 for v in choices.LIST_LABELS.values())

    def test_the_ai_supplied_label_wins_for_any_language(self):
        assert choices.list_label_for("¿Cuál prefieres?", hint="Ver opciones") == "Ver opciones"

    def test_an_over_long_or_empty_ai_label_is_ignored(self):
        assert choices.list_label_for("Which?", hint="x" * 21) == "Options"
        assert choices.list_label_for("Which?", hint="  ") == "Options"

    def test_the_list_sent_for_a_tamil_message_uses_the_tanglish_label(self, monkeypatch):
        _t, _c, outcome = _run(monkeypatch, THURSDAY_PACKAGES, config=PACKAGES)
        assert outcome.menu["button_text"] == "Options paarunga"

    def test_offer_choices_list_label_is_used(self, monkeypatch):
        call = {"function": {"name": "offer_choices", "arguments":
                '{"message": "¿Cuál prefieres?", "options": ["Uno", "Dos", "Tres"], "list_label": "Ver opciones"}'}}
        _t, _c, outcome = _run(monkeypatch, "", calls=[call], customer="hola")
        assert outcome.menu["kind"] == "list" and outcome.menu["button_text"] == "Ver opciones"


class TestLinkButton:
    def test_one_https_link_becomes_a_url_button(self):
        link = choices.split_link("Book your slot here:\nhttps://example.com/book?id=1")
        assert link.url == "https://example.com/book?id=1"
        assert link.body == "Book your slot here:" and link.label == "Open link"

    def test_payment_links_say_pay_now(self):
        link = choices.split_link("Pay here 👇\nhttps://rzp.io/l/abc")
        assert link.label == "Pay now"

    def test_the_label_follows_the_customer_language(self):
        assert choices.split_link("Pay pannunga:\nhttps://rzp.io/l/abc Edhu venum-nu sollunga").label == "Pay pannunga"
        assert choices.split_link("இங்கே பணம் செலுத்துங்கள் https://rzp.io/l/abc").label == "பணம் செலுத்து"

    def test_trailing_punctuation_is_not_part_of_the_url(self):
        assert choices.split_link("See https://example.com/a.").url == "https://example.com/a"

    def test_markdown_links_keep_their_words(self):
        link = choices.split_link("Please [book here](https://example.com/b) today")
        assert link.url == "https://example.com/b" and link.body == "Please book here today"

    def test_a_message_that_is_only_a_link_has_an_empty_body(self):
        assert choices.split_link("https://example.com/x").body == ""

    @pytest.mark.parametrize("text", [
        "no link here",
        "two https://a.com/1 and https://b.com/2",
        "plain http://example.com/insecure",
        "x " * 600 + "https://example.com/long-body",
    ])
    def test_anything_else_stays_plain_text(self, text):
        assert choices.split_link(text) is None

    def test_the_same_link_written_twice_is_still_one_link(self):
        assert choices.split_link("https://a.com/1 again https://a.com/1").url == "https://a.com/1"


class TestMetaLimits:
    def test_cta_url_rejects_a_label_over_20_characters(self):
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_cta_url_message("91", "Body", "x" * 21, "https://a.com"))

    def test_cta_url_rejects_a_non_https_url(self):
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_cta_url_message("91", "Body", "Open", "javascript:alert(1)"))

    def test_cta_url_rejects_an_empty_or_oversized_body(self):
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_cta_url_message("91", "", "Open", "https://a.com"))
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_cta_url_message("91", "x" * 1025, "Open", "https://a.com"))

    def test_buttons_reject_duplicate_titles(self):
        buttons = [{"id": "a", "title": "Yes"}, {"id": "b", "title": "yes"}]
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_interactive_buttons("91", "Body", buttons))

    def test_buttons_reject_an_id_over_256(self):
        buttons = [{"id": "a" * 257, "title": "Yes"}, {"id": "b", "title": "No"}]
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_interactive_buttons("91", "Body", buttons))

    def test_list_rejects_a_row_id_over_200_and_duplicate_ids(self):
        long_id = [{"rows": [{"id": "a" * 201, "title": "One"}]}]
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_list_message("91", "Body", "Options", long_id))
        twin_ids = [{"rows": [{"id": "a", "title": "One"}, {"id": "a", "title": "Two"}]}]
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_list_message("91", "Body", "Options", twin_ids))

    def test_list_rejects_an_empty_title_or_body(self):
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_list_message("91", "Body", "Options", [{"rows": [{"id": "a", "title": " "}]}]))
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_list_message("91", "", "Options", [{"rows": [{"id": "a", "title": "One"}]}]))

    def test_a_list_with_several_sections_needs_a_title_on_each(self):
        sections = [{"rows": [{"id": "a", "title": "One"}]}, {"title": "Two", "rows": [{"id": "b", "title": "Two"}]}]
        with pytest.raises(ValueError):
            asyncio.run(meta_cloud.send_list_message("91", "Body", "Options", sections))


class TestSendLink:
    def test_a_url_button_is_sent_and_reported_tappable(self, monkeypatch):
        sent = {}

        async def cta(**kw):
            sent.update(kw)
            return {"messages": [{"id": "wamid.1"}]}

        monkeypatch.setattr(meta_cloud, "send_cta_url_message", cta)
        link = choices.split_link("Pay here\nhttps://rzp.io/l/abc")
        sid, tappable = asyncio.run(deal_turn.send_link("91", link, tenant_id="t"))
        assert (sid, tappable) == ("wamid.1", True)
        assert sent["button_url"] == "https://rzp.io/l/abc" and sent["button_text"] == "Pay now"
        assert sent["body_text"] == "Pay here"

    def test_an_empty_body_gets_the_pointer_emoji(self, monkeypatch):
        sent = {}

        async def cta(**kw):
            sent.update(kw)
            return {"messages": [{"id": "w"}]}

        monkeypatch.setattr(meta_cloud, "send_cta_url_message", cta)
        asyncio.run(deal_turn.send_link("91", choices.split_link("https://example.com/x"), tenant_id="t"))
        assert sent["body_text"] == deal_turn.CHOICE_BODY_FALLBACK

    def test_when_meta_refuses_the_link_goes_out_as_plain_text(self, monkeypatch):
        plain = []

        async def cta(**kw):
            raise RuntimeError("rejected")

        async def send_whatsapp(phone, text, **kw):
            plain.append(text)
            return "wamid.2"

        monkeypatch.setattr(meta_cloud, "send_cta_url_message", cta)
        from app.services import ai_reply
        monkeypatch.setattr(ai_reply, "send_whatsapp", send_whatsapp)
        link = choices.split_link("Pay here\nhttps://rzp.io/l/abc")
        sid, tappable = asyncio.run(deal_turn.send_link("91", link, tenant_id="t"))
        assert (sid, tappable) == ("wamid.2", False)
        assert plain == ["Pay here\nhttps://rzp.io/l/abc"]


class TestSafetyNet:
    """A reply that asks for a pick but matches no pattern is checked by a small, fast model call."""

    OPEN = "Neenga enna time-la call venum? Sollunga."

    def test_the_classifier_attaches_the_options_it_finds(self, monkeypatch):
        reply = '{"options": ["Morning", "Evening"], "label": "Options paarunga"}'
        _t, _c, outcome = _run(monkeypatch, "Neenga evlo mani-ku call venum?", llm_text=reply)
        assert outcome.menu["kind"] == "buttons" and outcome.menu["options"] == ["Morning", "Evening"]

    def test_three_found_options_become_a_list_with_the_models_label(self, monkeypatch):
        reply = '{"options": ["Uno", "Dos", "Tres"], "label": "Ver opciones"}'
        _t, _c, outcome = _run(monkeypatch, "¿Cuál prefieres?", llm_text=reply, customer="hola")
        assert outcome.menu["kind"] == "list" and outcome.menu["button_text"] == "Ver opciones"

    def test_an_open_question_gets_no_buttons(self, monkeypatch):
        _t, _c, outcome = _run(monkeypatch, "What is your name?", llm_text='{"options": []}')
        assert outcome.menu is None

    def test_unparseable_or_failing_output_means_plain_text(self, monkeypatch):
        _t, _c, outcome = _run(monkeypatch, "Which one?", llm_text="sure! here you go")
        assert outcome.menu is None

    def test_a_slow_model_never_blocks_the_reply(self, monkeypatch):
        async def slow(messages, max_tokens, tenant_id):
            await asyncio.sleep(10)
            return '{"options": ["A", "B"]}'

        monkeypatch.setattr(deal_turn, "CHOICE_CLASSIFY_TIMEOUT", 0.05)
        result = asyncio.run(choices.classify("Which one do you want, A or B?", "hi", slow, "t",
                                              timeout=deal_turn.CHOICE_CLASSIFY_TIMEOUT))
        assert result is None

    def test_statements_are_never_sent_to_the_classifier(self, monkeypatch):
        calls = []

        async def spy(messages, max_tokens, tenant_id):
            calls.append(1)
            return '{"options": ["A", "B"]}'

        assert not choices.might_offer_choice("Your order ships tomorrow morning.")
        assert choices.might_offer_choice("Which time suits you?")
        assert calls == []
