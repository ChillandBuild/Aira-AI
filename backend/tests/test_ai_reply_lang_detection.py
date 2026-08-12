import inspect
from unittest.mock import MagicMock

from app.services import ai_reply
from app.services.ai_reply import (
    _AI_ESCALATION_RE,
    _detect_lang,
    _dominant_script,
    _FALLBACK_BY_LANG,
    _is_explicit_language_switch_request,
    _language_rule_block,
    _latest_message_script_note,
    _LANGUAGE_MODES,
    _regen_target_instruction,
    _reply_script_mismatch,
    _resolve_reply_language_mode,
    _resolve_tamil_lock,
)


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


def test_dominant_script_detects_tamil():
    assert _dominant_script("என் ஜாதகம் பார்க்கணும்") == "ta"


def test_dominant_script_ignores_tanglish_keywords():
    """Unlike _detect_lang, _dominant_script has no keyword fallback -- Latin-script
    Tanglish is indistinguishable from plain English at the script level, by design."""
    assert _dominant_script("En jadhagam paakanum") == "en"


def test_dominant_script_detects_telugu_kannada_malayalam_hindi():
    assert _dominant_script("నా జాతకం చూడాలి") == "te"
    assert _dominant_script("ನನ್ನ ಜಾತಕ ನೋಡಬೇಕು") == "kn"
    assert _dominant_script("എന്റെ ജാതകം നോക്കണം") == "ml"
    assert _dominant_script("मेरी जन्म कुंडली देखनी है") == "hi"


def test_dominant_script_defaults_to_english_for_empty_text():
    assert _dominant_script("") == "en"


def test_latest_message_script_note_for_tamil_script():
    note = _latest_message_script_note("நல்லா இருக்கு, order பண்ணலாமா?")
    assert note == "Tamil script. Reply in Tamil script."


def test_latest_message_script_note_for_latin_script():
    note = _latest_message_script_note("ok never mind, cancel it please")
    assert note == "Latin/English script. Do not reply in Tamil script."


def test_latest_message_script_note_does_not_force_english_over_tanglish():
    """The note must only gate script (Tamil vs Latin), never pick English over
    Tanglish within Latin script -- that call stays with the model reading raw text."""
    note = _latest_message_script_note("eppo delivery aagum?")
    assert "Reply in English" not in note
    assert note == "Latin/English script. Do not reply in Tamil script."


def test_generate_reply_injects_latest_message_script_note():
    # Lives inside _language_rule_block's "mirror" branch (the default reply_language_mode)
    # since the reply_language_mode refactor -- generate_reply calls it, it doesn't inline
    # the LANGUAGE RULE text itself anymore.
    source = inspect.getsource(ai_reply._language_rule_block)
    assert "_latest_message_script_note(message)" in source
    assert "CUSTOMER'S LATEST MESSAGE SCRIPT" in source


def test_explicit_switch_request_matches_prompt_examples():
    assert _is_explicit_language_switch_request("in English please")
    assert _is_explicit_language_switch_request("tamil-la sollunga")
    assert _is_explicit_language_switch_request("reply in tamil")


def test_explicit_switch_request_false_for_ordinary_message():
    assert not _is_explicit_language_switch_request("eppo delivery aagum?")
    assert not _is_explicit_language_switch_request("நல்லா இருக்கு, order பண்ணலாமா?")


def test_reply_script_mismatch_detects_silent_switch_to_tamil():
    customer_msg = "நல்லா இருக்கு, order பண்ணலாமா?"
    wrong_reply = "Sari, order pannunga sir."
    assert _reply_script_mismatch(customer_msg, wrong_reply)


def test_reply_script_mismatch_detects_silent_switch_to_english():
    customer_msg = "ok never mind, cancel it please"
    wrong_reply = "சரி சார், cancel பண்ணிடலாம்."
    assert _reply_script_mismatch(customer_msg, wrong_reply)


def test_reply_script_mismatch_false_when_scripts_agree():
    assert not _reply_script_mismatch("eppo delivery aagum?", "3-4 days aagum sir.")
    assert not _reply_script_mismatch("எப்போது டெலிவரி ஆகும்?", "நாளைக்கு சார்.")


def test_reply_script_mismatch_false_for_explicit_switch_request():
    """The model correctly switching script to fulfil 'tamil-la sollunga' must not
    be flagged as a bug -- that case is already 3/3 reliable and must be left alone."""
    assert not _reply_script_mismatch("tamil-la sollunga", "சரி சார், தமிழில் சொல்றேன்")


def test_generate_reply_wires_in_script_mismatch_regeneration():
    source = inspect.getsource(ai_reply.generate_reply)
    assert "_reply_script_mismatch(message, reply_text)" in source
    assert "regen_messages" in source


def test_regen_target_instruction_names_english_explicitly():
    """Must name the actual language, not just 'Latin script' -- a vague script-only
    instruction let the model drift into literal Latin (the dead language) in live
    testing, since any Latin-alphabet output technically satisfies 'not Tamil script'."""
    instruction = _regen_target_instruction("ok never mind, cancel it please")
    assert "English" in instruction
    assert "Latin script" not in instruction


def test_regen_target_instruction_names_tamil_for_tamil_script_customer_message():
    instruction = _regen_target_instruction("நல்லா இருக்கு, order பண்ணலாமா?")
    assert "Tamil" in instruction


def test_generate_reply_regen_call_carries_no_conversation_history():
    """The regen call must be an isolated rewrite, not a 'continue the chat' call --
    live-tested 2026-07-13: feeding the wrong reply back into full conversation
    history mostly failed (1/6) because it re-triggers the same anchor. An isolated
    call with no prior turns fixed it 10/10."""
    source = inspect.getsource(ai_reply.generate_reply)
    regen_block = source[source.index('elif reply_language_mode == "mirror" and _reply_script_mismatch(message, reply_text):'):]
    regen_block = regen_block[: regen_block.index("except Exception as regen_err")]
    assert "chat_messages +" not in regen_block
    assert "_regen_target_instruction(message)" in regen_block


def test_resolve_reply_language_mode_defaults_to_mirror_with_no_tenant():
    assert _resolve_reply_language_mode(None) == "mirror"


def test_resolve_reply_language_mode_rejects_unknown_stored_value(monkeypatch):
    monkeypatch.setattr(ai_reply, "get_setting", lambda *a, **k: "some-typo-value")
    assert _resolve_reply_language_mode("tenant-1") == "mirror"


def test_language_rule_block_mirror_matches_original_wording():
    block = _language_rule_block("mirror", "Hi")
    assert "LANGUAGE RULE" in block
    assert "SAME language style" in block
    assert "CUSTOMER'S LATEST MESSAGE SCRIPT" in block


def test_language_rule_block_tanglish_forces_tanglish_regardless_of_input():
    block = _language_rule_block("tanglish", "நல்லா இருக்கு")
    assert "Tanglish" in block
    assert "always" in block.lower()


def test_language_rule_block_english_forces_english_regardless_of_input():
    block = _language_rule_block("english", "நல்லா இருக்கு")
    assert "English only" in block


def test_language_rule_block_tamil_forces_native_script_regardless_of_input():
    block = _language_rule_block("tamil", "Hi there")
    assert "native Tamil script" in block


def test_ai_escalation_re_matches_tanglish_verb_final_grammar():
    """Live-tested 2026-07-17: Gemini's natural Tanglish escalation phrasing puts the
    noun before the verb, joined by a Tamil postposition (kooda/oda/kitta), not English
    word order -- 3/3 real replies in this shape were missed before this pattern was added."""
    assert _AI_ESCALATION_RE.search("naan innum unga team-kooda connect panna vendiyadhu irukku.")
    assert _AI_ESCALATION_RE.search("naan ungalai enga team kooda connect panren.")


def test_ai_escalation_re_matches_tamil_script():
    assert _AI_ESCALATION_RE.search("குழுவுடன் இணைக்கிறேன், விரைவில் தொடர்பு கொள்வோம்.")


def test_ai_escalation_re_does_not_false_positive_on_ordinary_tanglish_reply():
    """Regression guard for the Tanglish-grammar pattern above -- must not fire on
    ordinary consultation/booking language that isn't an AI-to-human handoff."""
    assert not _AI_ESCALATION_RE.search(
        "namma astrologer kitta oru detailed consultation eduthukitta, "
        "avanga ungaluku clear-ana vilakkathaiyum, parigarangalaiyum solluvanga."
    )
    assert not _AI_ESCALATION_RE.search("enga astrologer kitta pesi unga doubts-a clear pannalam.")


# ── _resolve_tamil_lock tests ──────────────────────────────────────────────────


def test_resolve_tamil_lock_returns_tanglish_for_tanglish_message_when_not_locked():
    db = MagicMock()
    result = _resolve_tamil_lock(db, "lead-1", {}, "eppo varuvinga")
    assert result == "tanglish"
    db.table.assert_not_called()


def test_resolve_tamil_lock_stays_tanglish_for_a_plain_tamil_script_message():
    """Tenant decision 2026-08-13: writing in Tamil script is not a request to be
    spoken to in Tamil. Only an explicit request, in Tamil script, flips the lock."""
    db = MagicMock()
    result = _resolve_tamil_lock(db, "lead-1", {}, "என் ஜாதகம் பார்க்கணும்")
    assert result == "tanglish"
    db.table.assert_not_called()


def test_resolve_tamil_lock_returns_tamil_and_updates_for_tamil_script_request():
    db = MagicMock()
    result = _resolve_tamil_lock(db, "lead-1", {}, "தமிழ்ல பேசுங்க")
    assert result == "tamil"
    db.table("leads").update.assert_called_once_with({"tamil_locked": True})


def test_resolve_tamil_lock_returns_tamil_without_touching_db_when_already_locked():
    db = MagicMock()
    result = _resolve_tamil_lock(db, "lead-1", {"tamil_locked": True}, "hello")
    assert result == "tamil"
    db.table.assert_not_called()


def test_tanglish_escalate_tamil_is_in_language_modes():
    assert "tanglish_escalate_tamil" in _LANGUAGE_MODES


def test_resolve_reply_language_mode_recognizes_tanglish_escalate_tamil(monkeypatch):
    monkeypatch.setattr(ai_reply, "get_setting", lambda *a, **k: "tanglish_escalate_tamil")
    assert _resolve_reply_language_mode("tenant-1") == "tanglish_escalate_tamil"
