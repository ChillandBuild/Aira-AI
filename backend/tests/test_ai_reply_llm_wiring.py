import pytest
from unittest.mock import AsyncMock, patch

from app.services import ai_reply


@pytest.mark.asyncio
async def test_llm_complete_defaults_to_sarvam_when_no_tenant_setting():
    with patch.object(ai_reply, "get_setting", return_value=None), \
         patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
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
async def test_llm_complete_routes_to_openrouter_for_non_sarvam_model():
    with patch.object(ai_reply, "get_setting", return_value="openai/gpt-5-mini"), \
         patch.object(ai_reply, "openrouter_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="openai/gpt-5-mini",
        temperature=0.4,
        max_tokens=120,
    )


@pytest.mark.asyncio
async def test_llm_chat_defaults_to_sarvam_when_no_tenant_setting():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "get_setting", return_value=None), \
         patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=600,
        tenant_id="tenant-2",
    )


@pytest.mark.asyncio
async def test_llm_chat_routes_to_openrouter_for_non_sarvam_model():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "get_setting", return_value="google/gemini-2.5-flash"), \
         patch.object(ai_reply, "openrouter_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="google/gemini-2.5-flash",
        temperature=0.4,
        max_tokens=600,
    )


def test_default_reply_model_is_sarvam_30b():
    assert ai_reply._DEFAULT_REPLY_MODEL == "sarvam-30b"


@pytest.mark.asyncio
async def test_send_whatsapp_voice_reply_uses_sarvam_tts_and_meta_audio_upload():
    db = object()
    with patch("app.services.sarvam_client.sarvam_text_to_speech", AsyncMock(return_value=b"audio-bytes")) as tts, \
         patch("app.services.meta_cloud.upload_media_to_meta", AsyncMock(return_value="media-123")) as upload, \
         patch("app.services.meta_cloud.send_media_message", AsyncMock(return_value={"messages": [{"id": "wamid.voice.1"}]})) as send, \
         patch.object(ai_reply, "meter") as meter:
        mid = await ai_reply.send_whatsapp_voice_reply(
            to_phone="+919999999999",
            message="Hi Prem",
            tenant_id="tenant-1",
            phone_number_id="phone-number-1",
            speaker="shubh",
            pace=1.2,
            target_language_code="en-IN",
            db=db,
        )

    assert mid == "wamid.voice.1"
    tts.assert_awaited_once_with(
        text="Hi Prem",
        target_language_code="en-IN",
        speaker="shubh",
        pace=1.2,
        tenant_id="tenant-1",
    )
    meter.assert_called_once_with(db, "tenant-1", "ai_text_to_speech")
    upload.assert_awaited_once_with(
        file_bytes=b"audio-bytes",
        mime_type="audio/mpeg",
        filename="aira-reply.mp3",
        tenant_id="tenant-1",
        phone_number_id="phone-number-1",
    )
    send.assert_awaited_once_with(
        to_number="+919999999999",
        media_id="media-123",
        wa_type="audio",
        tenant_id="tenant-1",
        phone_number_id="phone-number-1",
    )


def test_generate_reply_uses_voice_only_for_audio_inbound_whatsapp_dispatch():
    import inspect
    source = inspect.getsource(ai_reply.generate_reply)
    signature = inspect.signature(ai_reply.generate_reply)
    assert "inbound_media_type" in signature.parameters
    assert "ai_voice_reply_enabled" in source
    assert "ai_voice_reply_speaker" in source
    assert "ai_voice_reply_pace" in source
    assert "ai_voice_reply_language_mode" in source
    assert "ai_voice_reply_language_code" in source
    assert 'inbound_media_type == "audio"' in source
    assert "send_whatsapp_voice_reply" in source
    assert "send_whatsapp(_wa_phone, reply_text" in source
