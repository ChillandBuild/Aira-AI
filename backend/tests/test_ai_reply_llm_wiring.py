import pytest
from unittest.mock import AsyncMock, patch

from app.services import ai_reply


@pytest.mark.asyncio
async def test_llm_complete_calls_sarvam_with_reply_model():
    with patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_llm_chat_calls_sarvam_with_reply_model():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=600,
        tenant_id="tenant-2",
    )


def test_reply_model_is_sarvam_30b():
    assert ai_reply._REPLY_MODEL == "sarvam-30b"
