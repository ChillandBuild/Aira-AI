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
