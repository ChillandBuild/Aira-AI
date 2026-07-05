import inspect

from app.services import ai_reply
from app.services.ai_reply import _detect_lang, _FALLBACK_BY_LANG


def test_detects_tamil_script():
    assert _detect_lang("என் ஜாதகம் பார்க்கணும்") == "ta"


def test_detects_plain_english():
    assert _detect_lang("I need to check my horoscope") == "en"


def test_detects_tanglish_from_keyword_markers():
    assert _detect_lang("En jadhagam paakanum") == "tanglish"


def test_detects_tanglish_for_marriage_query():
    assert _detect_lang("Enaku marriage eppo") == "tanglish"


def test_detects_tanglish_for_dob_share_message():
    assert _detect_lang("DOB share panren") == "tanglish"


def test_empty_text_defaults_to_english():
    assert _detect_lang("") == "en"


def test_ambiguous_greeting_defaults_to_english_not_tanglish():
    assert _detect_lang("Hi") == "en"


def test_tanglish_has_a_fallback_entry():
    assert "tanglish" in _FALLBACK_BY_LANG


def test_generate_reply_does_not_inject_a_language_tag_into_the_user_message():
    """Static check: the final user turn sent to the LLM must be the customer's raw
    message, not a code-computed [Respond in X] tag. That tag used to override even
    a tenant's own, more accurate language-mirroring instructions (see AI Tune)
    whenever _detect_lang()'s crude keyword-list heuristic disagreed with what the
    model would have correctly figured out on its own from the raw text -- confirmed
    live: the same prompt + raw message produced correct Tanglish without the tag,
    but English (wrong) with it, because the heuristic misdetected the input."""
    source = inspect.getsource(ai_reply.generate_reply)
    assert "[Respond in" not in source

    module_source = inspect.getsource(ai_reply)
    assert "_LANG_NAMES" not in module_source
