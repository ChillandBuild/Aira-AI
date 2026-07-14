import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import openai_client
from app.services.openai_client import openai_chat_completion, openai_chat_completion_with_tools


@pytest.mark.asyncio
async def test_openai_chat_completion_returns_stripped_content():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "  Hello there!  "}}]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.openai_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        text = await openai_chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-5.4-nano-2026-03-17",
            tenant_id="tenant-1",
        )

    assert text == "Hello there!"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://api.openai.com/v1/chat/completions"
    assert call_kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert call_kwargs["json"]["model"] == "gpt-5.4-nano-2026-03-17"
    assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_openai_chat_completion_raises_when_tenant_key_missing():
    with patch(
        "app.services.openai_client.require_tenant_setting",
        side_effect=RuntimeError("openai_api_key not configured for this client"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await openai_chat_completion(messages=[{"role": "user", "content": "Hi"}], model="gpt-5-nano-2025-08-07", tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_openai_chat_completion_with_tools_returns_content_and_tool_calls():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{
            "message": {
                "content": "  Here you go  ",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "recommend_catalog_item", "arguments": "{}"}}],
            }
        }]
    }
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.openai_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        content, tool_calls = await openai_chat_completion_with_tools(
            messages=[{"role": "user", "content": "show me cakes"}],
            tools=[{"type": "function", "function": {"name": "recommend_catalog_item"}}],
            model="gpt-5.4-nano-2026-03-17",
            tenant_id="tenant-1",
        )

    assert content == "Here you go"
    assert tool_calls == [{"id": "call_1", "type": "function", "function": {"name": "recommend_catalog_item", "arguments": "{}"}}]
    call_kwargs = mock_instance.post.call_args.kwargs
    assert call_kwargs["json"]["tools"] == [{"type": "function", "function": {"name": "recommend_catalog_item"}}]


@pytest.mark.asyncio
async def test_openai_chat_completion_with_tools_handles_missing_tool_calls():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "just text"}}]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.openai_client.require_tenant_setting", return_value="test-key"), \
         patch("app.services.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        content, tool_calls = await openai_chat_completion_with_tools(
            messages=[{"role": "user", "content": "hi"}], tools=[], model="gpt-5-nano-2025-08-07", tenant_id="tenant-1",
        )

    assert content == "just text"
    assert tool_calls == []
