"""Unit tests for the deterministic checks in evals/conversations/checks.py.

A transcript is a list of turns:
  {"lead": str,
   "replies": [{"text": str, "kind": "text"|"buttons"|"list", "options": [str]}],
   "events": [{"type": "payment_link", "url": str, "missing_required": [str]},
              {"type": "handover", "reason": str}]}
"""
from evals.conversations import checks

CONFIG = {
    "packages": [
        {"key": "one_question", "name": "One Question", "amount_paise": 4900},
        {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900},
    ],
    "allowed_hosts": ["astrotamil.co.in"],
}


def _turn(lead="hi", replies=(), events=()):
    return {
        "lead": lead,
        "replies": [r if isinstance(r, dict) else {"text": r, "kind": "text", "options": []} for r in replies],
        "events": list(events),
    }


def _status(name, transcript, config=CONFIG):
    return checks.run_check(name, transcript, config).status


class TestNoEmptyBlock:
    def test_fails_on_empty_summary_bubble(self):
        t = [_turn(replies=["Here are your details.\n\n\n\nAre they correct?"])]
        assert _status("no_empty_block", t) == "fail"

    def test_passes_on_normal_paragraphs(self):
        t = [_turn(replies=["Line one.\n\nLine two."])]
        assert _status("no_empty_block", t) == "pass"


class TestNoInventedPrice:
    def test_passes_when_price_is_in_config(self):
        t = [_turn(replies=["One Question is ₹49."])]
        assert _status("no_invented_price", t) == "pass"

    def test_fails_on_price_not_in_config(self):
        t = [_turn(replies=["I can do it for ₹20 today."])]
        assert _status("no_invented_price", t) == "fail"

    def test_button_title_style_amount_is_recognised(self):
        t = [_turn(replies=["Pick one: [49 Rs] [75 Rs]"])]
        result = checks.run_check("no_invented_price", t, CONFIG)
        assert result.status == "fail" and "75" in result.detail

    def test_amount_the_lead_said_may_be_repeated(self):
        t = [_turn(lead="can you do it for 20 rupees", replies=["Sorry, I cannot do ₹20."])]
        assert _status("no_invented_price", t) == "pass"

    def test_lead_message_with_a_bare_comma_does_not_crash(self):
        t = [_turn(lead="Ravi Kumar, born 12 March 1994, 6:30 am", replies=["One Question is ₹49."])]
        assert _status("no_invented_price", t) == "pass"

    def test_nested_options_and_addon_prices_are_allowed(self):
        config = {"packages": [{"key": "career", "name": "Career", "options": [
            {"key": "gen", "name": "General", "amount_paise": 49900,
             "addons": [{"key": "r", "name": "Report", "amount_paise": 20000}]}]}]}
        t = [_turn(replies=["General is ₹499, add the report for ₹200."])]
        assert _status("no_invented_price", t, config) == "pass"

    def test_package_plus_addon_total_is_allowed(self):
        config = {"packages": [{"key": "c", "name": "Crash", "amount_paise": 1500000,
                                "addons": [{"key": "m", "name": "Material", "amount_paise": 200000}]}]}
        t = [_turn(replies=["With material it is ₹17,000 in total."])]
        assert _status("no_invented_price", t, config) == "pass"

    def test_words_ending_in_rs_are_not_rupees(self):
        t = [_turn(replies=["It covers 11th and 12th portions."])]
        assert _status("no_invented_price", t) == "pass"

    def test_quantity_multiples_are_allowed(self):
        config = {"catalog": [{"id": "a", "price_paise": 249900}]}
        t = [_turn(replies=["2 pairs come to ₹4,998."])]
        assert _status("no_invented_price", t, config) == "pass"


class TestNoInventedLink:
    def test_fails_on_unknown_link(self):
        t = [_turn(replies=["Pay here https://evil.example/pay"])]
        assert _status("no_invented_link", t) == "fail"

    def test_passes_on_link_from_payment_event(self):
        ev = {"type": "payment_link", "url": "https://rzp.io/l/abc", "missing_required": []}
        t = [_turn(replies=["Pay here https://rzp.io/l/abc"], events=[ev])]
        assert _status("no_invented_link", t) == "pass"

    def test_old_payment_link_reused_in_a_later_turn_fails(self):
        ev = {"type": "payment_link", "url": "https://rzp.io/l/abc", "missing_required": []}
        t = [_turn(replies=["Pay https://rzp.io/l/abc"], events=[ev]),
             _turn(lead="actually the other one", replies=["Here: https://rzp.io/l/abc"])]
        assert _status("no_invented_link", t) == "fail"

    def test_passes_on_allowed_host(self):
        t = [_turn(replies=["See https://astrotamil.co.in/app/consultation/"])]
        assert _status("no_invented_link", t) == "pass"


class TestLinkNeedsDetails:
    def test_fails_when_link_created_with_missing_details(self):
        ev = {"type": "payment_link", "url": "u", "missing_required": ["birth_date"]}
        assert _status("link_needs_details", [_turn(events=[ev])]) == "fail"

    def test_passes_when_nothing_missing(self):
        ev = {"type": "payment_link", "url": "u", "missing_required": []}
        assert _status("link_needs_details", [_turn(events=[ev])]) == "pass"


class TestNoRepeat:
    def test_fails_on_identical_consecutive_replies(self):
        t = [
            _turn(replies=["Please choose an option from the list."]),
            _turn(replies=["Please choose an option from the list."]),
        ]
        assert _status("no_repeat", t) == "fail"

    def test_fails_on_same_menu_twice_in_a_row(self):
        menu = {"text": "Which one?", "kind": "buttons", "options": ["49 Rs", "99 Rs"]}
        menu2 = {"text": "Pick from these", "kind": "buttons", "options": ["49 Rs", "99 Rs"]}
        assert _status("no_repeat", [_turn(replies=[menu]), _turn(replies=[menu2])]) == "fail"

    def test_passes_on_different_replies(self):
        t = [_turn(replies=["Hello there."]), _turn(replies=["Sure, what is your name?"])]
        assert _status("no_repeat", t) == "pass"


class TestHandover:
    def test_payment_complaint_needs_handover_by_first_mention(self):
        handover = {"type": "handover", "reason": "x"}
        late = [
            _turn(lead="I didn't get a response"),
            _turn(lead="while I paid the money also"),
            _turn(lead="worst support", events=[handover]),
        ]
        assert _status("handover_on_payment_complaint", late) == "fail"

    def test_payment_complaint_passes_when_handover_at_first_mention(self):
        handover = {"type": "handover", "reason": "x"}
        ok = [
            _turn(lead="I didn't get a response"),
            _turn(lead="while I paid the money also", events=[handover]),
        ]
        assert _status("handover_on_payment_complaint", ok) == "pass"

    def test_human_request_needs_handover(self):
        t = [_turn(lead="I want to talk to a person now")]
        assert _status("handover_on_human_request", t) == "fail"
        t[0]["events"].append({"type": "handover", "reason": "asked"})
        assert _status("handover_on_human_request", t) == "pass"

    def test_unknown_twice_needs_any_handover(self):
        t = [_turn(lead="can they video call at 2am?"), _turn(lead="so can they or not?")]
        assert _status("handover_on_unknown_twice", t) == "fail"


class TestOptOut:
    def test_fails_when_menu_sent_after_refusal(self):
        menu = {"text": "Pick", "kind": "buttons", "options": ["a", "b"]}
        t = [_turn(lead="not interested, dont message me again", replies=[menu])]
        assert _status("respects_opt_out", t) == "fail"

    def test_passes_with_short_closing_line(self):
        t = [_turn(lead="not interested, dont message me again", replies=["Okay, no problem. Take care."])]
        assert _status("respects_opt_out", t) == "pass"


class TestRegistry:
    def test_unknown_check_is_skipped_not_passed(self):
        assert _status("language_matches", [_turn()]) == "skip"
        assert _status("window_respected", [_turn()]) == "skip"
