import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.groq_client import groq_chat_completion, groq_chat_completion_with_tools


@pytest.mark.asyncio
async def test_groq_chat_completion_returns_stripped_content():
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="  Hello there!  "))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client) as mock_groq_cls:
        text = await groq_chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="llama-3.3-70b-versatile",
            tenant_id="tenant-1",
        )

    assert text == "Hello there!"
    mock_groq_cls.assert_called_once_with(api_key="test-key")
    mock_client.chat.completions.create.assert_awaited_once_with(
        model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": "Hi"}], temperature=0.4, max_tokens=300,
    )


@pytest.mark.asyncio
async def test_groq_chat_completion_raises_when_tenant_key_missing():
    with patch(
        "app.services.groq_client.require_tenant_setting",
        side_effect=RuntimeError("groq_api_key not configured for this client"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await groq_chat_completion(messages=[{"role": "user", "content": "Hi"}], model="llama-3.3-70b-versatile", tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_groq_chat_completion_with_tools_returns_content_and_tool_calls():
    tool_call = MagicMock()
    tool_call.model_dump.return_value = {"id": "call_1", "type": "function", "function": {"name": "recommend_catalog_item", "arguments": "{}"}}
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="Here you go", tool_calls=[tool_call]))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client):
        content, tool_calls = await groq_chat_completion_with_tools(
            messages=[{"role": "user", "content": "show me cakes"}],
            tools=[{"type": "function", "function": {"name": "recommend_catalog_item"}}],
            model="llama-3.3-70b-versatile",
            tenant_id="tenant-1",
        )

    assert content == "Here you go"
    assert tool_calls == [{"id": "call_1", "type": "function", "function": {"name": "recommend_catalog_item", "arguments": "{}"}}]


@pytest.mark.asyncio
async def test_groq_chat_completion_with_tools_handles_no_tool_calls():
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="just text", tool_calls=None))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client):
        content, tool_calls = await groq_chat_completion_with_tools(
            messages=[{"role": "user", "content": "hi"}], tools=[], model="llama-3.3-70b-versatile", tenant_id="tenant-1",
        )

    assert content == "just text"
    assert tool_calls == []


@pytest.mark.asyncio
async def test_groq_chat_completion_passes_reasoning_format_hidden_for_qwen():
    """Live-tested 2026-07-14: Qwen3 32B emits an inline <think> block by default that eats
    the token budget and leaks the reasoning trace unless reasoning_format="hidden" is set.
    Passing that same param to a non-reasoning model like Llama 3.3 70B is a hard 400 --
    so it must only be included for models that actually need it."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="Vanakkam! Ready aagum."))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client):
        await groq_chat_completion(
            messages=[{"role": "user", "content": "hi"}], model="qwen/qwen3-32b", tenant_id="tenant-1",
        )

    mock_client.chat.completions.create.assert_awaited_once_with(
        model="qwen/qwen3-32b", messages=[{"role": "user", "content": "hi"}],
        temperature=0.4, max_tokens=300, reasoning_format="hidden",
    )


@pytest.mark.asyncio
async def test_groq_chat_completion_omits_reasoning_format_for_non_reasoning_model():
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="hi there"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client):
        await groq_chat_completion(
            messages=[{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile", tenant_id="tenant-1",
        )

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "reasoning_format" not in call_kwargs


@pytest.mark.asyncio
async def test_groq_chat_completion_with_tools_passes_reasoning_format_hidden_for_qwen():
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=None, tool_calls=None))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=resp)

    with patch("app.services.groq_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.groq_client.AsyncGroq", return_value=mock_client):
        await groq_chat_completion_with_tools(
            messages=[{"role": "user", "content": "hi"}], tools=[], model="qwen/qwen3-32b", tenant_id="tenant-1",
        )

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["reasoning_format"] == "hidden"
