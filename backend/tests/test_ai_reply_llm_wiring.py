import pytest
from unittest.mock import AsyncMock, patch

from app.services import ai_reply


def _require_setting(model_value, key_should_raise=False):
    """Build a require_tenant_setting side_effect that mirrors the real function's
    per-key contract: "ai_reply_model" resolves to model_value; any other key (the
    provider's own API key, e.g. "gemini_api_key") resolves to a stub key unless
    key_should_raise is True, in which case that provider-key lookup raises instead.
    Needed because _resolve_provider now makes two separate require_tenant_setting
    calls (ai_reply_model, then {provider}_api_key) through the same mocked name --
    a single blanket return_value can't tell them apart."""
    def _side_effect(key, tenant_id):
        if key == "ai_reply_model":
            return model_value
        if key_should_raise:
            raise RuntimeError(f"{key} not configured for this client")
        return "key"
    return _side_effect


def test_provider_and_native_model_maps_all_known_prefixes():
    assert ai_reply._provider_and_native_model("sarvam-30b") == ("sarvam", "sarvam-30b")
    assert ai_reply._provider_and_native_model("sarvam-105b") == ("sarvam", "sarvam-105b")
    assert ai_reply._provider_and_native_model("google/gemini-3.1-flash-lite") == ("gemini", "gemini-3.1-flash-lite")
    assert ai_reply._provider_and_native_model("openai/gpt-5.4-nano-2026-03-17") == ("openai", "gpt-5.4-nano-2026-03-17")
    assert ai_reply._provider_and_native_model("groq/llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")


def test_provider_and_native_model_raises_for_unrecognized_model():
    with pytest.raises(RuntimeError, match="Unrecognized reply model"):
        ai_reply._provider_and_native_model("anthropic/claude-4")


def test_resolve_reply_model_raises_when_tenant_has_not_configured_one():
    """No silent fallback -- an unconfigured tenant gets no AI replies at all rather
    than quietly running on a hardcoded default model (operator decision, see
    decisions/log.md)."""
    with patch.object(
        ai_reply, "require_tenant_setting",
        side_effect=RuntimeError("ai_reply_model not configured for this client"),
    ) as mock_require:
        with pytest.raises(RuntimeError, match="ai_reply_model not configured"):
            ai_reply._resolve_reply_model("tenant-1")
    mock_require.assert_called_once_with("ai_reply_model", "tenant-1")


def test_resolve_provider_raises_when_tenant_key_not_configured():
    with patch.object(
        ai_reply, "require_tenant_setting",
        side_effect=_require_setting("google/gemini-3.1-flash-lite", key_should_raise=True),
    ) as mock_require:
        with pytest.raises(RuntimeError, match="gemini_api_key not configured"):
            ai_reply._resolve_provider("tenant-1")
    mock_require.assert_any_call("ai_reply_model", "tenant-1")
    mock_require.assert_any_call("gemini_api_key", "tenant-1")


@pytest.mark.asyncio
async def test_llm_complete_raises_when_no_tenant_reply_model_configured():
    with patch.object(
        ai_reply, "require_tenant_setting",
        side_effect=RuntimeError("ai_reply_model not configured for this client"),
    ):
        with pytest.raises(RuntimeError, match="ai_reply_model not configured"):
            await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_llm_complete_routes_to_sarvam_for_sarvam_model():
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("sarvam-30b")), \
         patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_complete_routes_to_gemini_and_strips_prefix():
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("google/gemini-3.1-flash-lite")), \
         patch.object(ai_reply, "gemini_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="gemini-3.1-flash-lite",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_complete_routes_to_openai_and_strips_prefix():
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("openai/gpt-5.4-nano-2026-03-17")), \
         patch.object(ai_reply, "openai_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="gpt-5.4-nano-2026-03-17",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_complete_routes_to_groq_and_strips_prefix():
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("groq/llama-3.3-70b-versatile")), \
         patch.object(ai_reply, "groq_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="llama-3.3-70b-versatile",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_chat_raises_when_no_tenant_reply_model_configured():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(
        ai_reply, "require_tenant_setting",
        side_effect=RuntimeError("ai_reply_model not configured for this client"),
    ):
        with pytest.raises(RuntimeError, match="ai_reply_model not configured"):
            await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")


@pytest.mark.asyncio
async def test_llm_chat_routes_to_gemini_for_google_prefixed_model():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("google/gemini-3.5-flash")), \
         patch.object(ai_reply, "gemini_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="gemini-3.5-flash",
        temperature=0.4,
        max_tokens=600,
        tenant_id="tenant-2",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_chat_with_tools_raises_when_no_tenant_reply_model_configured():
    messages = [{"role": "user", "content": "show me cakes"}]
    tools = [{"type": "function", "function": {"name": "recommend_catalog_item"}}]
    with patch.object(
        ai_reply, "require_tenant_setting",
        side_effect=RuntimeError("ai_reply_model not configured for this client"),
    ):
        with pytest.raises(RuntimeError, match="ai_reply_model not configured"):
            await ai_reply._llm_chat_with_tools(messages, tools, max_tokens=600, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_llm_chat_with_tools_routes_to_sarvam_for_sarvam_model():
    messages = [{"role": "user", "content": "show me cakes"}]
    tools = [{"type": "function", "function": {"name": "recommend_catalog_item"}}]
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("sarvam-30b")), \
         patch.object(ai_reply, "sarvam_chat_completion_with_tools", AsyncMock(return_value=("here", []))) as mock_call:
        content, tool_calls = await ai_reply._llm_chat_with_tools(messages, tools, max_tokens=600, tenant_id="tenant-1")

    assert (content, tool_calls) == ("here", [])
    mock_call.assert_called_once_with(
        messages=messages, tools=tools, model="sarvam-30b", max_tokens=600, tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_chat_with_tools_routes_to_gemini_and_strips_prefix():
    messages = [{"role": "user", "content": "show me cakes"}]
    tools = [{"type": "function", "function": {"name": "recommend_catalog_item"}}]
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("google/gemini-3.1-flash-lite")), \
         patch.object(ai_reply, "gemini_chat_completion_with_tools", AsyncMock(return_value=("here", []))) as mock_call:
        content, tool_calls = await ai_reply._llm_chat_with_tools(messages, tools, max_tokens=600, tenant_id="tenant-1")

    assert (content, tool_calls) == ("here", [])
    mock_call.assert_called_once_with(
        messages=messages, tools=tools, model="gemini-3.1-flash-lite", max_tokens=600, tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_chat_with_tools_routes_to_openai_and_strips_prefix():
    messages = [{"role": "user", "content": "show me cakes"}]
    tools = [{"type": "function", "function": {"name": "recommend_catalog_item"}}]
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("openai/gpt-5-nano-2025-08-07")), \
         patch.object(ai_reply, "openai_chat_completion_with_tools", AsyncMock(return_value=("here", []))) as mock_call:
        content, tool_calls = await ai_reply._llm_chat_with_tools(messages, tools, max_tokens=600, tenant_id="tenant-1")

    assert (content, tool_calls) == ("here", [])
    mock_call.assert_called_once_with(
        messages=messages, tools=tools, model="gpt-5-nano-2025-08-07", max_tokens=600, tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_llm_chat_with_tools_routes_to_groq_and_strips_prefix():
    messages = [{"role": "user", "content": "show me cakes"}]
    tools = [{"type": "function", "function": {"name": "recommend_catalog_item"}}]
    with patch.object(ai_reply, "require_tenant_setting", side_effect=_require_setting("groq/llama-3.3-70b-versatile")), \
         patch.object(ai_reply, "groq_chat_completion_with_tools", AsyncMock(return_value=("here", []))) as mock_call:
        content, tool_calls = await ai_reply._llm_chat_with_tools(messages, tools, max_tokens=600, tenant_id="tenant-1")

    assert (content, tool_calls) == ("here", [])
    mock_call.assert_called_once_with(
        messages=messages, tools=tools, model="llama-3.3-70b-versatile", max_tokens=600, tenant_id="tenant-1",
        purpose="ai_reply",
    )


@pytest.mark.asyncio
async def test_send_whatsapp_voice_reply_uses_gemini_tts_and_meta_audio_upload():
    db = object()
    with patch("app.services.gemini_client.gemini_text_to_speech", AsyncMock(return_value=b"audio-bytes")) as tts, \
         patch("app.services.meta_cloud.upload_media_to_meta", AsyncMock(return_value="media-123")) as upload, \
         patch("app.services.meta_cloud.send_media_message", AsyncMock(return_value={"messages": [{"id": "wamid.voice.1"}]})) as send, \
         patch.object(ai_reply, "meter") as meter:
        mid = await ai_reply.send_whatsapp_voice_reply(
            to_phone="+919999999999",
            message="Hi Prem",
            tenant_id="tenant-1",
            phone_number_id="phone-number-1",
            speaker="Kore",
            db=db,
        )

    assert mid == "wamid.voice.1"
    tts.assert_awaited_once_with(text="Hi Prem", voice="Kore", tenant_id="tenant-1")
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


@pytest.mark.asyncio
async def test_send_whatsapp_voice_reply_defaults_to_default_gemini_voice_when_no_speaker():
    from app.services.gemini_client import DEFAULT_GEMINI_VOICE
    with patch("app.services.gemini_client.gemini_text_to_speech", AsyncMock(return_value=b"audio-bytes")) as tts, \
         patch("app.services.meta_cloud.upload_media_to_meta", AsyncMock(return_value="media-123")), \
         patch("app.services.meta_cloud.send_media_message", AsyncMock(return_value={"messages": [{"id": "wamid.voice.1"}]})):
        await ai_reply.send_whatsapp_voice_reply(
            to_phone="+919999999999", message="Hi Prem", tenant_id="tenant-1",
        )

    tts.assert_awaited_once_with(text="Hi Prem", voice=DEFAULT_GEMINI_VOICE, tenant_id="tenant-1")


def test_generate_reply_uses_voice_only_for_audio_inbound_whatsapp_dispatch():
    import inspect
    source = inspect.getsource(ai_reply.generate_reply)
    signature = inspect.signature(ai_reply.generate_reply)
    assert "inbound_media_type" in signature.parameters
    assert "ai_voice_reply_enabled" in source
    assert "ai_voice_reply_speaker" in source
    assert 'inbound_media_type == "audio"' in source
    assert "send_whatsapp_voice_reply" in source
    assert "send_whatsapp(_wa_phone, reply_text" in source
