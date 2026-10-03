"""A link the AI writes must come from the business's own material. 2026-10-04: it invented a Play Store
address (com.astrotamil.app) that returns 404, because the knowledge told it to write {{PLAY_STORE_LINK}}
and nothing fills that in. The URL button made the dead link look official."""
import asyncio

from app.services import choices, deal_actions, deal_turn

REAL = "https://astrotamil.co.in/app/questions"
INVENTED = "https://play.google.com/store/apps/details?id=com.astrotamil.app"
SYSTEM = f"You are Aira. Business info: the app is at {REAL} and consultations at https://astrotamil.co.in/app/consultation/"


def _turn(draft, *, system=SYSTEM, history=(), second=None):
    """Runs converse_once with a model that answers `draft` (then `second` on a retry). Returns (text, notes)."""
    ctx = deal_actions.DealContext(config={}, db=object(), lead_id="l", tenant_id="t", phone="", buttons_enabled=True)
    answers = [draft] + ([second] if second is not None else [draft])
    notes = []

    async def llm(messages, tools, max_tokens, tenant_id):
        notes.append(messages[-1]["content"])
        return answers[min(len(notes) - 1, len(answers) - 1)], []

    async def text_llm(messages, max_tokens, tenant_id):
        return ""

    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": "app link venum"}]
    import app.services.deal_turn as dt
    dt._state_line, original = (lambda ctx: "DEAL STATE stub"), dt._state_line
    try:
        text, _calls, _outcome = asyncio.run(dt.converse_once(messages, [], ctx, tenant_id="t", llm_with_tools=llm, llm=text_llm))
    finally:
        dt._state_line = original
    return text, notes


class TestUrlHelpers:
    def test_urls_are_found_and_trimmed(self):
        assert choices.urls_in("See https://a.com/x. And (https://b.com/y)!") == ["https://a.com/x", "https://b.com/y"]

    def test_the_same_address_matches_with_a_slash_scheme_or_case_difference(self):
        key = choices.url_key
        assert key("https://Astrotamil.co.in/app/consultation/") == key("http://www.astrotamil.co.in/app/consultation")


class TestStripUnverifiedLinks:
    def test_an_invented_link_is_removed_and_reported(self):
        text, removed = deal_turn.strip_unverified_links(f"Aama 😊 {INVENTED}\n\nApp-la features irukku.", SYSTEM)
        assert INVENTED not in text and removed == [INVENTED]
        assert "App-la features irukku." in text

    def test_a_link_from_the_business_information_is_kept(self):
        text, removed = deal_turn.strip_unverified_links(f"Inga paarunga: {REAL}.", SYSTEM)
        assert text == f"Inga paarunga: {REAL}." and removed == []

    def test_the_sentence_punctuation_after_a_removed_link_stays(self):
        text, _ = deal_turn.strip_unverified_links(f"Try {INVENTED}.", SYSTEM)
        assert text == "Try."

    def test_a_markdown_link_keeps_its_words_when_the_address_is_unknown(self):
        text, removed = deal_turn.strip_unverified_links(f"Please [download the app]({INVENTED}) now", SYSTEM)
        assert text == "Please download the app now" and removed == [INVENTED]

    def test_an_unfilled_placeholder_never_reaches_the_customer(self):
        text, removed = deal_turn.strip_unverified_links("Aama, app irukku 😊 {{PLAY_STORE_LINK}}", SYSTEM)
        assert "{{" not in text and removed == ["{{PLAY_STORE_LINK}}"]


class TestInAReplyTurn:
    def test_the_dead_play_store_link_is_not_sent(self):
        text, _ = _turn(f"Aama, AstroTamil app irukku 😊 {INVENTED}\n\nApp-la free question irukku.")
        assert "play.google.com" not in text and "App-la free question irukku." in text

    def test_the_model_is_told_why_and_can_answer_without_inventing(self):
        text, notes = _turn(f"Aama 😊 {INVENTED}", second="App link-ai team share pannuvanga.")
        assert len(notes) == 2 and "not in the business information" in notes[1]
        assert text == "App link-ai team share pannuvanga."

    def test_a_link_in_the_business_information_still_goes_out(self):
        text, _ = _turn(f"Sari, indha link-ai try panni paarunga: {REAL} 😊")
        assert REAL in text

    def test_a_dead_link_from_an_earlier_reply_is_not_trusted_again(self):
        history = [{"role": "assistant", "content": f"Aama 😊 {INVENTED}"}]
        text, _ = _turn(f"Sari, link: {INVENTED}", history=history)
        assert "play.google.com" not in text

    def test_a_raw_placeholder_is_removed(self):
        text, _ = _turn("Aama, app irukku 😊 {{PLAY_STORE_LINK}}")
        assert "{{" not in text
