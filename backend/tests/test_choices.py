"""Choices always go out tappable (services/choices.py)."""
from app.services import choices


class TestMarker:
    def test_marker_line_becomes_options_and_is_removed(self):
        body, options = choices.extract("Morning or evening slot?\nCHOICES: Morning | Evening")
        assert body == "Morning or evening slot?"
        assert options == ["Morning", "Evening"]

    def test_marker_is_case_and_markdown_tolerant(self):
        body, options = choices.extract("Pick one\n**choices:** Yes | No ")
        assert body == "Pick one" and options == ["Yes", "No"]

    def test_single_option_marker_is_removed_but_gives_no_menu(self):
        body, options = choices.extract("Shall I go ahead?\nCHOICES: Yes")
        assert body == "Shall I go ahead?" and options == []

    def test_duplicates_are_dropped(self):
        _, options = choices.extract("x?\nCHOICES: Yes | yes | No")
        assert options == ["Yes", "No"]

    def test_tamil_options_survive(self):
        _, options = choices.extract("எது வேண்டும்?\nCHOICES: காலை | மாலை")
        assert options == ["காலை", "மாலை"]


class TestListBackstop:
    def test_numbered_list_under_a_which_question(self):
        text = "Which one would you like?\n1. Silk saree\n2. Cotton saree\n3. Linen saree"
        body, options = choices.extract(text)
        assert options == ["Silk saree", "Cotton saree", "Linen saree"]
        assert body == "Which one would you like?"

    def test_bulleted_list_with_tanglish_question_after(self):
        text = "Namma kitta rendu option irukku:\n- Online class\n- Offline class\nEdhu venum?"
        body, options = choices.extract(text)
        assert options == ["Online class", "Offline class"]
        assert "Edhu venum?" in body and "- Online" not in body

    def test_information_list_without_a_pick_question_is_left_alone(self):
        text = "The kit includes:\n- 2 brushes\n- 1 palette\nAnything else I can help with?"
        assert choices.extract(text) == (text, [])

    def test_long_items_are_descriptions_not_options(self):
        text = "Which suits you?\n- " + "x" * 80 + "\n- short"
        assert choices.extract(text)[1] == []

    def test_two_separate_lists_are_ambiguous_and_left_alone(self):
        text = "Which size?\n- S\n- M\nWhich colour?\n- Red\n- Blue"
        assert choices.extract(text)[1] == []

    def test_plain_message_has_no_options(self):
        assert choices.extract("Your order ships tomorrow.") == ("Your order ships tomorrow.", [])


class TestMenu:
    def test_two_or_three_short_options_are_buttons(self):
        menu = choices.build_menu(["Yes", "No"])
        assert menu["kind"] == "buttons"
        assert menu["buttons"] == [{"id": "choice:1", "title": "Yes"}, {"id": "choice:2", "title": "No"}]

    def test_long_option_falls_to_a_list_with_full_text_in_description(self):
        menu = choices.build_menu(["Weekend batch starting October", "Weekday"])
        assert menu["kind"] == "list"
        row = menu["sections"][0]["rows"][0]
        assert len(row["title"]) <= 24 and row["description"] == "Weekend batch starting October"

    def test_four_to_ten_options_are_a_list(self):
        menu = choices.build_menu([f"Option {i}" for i in range(7)])
        assert menu["kind"] == "list" and len(menu["options"]) == 7

    def test_more_than_ten_keeps_ten(self):
        assert len(choices.build_menu([f"O{i}" for i in range(14)])["options"]) == 10

    def test_one_option_is_no_menu(self):
        assert choices.build_menu(["Only"]) is None


def test_text_channels_get_the_options_written_out():
    assert choices.as_text("Which slot?", ["Morning", "Evening"]) == "Which slot?\n\n1. Morning\n2. Evening"
    assert choices.as_text("Morning or Evening?", ["Morning", "Evening"]) == "Morning or Evening?"


def test_choice_tap_ids():
    assert choices.is_choice_tap("choice:2")
    assert not choices.is_choice_tap("one_question") and not choices.is_choice_tap(None)


class TestInline:
    def test_options_after_a_colon(self):
        assert choices.inline_options("What time: morning or evening?") == ["Morning", "Evening"]

    def test_tamil_or(self):
        assert choices.inline_options("காலை, மதியம் அல்லது மாலை?") == ["காலை", "மதியம்", "மாலை"]

    def test_a_long_open_question_is_not_options(self):
        assert choices.inline_options("Would you like me to check with the team or send the link now?") == []

    def test_trailing_which_clause_is_not_an_option(self):
        assert choices.inline_options("Morning or evening, which works?") == ["Morning", "Evening"]

    def test_yes_no_without_options_is_left_alone(self):
        assert choices.inline_options("Shall I send the payment link?") == []


def test_tool_call_parsing():
    call = {"function": {"name": "offer_choices", "arguments": '{"message": "Pick", "options": ["A", "A", "B"]}'}}
    assert choices.from_tool_calls([call]) == ("Pick", ["A", "B"])
    bad = {"function": {"name": "offer_choices", "arguments": "not json"}}
    assert choices.from_tool_calls([bad]) is None


def test_field_options_need_the_question_to_be_about_that_detail():
    field = {"label": "Preferred time", "options": ["Morning", "Evening"]}
    assert choices.field_options_for("What time works?", field) == ["Morning", "Evening"]
    assert choices.field_options_for("Anything else I can help with?", field) == []
    assert choices.field_options_for("Noted the time.", field) == []


def test_options_before_a_dash_question():
    assert choices.inline_options("நாளைக்கு எப்போ? காலை, மதியம் அல்லது மாலை - இதில் எது உங்களுக்கு வசதி?") == ["காலை", "மதியம்", "மாலை"]
