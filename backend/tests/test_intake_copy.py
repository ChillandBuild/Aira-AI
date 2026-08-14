import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import intake_copy as ic


@pytest.mark.asyncio
async def test_compose_line_returns_model_text():
    with patch.object(ic, "_llm_chat", new=AsyncMock(return_value="  Unga piranthaa ooru edhu?  ")):
        text = await ic.compose_line(
            "ask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="seri", field_label="Place of birth",
        )
    assert text == "Unga piranthaa ooru edhu?"


@pytest.mark.asyncio
async def test_compose_line_falls_back_to_english_on_llm_error():
    with patch.object(ic, "_llm_chat", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        text = await ic.compose_line(
            "ask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="seri", field_label="Place of birth",
        )
    assert text == "Great! Could you share your place of birth?"


@pytest.mark.asyncio
async def test_compose_line_falls_back_on_empty_reply():
    with patch.object(ic, "_llm_chat", new=AsyncMock(return_value="   ")):
        text = await ic.compose_line(
            "reask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="M3", field_label="Date of birth",
        )
    assert text == "Thanks! And your date of birth?"


@pytest.mark.asyncio
async def test_payment_intro_strips_any_url_the_model_invents():
    with patch.object(ic, "_llm_chat", new=AsyncMock(return_value="Idho unga link: https://evil.example/x")):
        text = await ic.compose_line(
            "payment_intro", tenant_id="t-1", language_mode="tanglish", customer_message="seri",
        )
    assert "http" not in text
    assert text.strip() != ""


@pytest.mark.asyncio
async def test_compose_wrapped_keeps_the_block_verbatim():
    block = "Full Name: Cheran\nDate of birth: 06.06.2000"
    with patch.object(ic, "_llm_chat_json", new=AsyncMock(return_value={
        "intro": "Naan eduthukitta vivarangal:", "question": "Idhu sariya?",
    })):
        text = await ic.compose_wrapped(
            "summary", tenant_id="t-1", language_mode="tanglish",
            customer_message="chidambaram", block=block,
        )
    assert block in text
    assert text.startswith("Naan eduthukitta vivarangal:")
    assert text.endswith("Idhu sariya?")


@pytest.mark.asyncio
async def test_compose_wrapped_falls_back_to_english_wrapper():
    block = "Full Name: Cheran"
    with patch.object(ic, "_llm_chat_json", new=AsyncMock(side_effect=RuntimeError("boom"))):
        text = await ic.compose_wrapped(
            "summary", tenant_id="t-1", language_mode="tanglish",
            customer_message="x", block=block,
        )
    assert text == "Here's what I've got:\n\nFull Name: Cheran\n\nIs that correct?"


def test_resolve_language_mode_passes_through_forced_modes():
    db = MagicMock()
    with patch.object(ic, "_resolve_reply_language_mode", return_value="tanglish"):
        assert ic.resolve_language_mode("lead-1", "t-1", db) == "tanglish"
    db.table.assert_not_called()


def test_resolve_language_mode_reads_tamil_lock_for_escalate_mode():
    db = MagicMock()
    row = MagicMock()
    row.data = {"tamil_locked": True}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    with patch.object(ic, "_resolve_reply_language_mode", return_value="tanglish_escalate_tamil"):
        assert ic.resolve_language_mode("lead-1", "t-1", db) == "tamil"


def test_resolve_language_mode_defaults_to_tanglish_when_unlocked():
    db = MagicMock()
    row = MagicMock()
    row.data = {"tamil_locked": False}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    with patch.object(ic, "_resolve_reply_language_mode", return_value="tanglish_escalate_tamil"):
        assert ic.resolve_language_mode("lead-1", "t-1", db) == "tanglish"


@pytest.mark.asyncio
async def test_gather_context_survives_a_broken_knowledge_lookup():
    db = MagicMock()
    rows = MagicMock()
    rows.data = [{"direction": "inbound", "content": "seri"}]
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = rows
    with patch("app.services.knowledge_service.get_knowledge_context", new=AsyncMock(side_effect=RuntimeError("down"))):
        thread, knowledge = await ic.gather_context(db, "lead-1", "t-1", "hello")
    assert thread == [{"direction": "inbound", "content": "seri"}]
    assert knowledge == ""


def test_unknown_purpose_is_rejected():
    with pytest.raises(ValueError):
        ic._fallback("not_a_purpose", None, None)


_FIELDS = [
    {"key": "full_name", "label": "Full Name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
]


@pytest.mark.asyncio
async def test_localized_fields_skips_translation_outside_tamil_mode():
    """Live decision 2026-08-14: labels stay English in every mode except the
    locked-native-Tamil one. No LLM call at all outside that mode -- free and
    behaviorally identical to before this feature existed."""
    with patch.object(ic, "_llm_chat_json", new=AsyncMock()) as mock_json:
        fields = await ic.localized_fields(_FIELDS, "tanglish", tenant_id="t-1")
    mock_json.assert_not_awaited()
    assert fields == _FIELDS


@pytest.mark.asyncio
async def test_localized_fields_translates_labels_in_tamil_mode():
    with patch.object(ic, "_llm_chat_json", new=AsyncMock(return_value={
        "full_name": "முழு பெயர்", "date_of_birth": "பிறந்த தேதி",
    })):
        fields = await ic.localized_fields(_FIELDS, "tamil", tenant_id="t-1")
    assert fields[0]["label"] == "முழு பெயர்"
    assert fields[1]["label"] == "பிறந்த தேதி"
    # keys and types untouched -- only the display label moves
    assert fields[0]["key"] == "full_name"
    assert fields[0]["type"] == "text"


@pytest.mark.asyncio
async def test_localized_fields_falls_back_on_llm_error():
    with patch.object(ic, "_llm_chat_json", new=AsyncMock(side_effect=RuntimeError("boom"))):
        fields = await ic.localized_fields(_FIELDS, "tamil", tenant_id="t-1")
    assert fields == _FIELDS


@pytest.mark.asyncio
async def test_localized_fields_falls_back_on_incomplete_translation():
    """All-or-nothing: a partial rewrite (one field translated, one not) is worse
    than the plain English original, so any missing key discards the whole result."""
    with patch.object(ic, "_llm_chat_json", new=AsyncMock(return_value={"full_name": "முழு பெயர்"})):
        fields = await ic.localized_fields(_FIELDS, "tamil", tenant_id="t-1")
    assert fields == _FIELDS


@pytest.mark.asyncio
async def test_localized_fields_never_touches_collected_values():
    captured = {}

    async def fake_json(system_prompt, user_prompt, tenant_id):
        captured["user_prompt"] = user_prompt
        return {"full_name": "முழு பெயர்", "date_of_birth": "பிறந்த தேதி"}

    with patch.object(ic, "_llm_chat_json", new=AsyncMock(side_effect=fake_json)):
        await ic.localized_fields(_FIELDS, "tamil", tenant_id="t-1")
    # only key + label are sent -- the lead's actual answers never reach this call
    assert "Prem" not in captured["user_prompt"]


def test_user_prompt_always_includes_flow_facts():
    """Live evidence 2026-08-13: a lead asked 'eppo astrologer enne contact
    pannuvange' (when will the astrologer contact me) mid-collection. The composer
    ignored 'eppo' and just re-asked the pending field, because the only thing it was
    ever told it could answer was retrieved KNOWLEDGE -- and 'when does the expert
    reply' isn't a business fact, it's flow state the composer was never given."""
    prompt = ic._user_prompt("do something", "tanglish", "eppo contact pannuvanga", None, "")
    assert "FLOW FACTS" in prompt
    assert "no fixed time" in prompt.lower() or "never state a" in prompt.lower()


def test_system_prompt_tells_the_model_to_answer_real_questions_first():
    assert "real question" in ic._SYSTEM_PROMPT.lower()
    assert "and nothing else" not in ic._SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_compose_payment_receipt_uses_the_leads_language_and_prepends_the_name():
    with patch.object(ic, "resolve_language_mode", return_value="tamil"), \
         patch("app.db.supabase.get_supabase", return_value=MagicMock()), \
         patch.object(ic, "_llm_chat", new=AsyncMock(return_value="Unga consultation confirm aayiduchu.")):
        text = await ic.compose_payment_receipt(
            lead_id="l-1", tenant_id="t-1", customer_name="Priya", service_noun="consultation",
        )
    assert text == "Priya, Unga consultation confirm aayiduchu."


@pytest.mark.asyncio
async def test_compose_payment_receipt_falls_back_to_english_on_error():
    with patch.object(ic, "resolve_language_mode", return_value="tamil"), \
         patch("app.db.supabase.get_supabase", return_value=MagicMock()), \
         patch.object(ic, "_llm_chat", new=AsyncMock(side_effect=RuntimeError("boom"))):
        text = await ic.compose_payment_receipt(
            lead_id="l-1", tenant_id="t-1", customer_name="Priya", service_noun="consultation",
        )
    assert text == "Priya, Your consultation is confirmed — our expert will be in touch here on WhatsApp shortly."


def test_reask_task_has_no_hardcoded_date_example():
    """Live evidence 2026-08-13: the reask instruction contained the literal example
    'a date as 06/06/2000', and the model asked for the DATE of birth -- already
    collected -- while re-asking for time of birth."""
    assert "06/06/2000" not in ic._TASKS["reask_field"]
    assert "{field_label} and nothing else" in ic._TASKS["reask_field"]


@pytest.mark.asyncio
async def test_compose_line_tells_the_model_what_is_already_collected():
    captured = {}

    async def fake_llm_chat(messages, max_tokens, tenant_id):
        captured["messages"] = messages
        return "Unga pirandha neram sollunga."

    with patch.object(ic, "_llm_chat", new=AsyncMock(side_effect=fake_llm_chat)):
        await ic.compose_line(
            "reask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="theriyathu", field_label="Time of Birth",
            collected={"full_name": "Prem", "date_of_birth": "6 july 2006"},
        )
    user_content = captured["messages"][1]["content"]
    assert "ALREADY COLLECTED" in user_content
    assert "6 july 2006" in user_content


@pytest.mark.asyncio
async def test_compose_line_carries_the_main_brain_identity():
    """The collector used to compose with only a tiny hand-written system prompt --
    no master prompt, no business description, no lead context -- so it read as a
    different, thinner assistant the moment the paid flow took over."""
    captured = {}

    async def fake_llm_chat(messages, max_tokens, tenant_id):
        captured["messages"] = messages
        return "Unga place of birth sollunga."

    with patch.object(ic, "_llm_chat", new=AsyncMock(side_effect=fake_llm_chat)), \
         patch.object(ic, "_brain_prompt", return_value="MASTER PROMPT\n\nBUSINESS DESCRIPTION:\nAstro stuff"):
        await ic.compose_line(
            "ask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="seri", field_label="Place of birth",
            brain_prompt="MASTER PROMPT\n\nBUSINESS DESCRIPTION:\nAstro stuff",
        )
    system_content = captured["messages"][0]["content"]
    assert "MASTER PROMPT" in system_content
    assert "BUSINESS DESCRIPTION" in system_content
    # the collector's own rules must still win over the general prompt
    assert "TASK" in system_content or "real question" in system_content.lower()


@pytest.mark.asyncio
async def test_compose_line_works_without_a_brain_prompt():
    with patch.object(ic, "_llm_chat", new=AsyncMock(return_value="Unga place of birth sollunga.")):
        text = await ic.compose_line(
            "ask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="seri", field_label="Place of birth",
        )
    assert text == "Unga place of birth sollunga."


@pytest.mark.asyncio
async def test_compose_line_sends_flow_facts_to_the_model():
    captured = {}

    async def fake_llm_chat(messages, max_tokens, tenant_id):
        captured["messages"] = messages
        return "Payment mudinjadhum astrologer reply pannuvanga. Unga place of birth sollunga."

    with patch.object(ic, "_llm_chat", new=AsyncMock(side_effect=fake_llm_chat)):
        text = await ic.compose_line(
            "reask_field", tenant_id="t-1", language_mode="tanglish",
            customer_message="eppo astrologer enne contact pannuvanga", field_label="Place of birth",
        )
    user_content = captured["messages"][1]["content"]
    assert "FLOW FACTS" in user_content
    assert text == "Payment mudinjadhum astrologer reply pannuvanga. Unga place of birth sollunga."
