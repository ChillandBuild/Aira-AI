# backend/app/services/gemini_client.py
import base64
import json

import httpx
import lameenc

from app.config import settings
from app.config_dynamic import require_tenant_setting

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


def _messages_to_gemini_input(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Gemini's /v1beta/interactions endpoint doesn't use OpenAI's messages array --
    system prompt goes in a separate system_instruction field, and conversation turns are
    a list of {type: user_input|model_output, content: [{type: text, text}]} steps. Live-
    tested 2026-07-14: prior-assistant-turn history uses "model_output" (the same type the
    API returns responses as), NOT "model_response" -- that type doesn't exist and 400s."""
    system_parts: list[str] = []
    steps: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            steps.append({"type": "model_output", "content": [{"type": "text", "text": content}]})
        else:
            steps.append({"type": "user_input", "content": [{"type": "text", "text": content}]})
    return ("\n\n".join(system_parts) if system_parts else None), steps


def _openai_tools_to_gemini(tools: list[dict]) -> list[dict]:
    """Gemini's function declarations are flat ({type, name, description, parameters}),
    unlike OpenAI/Sarvam's nested {type: function, function: {name, description, parameters}}."""
    gemini_tools = []
    for t in tools:
        func = t.get("function") or {}
        gemini_tools.append({
            "type": "function",
            "name": func.get("name"),
            "description": func.get("description"),
            "parameters": func.get("parameters"),
        })
    return gemini_tools


def _gemini_output_text(steps: list[dict]) -> str:
    """Extracts and concatenates text from model_output steps. Live-tested 2026-07-14:
    there is no top-level output_text convenience field on this endpoint (despite docs
    implying one) -- responses come back as a steps array that can include a "thought"
    step (reasoning trace, present by default on 3.x models) before the real
    "model_output" step, so thought steps must be skipped, not concatenated in."""
    parts = []
    for step in steps:
        if step.get("type") != "model_output":
            continue
        for c in step.get("content") or []:
            if c.get("type") == "text":
                parts.append(c.get("text") or "")
    return "".join(parts).strip()


def _gemini_steps_to_tool_calls(steps: list[dict]) -> list[dict]:
    """Converts Gemini's function_call steps back into the OpenAI-shaped tool_calls tuple
    the rest of the codebase (generate_reply's catalog handling) already expects."""
    tool_calls = []
    for i, step in enumerate(steps):
        if step.get("type") != "function_call":
            continue
        tool_calls.append({
            "id": step.get("id") or f"call_{i}",
            "type": "function",
            "function": {
                "name": step.get("name"),
                "arguments": json.dumps(step.get("arguments") or {}),
            },
        })
    return tool_calls


async def gemini_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> str:
    """Plain chat completion via Gemini's interactions endpoint. No fallback to a platform
    key -- every client must configure their own gemini_api_key (operator decision, see
    decisions/log.md)."""
    api_key = require_tenant_setting("gemini_api_key", tenant_id)
    system_instruction, input_steps = _messages_to_gemini_input(messages)
    request_json: dict = {
        "model": model,
        "input": input_steps,
        "generation_config": {"temperature": temperature, "max_output_tokens": max_tokens},
    }
    if system_instruction:
        request_json["system_instruction"] = system_instruction
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GEMINI_INTERACTIONS_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=request_json,
        )
        resp.raise_for_status()
        data = resp.json()
    return _gemini_output_text(data.get("steps") or [])


async def gemini_chat_completion_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
    tenant_id: str | None = None,
) -> tuple[str, list[dict]]:
    api_key = require_tenant_setting("gemini_api_key", tenant_id)
    system_instruction, input_steps = _messages_to_gemini_input(messages)
    request_json: dict = {
        "model": model,
        "input": input_steps,
        "tools": _openai_tools_to_gemini(tools),
        "generation_config": {"temperature": temperature, "max_output_tokens": max_tokens},
    }
    if system_instruction:
        request_json["system_instruction"] = system_instruction
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GEMINI_INTERACTIONS_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=request_json,
        )
        resp.raise_for_status()
        data = resp.json()
    steps = data.get("steps") or []
    content = _gemini_output_text(steps)
    tool_calls = _gemini_steps_to_tool_calls(steps)
    return content, tool_calls


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
