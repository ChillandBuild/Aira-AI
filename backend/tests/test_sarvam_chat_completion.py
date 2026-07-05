import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import sarvam_client
from app.services.sarvam_client import sarvam_chat_completion


@pytest.mark.asyncio
async def test_sarvam_chat_completion_returns_stripped_message_content():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "  Hello there!  "}}]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.sarvam_client.get_sarvam_api_key", return_value="test-key"), \
         patch("app.services.sarvam_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        text = await sarvam_chat_completion(
            messages=[{"role": "user", "content": "Hi"}], model="sarvam-30b"
        )

    assert text == "Hello there!"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://api.sarvam.ai/v1/chat/completions"
    assert call_kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert call_kwargs["json"]["model"] == "sarvam-30b"
    assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert call_kwargs["json"]["reasoning_effort"] is None
    assert call_kwargs["json"]["frequency_penalty"] == 0.5


@pytest.mark.asyncio
async def test_sarvam_chat_completion_raises_on_http_failure():
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(side_effect=Exception("503 Service Unavailable"))

    with patch("app.services.sarvam_client.get_sarvam_api_key", return_value="test-key"), \
         patch("app.services.sarvam_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        with pytest.raises(Exception, match="503"):
            await sarvam_chat_completion(messages=[{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_sarvam_chat_completion_raises_when_api_key_missing():
    with patch(
        "app.services.sarvam_client.get_sarvam_api_key",
        side_effect=RuntimeError("Sarvam API key not configured"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await sarvam_chat_completion(messages=[{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_sarvam_speech_to_text_posts_audio_bytes_with_subscription_key():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"transcript": "  Andheri la flat venum  "}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.sarvam_client.get_sarvam_api_key", return_value="test-key"), \
         patch("app.services.sarvam_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        text = await sarvam_client.sarvam_speech_to_text(
            file_bytes=b"audio-bytes",
            mime_type="audio/ogg",
            filename="voice.ogg",
            mode="codemix",
            tenant_id="tenant-1",
        )

    assert text == "Andheri la flat venum"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://api.sarvam.ai/speech-to-text"
    assert call_kwargs["headers"] == {"api-subscription-key": "test-key"}
    assert call_kwargs["files"] == {"file": ("voice.ogg", b"audio-bytes", "audio/ogg")}
    assert call_kwargs["data"] == {"model": "saaras:v3", "mode": "codemix"}
