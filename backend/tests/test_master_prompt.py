from unittest.mock import patch

from app.services import ai_reply


def test_build_base_prompt_includes_master_channel_and_description():
    with patch.object(ai_reply, "_get_prompt", return_value="MASTER BEHAVIOUR"), \
         patch.object(ai_reply, "get_setting", return_value="We sell birth-chart readings."):
        result = ai_reply._build_base_prompt("whatsapp", "tenant-1")

    assert "MASTER BEHAVIOUR" in result
    assert "WhatsApp" in result
    assert "BUSINESS DESCRIPTION:" in result
    assert "We sell birth-chart readings." in result
    # Description must come after the master prompt, never before it.
    assert result.index("MASTER BEHAVIOUR") < result.index("BUSINESS DESCRIPTION:")


def test_build_base_prompt_omits_description_block_when_unset():
    with patch.object(ai_reply, "_get_prompt", return_value="MASTER BEHAVIOUR"), \
         patch.object(ai_reply, "get_setting", return_value=None):
        result = ai_reply._build_base_prompt("telegram", "tenant-1")

    assert "MASTER BEHAVIOUR" in result
    assert "Telegram" in result
    assert "BUSINESS DESCRIPTION:" not in result


def test_build_base_prompt_reads_the_master_row():
    with patch.object(ai_reply, "_get_prompt", return_value="M") as mock_get, \
         patch.object(ai_reply, "get_setting", return_value=None):
        ai_reply._build_base_prompt("instagram", "tenant-9")

    mock_get.assert_called_once_with("master", tenant_id="tenant-9")


def test_build_base_prompt_labels_every_channel():
    labels = {
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "instagram": "Instagram",
        "facebook": "Facebook Messenger",
    }
    for channel, label in labels.items():
        with patch.object(ai_reply, "_get_prompt", return_value="M"), \
             patch.object(ai_reply, "get_setting", return_value=None):
            assert label in ai_reply._build_base_prompt(channel, "t")


def test_language_rule_mirror_mode_wording_is_unchanged():
    """The mirror-mode LANGUAGE RULE wording is live-tested (12/12 on Gemini 3.1 Flash
    Lite; an aggressive rewording made gpt-5-nano return empty replies 0/8). If this
    test fails, the wording was edited -- re-run that live test before accepting it."""
    block = ai_reply._language_rule_block("mirror", "hello")
    assert "LANGUAGE RULE: Reply in the SAME language style the user just wrote in." in block
    assert "Tanglish" in block
    assert "CUSTOMER'S LATEST MESSAGE SCRIPT:" in block


def test_language_rule_forced_modes_still_present():
    assert "Your reply style is always Tanglish" in ai_reply._language_rule_block("tanglish", "hi")
    assert "Always reply in English only" in ai_reply._language_rule_block("english", "hi")
    assert "Always reply in native Tamil script" in ai_reply._language_rule_block("tamil", "hi")


def test_accuracy_rule_still_forbids_stating_prices():
    assert "ACCURACY RULE:" in ai_reply._ACCURACY_RULE
    assert "Never state a specific price, fee, or payment method" in ai_reply._ACCURACY_RULE
