# backend/app/services/sarvam_client.py
import base64

import httpx

from app.config_dynamic import get_setting
from app.config import settings

SARVAM_BASE_URL = "https://api.sarvam.ai"
SARVAM_CHAT_URL = f"{SARVAM_BASE_URL}/v1/chat/completions"
SARVAM_STT_URL = f"{SARVAM_BASE_URL}/speech-to-text"
SARVAM_TTS_URL = f"{SARVAM_BASE_URL}/text-to-speech"


def get_sarvam_api_key(tenant_id: str | None = None) -> str:
    if tenant_id:
        api_key = get_setting("sarvam_api_key", tenant_id=tenant_id)
        if not api_key:
            raise RuntimeError("Client Sarvam API key not configured")
        return api_key
    api_key = settings.sarvam_api_key
    if not api_key:
        raise RuntimeError("Sarvam API key not configured")
    return api_key


async def sarvam_chat_completion(
    messages: list[dict],
    model: str = "sarvam-30b",
    temperature: float = 0.4,
    max_tokens: int = 300,
    frequency_penalty: float = 0.5,
    tenant_id: str | None = None,
) -> str:
    """Sarvam's Chat Completions API (OpenAI-compatible response shape). Unlike the
    Speech-to-Text/Document Digitization endpoints (api-subscription-key header),
    this one uses standard Authorization: Bearer auth.

    reasoning_effort=None disables sarvam-30b/105b's default "medium" reasoning mode.
    Without it, the model spends its entire max_tokens budget on an internal
    reasoning_content trace and never reaches the actual answer -- content comes
    back null with finish_reason="length" regardless of max_tokens size, since the
    model treats reasoning as the priority output, not an optional pre-step.

    frequency_penalty=0.5 measurably reduced a degenerate-repetition failure mode
    seen in testing (the model looping the same sentence fragment verbatim several
    times before finishing) -- observed in ~1/10 baseline replies, 0/10 with this set."""
    api_key = get_sarvam_api_key(tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SARVAM_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_effort": None,
                "frequency_penalty": frequency_penalty,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def sarvam_speech_to_text(
    file_bytes: bytes,
    mime_type: str,
    filename: str = "audio.ogg",
    model: str = "saaras:v3",
    mode: str = "codemix",
    tenant_id: str | None = None,
) -> str:
    """Transcribe audio with Sarvam Saaras."""
    api_key = get_sarvam_api_key(tenant_id)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": api_key},
            files={"file": (filename, file_bytes, mime_type)},
            data={"model": model, "mode": mode},
        )
        resp.raise_for_status()
        data = resp.json()
    return (data.get("transcript") or "").strip()


async def sarvam_text_to_speech(
    text: str,
    target_language_code: str,
    speaker: str = "shubh",
    model: str = "bulbul:v3",
    output_audio_codec: str = "mp3",
    speech_sample_rate: int = 24000,
    pace: float = 1.0,
    temperature: float = 0.6,
    tenant_id: str | None = None,
) -> bytes:
    api_key = get_sarvam_api_key(tenant_id)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            SARVAM_TTS_URL,
            headers={"api-subscription-key": api_key},
            json={
                "text": text,
                "target_language_code": target_language_code,
                "speaker": speaker,
                "model": model,
                "output_audio_codec": output_audio_codec,
                "speech_sample_rate": speech_sample_rate,
                "pace": pace,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    audios = data.get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio")
    return base64.b64decode(audios[0])
