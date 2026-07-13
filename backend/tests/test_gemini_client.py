import base64
import wave
import io

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import gemini_client


def _pcm_wav_bytes(samples: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(samples)
    return buf.getvalue()


def test_get_gemini_api_key_raises_when_missing():
    with patch("app.services.gemini_client.settings") as mock_settings:
        mock_settings.gemini_api_key = None
        with pytest.raises(RuntimeError, match="Gemini API key not configured"):
            gemini_client.get_gemini_api_key()


def test_get_gemini_api_key_returns_configured_key():
    with patch("app.services.gemini_client.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        assert gemini_client.get_gemini_api_key() == "test-key"


@pytest.mark.asyncio
async def test_gemini_text_to_speech_decodes_pcm_and_transcodes_to_mp3():
    pcm_samples = b"\x00\x01" * 100  # 100 frames of silence-ish 16-bit mono PCM
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "steps": [
            {"content": [{"mime_type": "audio/l16", "data": base64.b64encode(pcm_samples).decode("ascii")}]}
        ]
    }
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.gemini_client.get_gemini_api_key", return_value="test-key"), \
         patch("app.services.gemini_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        audio = await gemini_client.gemini_text_to_speech(text="Vanga sir, order ready ah irukku")

    assert isinstance(audio, bytes)
    assert len(audio) > 0
    # MP3 frame sync (0xFF + top 3 bits of next byte set) or an ID3 tag -- confirms lameenc
    # actually produced MP3, not a raw PCM passthrough
    assert (audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0) or audio[:3] == b"ID3"

    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert call_kwargs["headers"] == {"x-goog-api-key": "test-key", "Content-Type": "application/json"}
    assert call_kwargs["json"] == {
        "model": "gemini-2.5-flash-preview-tts",
        "input": "Vanga sir, order ready ah irukku",
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": "Kore"}]},
    }


@pytest.mark.asyncio
async def test_gemini_text_to_speech_raises_when_no_audio_returned():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"steps": []}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.gemini_client.get_gemini_api_key", return_value="test-key"), \
         patch("app.services.gemini_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        with pytest.raises(RuntimeError, match="no audio"):
            await gemini_client.gemini_text_to_speech(text="Hi")


@pytest.mark.asyncio
async def test_gemini_text_to_speech_raises_when_api_key_missing():
    with patch(
        "app.services.gemini_client.get_gemini_api_key",
        side_effect=RuntimeError("Gemini API key not configured"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await gemini_client.gemini_text_to_speech(text="Hi")
