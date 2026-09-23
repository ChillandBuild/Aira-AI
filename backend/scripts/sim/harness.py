"""Run the real reply pipeline without anything leaving the building.

generate_reply() is called unmodified -- real RAG, real catalog retrieval, real
intake state, real language rules, real scoring, real DB writes. Only the outward
edges are replaced: Meta's send endpoints, staff notifications, and the silence
nudge timer. Everything patched here is a thing that would reach a human.

Alongside the stubbing, this captures what the pipeline built: the exact assembled
system prompt, the full chat message list, the tool definitions offered, and the
reply. That capture is the point -- texting the number by hand gives you the reply
and nothing else.
"""
from __future__ import annotations

import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Fake WhatsApp message id handed back in place of Meta's. Shaped like the real
# thing so the burst-check and silence-nudge code paths behave normally.
_FAKE_MID_PREFIX = "wamid.SIMULATED"


@dataclass
class Turn:
    """One customer message and everything the pipeline did with it."""

    customer_message: str
    system_prompt: str = ""
    chat_messages: list[dict] = field(default_factory=list)
    tools_offered: list[str] = field(default_factory=list)
    reply_text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    sends: list[dict] = field(default_factory=list)
    suppressed: list[str] = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None

    @property
    def history_chars(self) -> int:
        return sum(len(m.get("content") or "") for m in self.chat_messages[1:])


class Capture:
    """Collects one turn's worth of pipeline internals."""

    def __init__(self) -> None:
        self.turn = Turn(customer_message="")

    def reset(self, customer_message: str) -> None:
        self.turn = Turn(customer_message=customer_message)


@contextlib.contextmanager
def sandboxed(
    capture: Capture,
    *,
    live_notifications: bool = False,
    master_override: str | None = None,
):
    """Patch every outward edge, plus the capture wrappers, for the duration.

    master_override swaps the platform prompt for this run without writing to
    platform_defaults -- the point is to compare candidate master prompts against
    one identical tenant (same description, same knowledge base, same catalog),
    so the only variable is the platform layer itself.
    """
    import app.services.ai_reply as ai_reply
    import app.services.meta_cloud as meta_cloud

    patches: list[tuple[Any, str, Any]] = []

    def patch(module: Any, name: str, replacement: Any) -> None:
        if not hasattr(module, name):
            return
        patches.append((module, name, getattr(module, name)))
        setattr(module, name, replacement)

    # ---- outward edge: Meta Cloud API -------------------------------------
    # messages.meta_message_id carries a unique index, so a fixed fake id collides
    # on the second turn of any conversation.
    def _mid(kind: str) -> str:
        return f"{_FAKE_MID_PREFIX}.{kind}.{uuid.uuid4().hex[:16]}"

    async def fake_send_text(*, to_number: str, text: str, **kw: Any) -> dict:
        capture.turn.sends.append({"kind": "text", "to": to_number, "text": text})
        return {"messages": [{"id": _mid("txt")}]}

    async def fake_send_buttons(*, to_number: str, body_text: str, buttons: Any, **kw: Any) -> dict:
        capture.turn.sends.append(
            {"kind": "buttons", "to": to_number, "text": body_text, "buttons": buttons}
        )
        return {"messages": [{"id": _mid("btn")}]}

    async def fake_upload_media(**kw: Any) -> str:
        return "SIMULATED_MEDIA_ID"

    async def fake_send_media(*, to_number: str, caption: str = "", **kw: Any) -> dict:
        capture.turn.sends.append({"kind": "media", "to": to_number, "caption": caption})
        return {"messages": [{"id": _mid("media")}]}

    async def noop_async(*a: Any, **kw: Any) -> None:
        return None

    patch(meta_cloud, "send_text_message", fake_send_text)
    patch(meta_cloud, "send_interactive_buttons", fake_send_buttons)
    patch(meta_cloud, "upload_media_to_meta", fake_upload_media)
    patch(meta_cloud, "send_media_message", fake_send_media)
    patch(meta_cloud, "send_typing_indicator", noop_async)
    patch(meta_cloud, "send_location_message", noop_async)
    patch(meta_cloud, "send_cta_url_message", noop_async)

    # ---- outward edge: the non-WhatsApp channels ---------------------------
    async def fake_channel_send(user_id: str, message: str, **kw: Any) -> str:
        capture.turn.sends.append({"kind": "channel", "to": user_id, "text": message})
        return _mid("chan")

    patch(ai_reply, "send_instagram", fake_channel_send)
    patch(ai_reply, "send_telegram", fake_channel_send)
    patch(ai_reply, "send_facebook", fake_channel_send)

    async def fake_voice(*a: Any, **kw: Any) -> None:
        # Returning None makes generate_reply fall through to the text path,
        # which is what we want to measure. A real voice send would also burn
        # TTS credits on every simulated turn.
        capture.turn.suppressed.append("voice_reply")
        return None

    patch(ai_reply, "send_whatsapp_voice_reply", fake_voice)

    # ---- outward edge: staff notifications ---------------------------------
    if not live_notifications:
        def noop_notify(*a: Any, **kw: Any) -> None:
            capture.turn.suppressed.append("staff_notification")
            return None

        try:
            import app.services.notify as notify

            patch(notify, "notify_pool", noop_notify)
            patch(notify, "notify_user", noop_notify)
            patch(notify, "notify_assigned_caller_of_reply", noop_notify)
        except ImportError:
            pass
        try:
            import app.services.whatsapp_notify as whatsapp_notify

            patch(whatsapp_notify, "queue_escalation_whatsapp_alert", noop_notify)
        except ImportError:
            pass

    # ---- outward edge: the silence nudge timer -----------------------------
    # Left un-armed: a simulated conversation that stops mid-run would otherwise
    # schedule a real follow-up message to the real phone number on the lead.
    try:
        import app.services.silence_nudge as silence_nudge

        def noop_arm(*a: Any, **kw: Any) -> None:
            capture.turn.suppressed.append("silence_nudge")
            return None

        patch(silence_nudge, "maybe_arm_after_ai_reply", noop_arm)
    except ImportError:
        pass

    # ---- variant: swap the platform prompt --------------------------------
    if master_override is not None:
        patch(ai_reply, "get_master_prompt", lambda: master_override)

    # ---- capture: the assembled prompt ------------------------------------
    real_build = ai_reply.build_reply_system_prompt

    def capturing_build(*a: Any, **kw: Any):
        result = real_build(*a, **kw)
        capture.turn.system_prompt = result[0]
        return result

    patch(ai_reply, "build_reply_system_prompt", capturing_build)

    # ---- capture: what actually went to the model -------------------------
    real_chat = ai_reply._llm_chat
    real_chat_tools = ai_reply._llm_chat_with_tools

    def _record_messages(messages: list[dict], tools: list[dict] | None = None) -> None:
        # The script-mismatch regeneration fires a second, historyless call with
        # its own translator system prompt. Keep the first (the real reply call)
        # so the captured prompt is the one we are measuring.
        if capture.turn.chat_messages:
            return
        capture.turn.chat_messages = [dict(m) for m in messages]
        for tool in tools or []:
            name = (tool.get("function") or {}).get("name")
            if name:
                capture.turn.tools_offered.append(name)

    async def capturing_chat(messages: list[dict], **kw: Any) -> str:
        _record_messages(messages)
        return await real_chat(messages, **kw)

    async def capturing_chat_tools(messages: list[dict], tools: list[dict], **kw: Any):
        _record_messages(messages, tools)
        return await real_chat_tools(messages, tools=tools, **kw)

    patch(ai_reply, "_llm_chat", capturing_chat)
    patch(ai_reply, "_llm_chat_with_tools", capturing_chat_tools)

    try:
        yield capture
    finally:
        for module, name, original in reversed(patches):
            setattr(module, name, original)


async def run_turn(
    lead_id: str,
    tenant_id: str,
    message: str,
    *,
    channel: str = "whatsapp",
    live_notifications: bool = False,
    master_override: str | None = None,
    db: Any = None,
) -> Turn:
    """Store the inbound message, run generate_reply, return the captured turn.

    The inbound row is written first because generate_reply assumes the webhook
    already stored it -- trigger D (repeated question) reads it back out of the
    thread, and the reply would see a thread one message short without it.
    """
    from app.db.supabase import get_supabase
    from app.services.ai_reply import generate_reply

    db = db or get_supabase()
    capture = Capture()
    capture.reset(message)

    db.table("messages").insert(
        {
            "lead_id": str(lead_id),
            "tenant_id": tenant_id,
            "direction": "inbound",
            "channel": channel,
            "content": message,
            "is_ai_generated": False,
        }
    ).execute()

    started = time.monotonic()
    with sandboxed(
        capture,
        live_notifications=live_notifications,
        master_override=master_override,
    ):
        try:
            await generate_reply(str(lead_id), message, channel=channel)
        except Exception as exc:  # the pipeline swallows most of its own errors
            capture.turn.error = f"{type(exc).__name__}: {exc}"
            logger.exception("generate_reply raised for lead %s", lead_id)
    capture.turn.latency_ms = int((time.monotonic() - started) * 1000)

    # The reply the customer would have received is whatever was sent. Fall back
    # to the stored outbound row when the send path was skipped entirely.
    if capture.turn.sends:
        capture.turn.reply_text = capture.turn.sends[0].get("text") or ""
    else:
        row = (
            db.table("messages")
            .select("content")
            .eq("lead_id", str(lead_id))
            .eq("direction", "outbound")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        capture.turn.reply_text = (row.data or [{}])[0].get("content") or ""

    return capture.turn
