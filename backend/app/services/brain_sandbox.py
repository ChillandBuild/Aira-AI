"""Test Anril: an answers-only sandbox for the client hub and the operator console.

It builds the same system prompt a real reply gets (master prompt, business description,
knowledge excerpts, language rule) and asks the tenant's own reply model to answer the
typed conversation, which lives only in memory. Nothing is stored and nothing can be
sent, by construction:

- It never calls generate_reply or deal_turn.converse_once. It calls ai_reply._llm_chat,
  which passes no tools and writes nothing itself.
- Like a real reply, the prompt also carries the catalog block (ready items and the client's
  AI rules), built by ai_reply._build_catalog_context, which only reads.
- The prompt is built for a synthetic lead whose id matches no row, with persist=False,
  so no lead, message, session, deal, order, payment or handover row is created or read.
- The only side effect is the provider client's best-effort token counter
  (token_meter.record_tokens), filed under purpose="sandbox" so the usage is labelled.

Each call costs model tokens (plus one embedding call for retrieval), so it is limited
per tenant and has a kill switch (platform_defaults row "brain_sandbox_enabled").
"""
import logging
import threading
import time
from collections import deque

from app.db.supabase import get_supabase
from app.services import ai_reply
from app.services import knowledge_service

logger = logging.getLogger(__name__)

# Rate limit: per tenant and per source (a client and an operator do not share a budget).
# In-process sliding window: the codebase's only other limiter (slowapi in main.py) is
# per IP, which cannot express "per business". State resets on restart, which is fine
# for a cost guard on a single web instance.
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 10 * 60

MAX_TURNS = 20
MAX_MESSAGE_CHARS = 1000
MAX_REPLY_TOKENS = 400
SANDBOX_TEMPERATURE = 0.4
SANDBOX_PURPOSE = "sandbox"

# A UUID no lead row has. Every lead-keyed read in the prompt build (summary, calls,
# orders, campaign) matches nothing and returns empty instead of erroring.
NO_LEAD_ID = "00000000-0000-0000-0000-000000000000"
_SYNTHETIC_LEAD = {
    "name": "Test customer",
    "segment": None,
    "tamil_locked": False,
    "needs_human_attention": False,
}

# Kill switch: a row in platform_defaults (the table the master prompt already lives in).
# Absent row = on. Set value to "false" / "off" / "0" to switch Test Anril off for everyone
# without a deploy. Cached briefly so a burst of calls does not re-read it each time.
KILL_SWITCH_KEY = "brain_sandbox_enabled"
_OFF_VALUES = frozenset({"false", "off", "0", "no"})
_KILL_SWITCH_TTL_SECONDS = 30.0
_kill_switch_cache: dict[str, tuple[float, bool]] = {}

NOTE = "Answers only. Nothing was saved or sent, and orders, quotes and payment links are not tested here."


class SandboxError(Exception):
    """Base for failures the route maps to an HTTP status."""

    status_code = 500
    message = "Test Anril failed"


class SandboxSwitchedOff(SandboxError):
    status_code = 503
    message = "Test Anril is switched off"


class SandboxNotConfigured(SandboxError):
    status_code = 409
    message = "Anril's reply model isn't set up for this business"


class SandboxRateLimited(SandboxError):
    status_code = 429
    message = "Too many test messages. Please wait a few minutes and try again"


class SandboxProviderFailed(SandboxError):
    status_code = 502
    message = "Anril couldn't answer just now. Please try again"


class _SlidingWindowLimiter:
    """Allows `limit` hits per `window` seconds per key. Thread-safe."""

    def __init__(self, limit: int, window_seconds: float):
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = _SlidingWindowLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


def reset_state() -> None:
    """Clears the limiter and the kill-switch cache (tests)."""
    _limiter.reset()
    _kill_switch_cache.clear()


def is_enabled() -> bool:
    """True unless the platform_defaults kill-switch row says off. A failed read keeps
    the sandbox on: the switch exists to stop cost, and the rate limit still applies."""
    cached = _kill_switch_cache.get(KILL_SWITCH_KEY)
    now = time.monotonic()
    if cached and now - cached[0] < _KILL_SWITCH_TTL_SECONDS:
        return cached[1]
    try:
        rows = (
            get_supabase().table("platform_defaults").select("value")
            .eq("key", KILL_SWITCH_KEY).limit(1).execute().data or []
        )
    except Exception:
        logger.exception("Test Anril kill-switch read failed; leaving it on")
        return True
    value = str((rows[0].get("value") if rows else "") or "").strip().lower()
    enabled = value not in _OFF_VALUES
    _kill_switch_cache[KILL_SWITCH_KEY] = (now, enabled)
    return enabled


def _resolve_model(tenant_id: str) -> str:
    """The tenant's reply model, resolved exactly as a real reply does: per-tenant model
    setting and per-tenant provider key, no platform fallback."""
    try:
        _provider, native_model = ai_reply._resolve_provider(tenant_id)
    except RuntimeError:
        logger.info("Test Anril: reply model or key not configured for tenant %s", tenant_id)
        raise SandboxNotConfigured() from None
    return native_model


async def _knowledge_for(tenant_id: str, query: str) -> str:
    """Same retrieval a real reply uses. A failure means no excerpts, like generate_reply."""
    try:
        return await knowledge_service.get_knowledge_context(tenant_id, query=query)
    except Exception:
        logger.warning("Test Anril: knowledge fetch failed for tenant %s", tenant_id, exc_info=True)
        return ""


async def _catalog_for(tenant_id: str, query: str) -> str:
    """The CATALOG block a real reply gets (ready items, prices, the client's AI rules),
    built by the same function generate_reply uses. It only reads (selects plus the
    match_catalog_items search); the tool definitions it also returns are dropped, because
    the sandbox passes no tools. A failure means no catalog block, like generate_reply."""
    try:
        catalog_context, _tools, _items, _max_images = await ai_reply._build_catalog_context(
            get_supabase(), tenant_id, query
        )
    except Exception:
        logger.warning("Test Anril: catalog context failed for tenant %s", tenant_id, exc_info=True)
        return ""
    return catalog_context


def _build_messages(tenant_id: str, turns: list[dict], context_text: str, catalog_context: str) -> list[dict]:
    latest = turns[-1]["content"]
    system_prompt, _mode, _intake = ai_reply.build_reply_system_prompt(
        get_supabase(),
        NO_LEAD_ID,
        tenant_id,
        dict(_SYNTHETIC_LEAD),
        latest,
        "whatsapp",
        context_text=context_text,
        catalog_context=catalog_context,
        include_intake_context=False,
        persist=False,
    )
    return [{"role": "system", "content": system_prompt}, *turns]


async def run_sandbox(tenant_id: str, messages: list[dict], *, source: str = "client") -> dict:
    """Answer the last user message of `messages` (already validated by the route: 1 to 20
    turns, user/assistant roles, last is user). Returns
    {reply, knowledge_used, model, note}. Raises a SandboxError subclass."""
    if not is_enabled():
        raise SandboxSwitchedOff()
    model = _resolve_model(tenant_id)
    if not _limiter.allow(f"{source}:{tenant_id}"):
        raise SandboxRateLimited()

    turns = [{"role": m["role"], "content": m["content"]} for m in messages]
    context_text = await _knowledge_for(tenant_id, turns[-1]["content"])
    catalog_context = await _catalog_for(tenant_id, turns[-1]["content"])
    chat_messages = _build_messages(tenant_id, turns, context_text, catalog_context)
    try:
        reply = await ai_reply._llm_chat(
            chat_messages,
            max_tokens=MAX_REPLY_TOKENS,
            tenant_id=tenant_id,
            purpose=SANDBOX_PURPOSE,
            temperature=SANDBOX_TEMPERATURE,
        )
    except Exception:
        logger.exception("Test Anril model call failed for tenant %s", tenant_id)
        raise SandboxProviderFailed() from None

    reply = (reply or "").strip()
    if not reply:
        raise SandboxProviderFailed()
    return {"reply": reply, "knowledge_used": bool(context_text), "model": model, "note": NOTE}
