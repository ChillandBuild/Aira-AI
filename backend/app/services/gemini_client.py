# backend/app/services/gemini_client.py
import base64

import httpx
import lameenc

from app.config import settings

GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_GEMINI_VOICE = "Kore"
_PCM_SAMPLE_RATE = 24000
_PCM_CHANNELS = 1


def get_gemini_api_key() -> str:
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("Gemini API key not configured")
    return api_key


def _pcm_to_mp3(pcm_bytes: bytes) -> bytes:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(_PCM_SAMPLE_RATE)
    encoder.set_channels(_PCM_CHANNELS)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm_bytes) + encoder.flush())


async def gemini_text_to_speech(
    text: str,
    voice: str = DEFAULT_GEMINI_VOICE,
    model: str = DEFAULT_GEMINI_TTS_MODEL,
) -> bytes:
    """Sarvam Bulbul mispronounced Romanized Tanglish with a non-Tamil accent regardless
    of target_language_code (live-tested 2026-07-13/14, see subsystem-notes.md). Gemini's
    TTS is LLM-native rather than a classic grapheme-to-phoneme pipeline, and handles raw
    Roman-script Tanglish correctly with no code-switch preprocessing -- confirmed via live
    A/B audio testing. Returns MP3 bytes (transcoded from Gemini's raw PCM output via
    lameenc, since the API has no compressed-format response option and WhatsApp's Cloud
    API doesn't accept raw PCM)."""
    api_key = get_gemini_api_key()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            GEMINI_INTERACTIONS_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "input": text,
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": voice}]},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    steps = data.get("steps") or []
    content = steps[0].get("content") if steps else None
    if not content:
        raise RuntimeError("Gemini TTS returned no audio")
    pcm_bytes = base64.b64decode(content[0]["data"])
    return _pcm_to_mp3(pcm_bytes)
