import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import openrouter_client
from app.services.openrouter_client import openrouter_chat_completion


def test_openrouter_api_key_raises_when_missing():
    with patch("app.services.openrouter_client.settings") as mock_settings:
        mock_settings.openrouter_api_key = None
        with pytest.raises(RuntimeError, match="OpenRouter API key not configured"):
            openrouter_client.get_openrouter_api_key()


def test_openrouter_api_key_returns_platform_key():
    with patch("app.services.openrouter_client.settings") as mock_settings:
        mock_settings.openrouter_api_key = "platform-or-key"
        assert openrouter_client.get_openrouter_api_key() == "platform-or-key"


@pytest.mark.asyncio
async def test_openrouter_chat_completion_returns_stripped_message_content():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "  Hello there!  "}}]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.openrouter_client.get_openrouter_api_key", return_value="test-key"), \
         patch("app.services.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        text = await openrouter_chat_completion(
            messages=[{"role": "user", "content": "Hi"}], model="openai/gpt-5-mini"
        )

    assert text == "Hello there!"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://openrouter.ai/api/v1/chat/completions"
    assert call_kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert call_kwargs["json"]["model"] == "openai/gpt-5-mini"
    assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert call_kwargs["json"]["temperature"] == 0.4
    assert call_kwargs["json"]["max_tokens"] == 300


@pytest.mark.asyncio
async def test_openrouter_chat_completion_raises_when_api_key_missing():
    with patch(
        "app.services.openrouter_client.get_openrouter_api_key",
        side_effect=RuntimeError("OpenRouter API key not configured"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await openrouter_chat_completion(messages=[{"role": "user", "content": "Hi"}], model="openai/gpt-5-mini")
