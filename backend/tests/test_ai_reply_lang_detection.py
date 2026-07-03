from app.services.ai_reply import _detect_lang, _LANG_NAMES, _FALLBACK_BY_LANG


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


def test_tanglish_has_a_name_and_fallback_entry():
    assert "tanglish" in _LANG_NAMES
    assert "tanglish" in _FALLBACK_BY_LANG
