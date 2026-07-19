import pytest
import base64
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import sarvam_client
from app.services.sarvam_client import sarvam_chat_completion


def test_sarvam_api_key_requires_tenant_key_for_tenant_calls():
    with patch("app.services.sarvam_client.get_setting", return_value=None), \
         patch("app.services.sarvam_client.settings") as mock_settings:
        mock_settings.sarvam_api_key = "platform-key"
        with pytest.raises(RuntimeError, match="Client Sarvam API key not configured"):
            sarvam_client.get_sarvam_api_key("tenant-1")


def test_sarvam_api_key_uses_platform_key_only_without_tenant():
    with patch("app.services.sarvam_client.get_setting") as get_setting, \
         patch("app.services.sarvam_client.settings") as mock_settings:
        mock_settings.sarvam_api_key = "platform-key"
        assert sarvam_client.get_sarvam_api_key() == "platform-key"
        get_setting.assert_not_called()


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
async def test_sarvam_text_to_speech_decodes_bulbul_audio_with_subscription_key():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"request_id": "req-1", "audios": [base64.b64encode(b"mp3-bytes").decode("ascii")]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.sarvam_client.get_sarvam_api_key", return_value="test-key"), \
         patch("app.services.sarvam_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        audio = await sarvam_client.sarvam_text_to_speech(
            text="Hello Prem",
            target_language_code="en-IN",
            tenant_id="tenant-1",
        )

    assert audio == b"mp3-bytes"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://api.sarvam.ai/text-to-speech"
    assert call_kwargs["headers"] == {"api-subscription-key": "test-key"}
    assert call_kwargs["json"] == {
        "text": "Hello Prem",
        "target_language_code": "en-IN",
        "speaker": "shubh",
        "model": "bulbul:v3",
        "output_audio_codec": "mp3",
        "speech_sample_rate": 24000,
        "pace": 1.0,
        "temperature": 0.6,
    }
