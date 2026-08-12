"""Language-aware wording for the paid intake flow.

The collector's outgoing lines were hardcoded English f-strings, so a tenant on
reply_language_mode=tanglish got English the moment the intake flow took over --
live evidence 2026-08-12: four consecutive English collector messages sandwiched
between Tanglish AI replies to the same lead, on a tenant configured for
tanglish_escalate_tamil.

Division of labour, deliberately: the state machine in intake.py still decides
WHAT to say and when payment fires; this module only decides HOW it is worded.
Prices, collected values and payment URLs are rendered in Python and passed
through verbatim -- the model writes the sentence around them, never the number.
Same reasoning as package_list_block's docstring in intake.py.

Every call fails soft to the exact English literal the flow used before, so a
model outage degrades the language, never the payment flow.
"""
import logging
import re

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_MAX_COMPOSE_TOKENS = 200
_THREAD_WINDOW = 6

PURPOSES = frozenset({
    "ask_field", "reask_field", "skip_field",
    "payment_intro", "package_reask", "no_packages",
})

_TASKS = {
    "ask_field": (
        "Ask the customer for one detail: {field_label}. Nothing else."
    ),
    "reask_field": (
        "The customer's last message did not contain their {field_label}. Ask for it "
        "again, but differently from last time -- acknowledge what they said, and if a "
        "format would help (for example a date as 06/06/2000) show it. Do not repeat "
        "your previous sentence word for word."
    ),
    "skip_field": (
        "The customer has now twice been unable to give their {field_label}. Tell them "
        "warmly that it is fine and we can proceed without it, then in the same message "
        "ask for their {next_field_label}."
    ),
    "payment_intro": (
        "Tell the customer their payment link follows. One short sentence. Do NOT write "
        "any link, URL or amount yourself -- the system appends the real link after your "
        "sentence."
    ),
    "package_reask": (
        "The customer's reply did not clearly pick one of the options. Say you did not "
        "catch which one, in one short sentence. The system re-prints the option list "
        "with prices after your sentence, so do not list options or prices yourself."
    ),
    "no_packages": (
        "Tell the customer their details are noted and the team will follow up shortly "
        "with next steps. One short sentence."
    ),
}

_FALLBACKS = {
    "ask_field": "Great! Could you share your {field_label_lower}?",
    "reask_field": "Thanks! And your {field_label_lower}?",
    "skip_field": "No problem. And your {next_field_label_lower}?",
    "payment_intro": "Great, here's your payment link:",
    "package_reask": "Sorry, I didn't catch which one —",
    "no_packages": "Thanks! Our team will follow up shortly with the next steps.",
}

_WRAPPER_FALLBACKS = {
    "summary": ("Here's what I've got:", "Is that correct?"),
    "packages": ("Here are our options:", "Which one would you like?"),
}

_WRAPPER_TASKS = {
    "summary": (
        "You are showing the customer the details you collected, so they can confirm "
        "them before paying. Write a short intro line and a short closing question "
        "asking whether the details are correct."
    ),
    "packages": (
        "You are showing the customer the list of paid options. Write a short intro "
        "line and a short closing question asking which one they want. Do not mention "
        "any price -- the list with prices is inserted between your two lines."
    ),
}

_SYSTEM_PROMPT = (
    "You are the same WhatsApp assistant this customer has been chatting with. You are "
    "in the middle of signing them up for a paid consultation.\n"
    "Rules:\n"
    "- Do exactly the job described under TASK and nothing else.\n"
    "- One or two short sentences, the way a person texts on WhatsApp.\n"
    "- No greetings, no sign-offs, no emoji, no bullet lists.\n"
    "- Never state a price, a fee, or a URL. Never invent details about the customer.\n"
    "- If the customer asked something answerable from KNOWLEDGE below, answer it in one "
    "short sentence first, then do the TASK in the same message.\n"
    "- Reply with the message text only -- no quotes, no labels, no explanation."
)


async def _llm_chat(messages: list[dict], max_tokens: int, tenant_id: str) -> str:
    """Indirection so tests can patch this module rather than ai_reply, and so the
    intake voice always uses whatever model the tenant's AI brain uses."""
    from app.services.ai_reply import _llm_chat as _brain_chat
    return await _brain_chat(messages, max_tokens=max_tokens, tenant_id=tenant_id)


async def _llm_chat_json(system_prompt: str, user_prompt: str, tenant_id: str) -> dict:
    from app.services.gemini_client import gemini_chat_completion_json
    return await gemini_chat_completion_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=_MAX_COMPOSE_TOKENS,
        tenant_id=tenant_id,
        purpose="intake_copy_wrapped",
    )


def _resolve_reply_language_mode(tenant_id: str | None) -> str:
    from app.services.ai_reply import _resolve_reply_language_mode as _resolve
    return _resolve(tenant_id)


def resolve_language_mode(lead_id: str, tenant_id: str, db) -> str:
    """The language the intake flow should speak to THIS lead in. Forced modes pass
    through; tanglish_escalate_tamil resolves against leads.tamil_locked, which the
    webhook keeps current (ai_reply.record_tamil_lock_request)."""
    mode = _resolve_reply_language_mode(tenant_id)
    if mode != "tanglish_escalate_tamil":
        return mode
    try:
        row = (
            db.table("leads").select("tamil_locked").eq("id", str(lead_id)).maybe_single().execute()
        )
        locked = bool((row.data or {}).get("tamil_locked")) if row else False
    except Exception:
        logger.warning("tamil_locked lookup failed for lead %s -- defaulting to tanglish", lead_id)
        locked = False
    return "tamil" if locked else "tanglish"


def _language_block(mode: str, customer_message: str) -> str:
    from app.services.ai_reply import _language_rule_block
    return _language_rule_block(mode, customer_message)


async def gather_context(db, lead_id: str, tenant_id: str, message: str) -> tuple[list[dict], str]:
    """(recent thread, knowledge excerpt) for the composer. Both are best-effort: an
    empty result costs naturalness, never the message."""
    thread: list[dict] = []
    try:
        rows = (
            db.table("messages")
            .select("direction,content")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(_THREAD_WINDOW)
            .execute()
        )
        thread = list(reversed(rows.data or []))
    except Exception:
        logger.warning("Intake copy thread fetch failed for lead %s", lead_id)

    knowledge = ""
    try:
        from app.services.knowledge_service import get_knowledge_context
        knowledge = await get_knowledge_context(tenant_id, query=message) or ""
    except Exception:
        logger.warning("Intake copy knowledge fetch failed for tenant %s", tenant_id)
    return thread, knowledge


def _render_thread(thread: list[dict] | None) -> str:
    if not thread:
        return ""
    lines = []
    for row in thread:
        who = "You" if row.get("direction") == "outbound" else "Customer"
        content = (row.get("content") or "").strip()
        if content:
            lines.append(f"{who}: {content}")
    return "\n".join(lines)


def _user_prompt(
    task: str, language_mode: str, customer_message: str,
    thread: list[dict] | None, knowledge: str,
) -> str:
    parts = [f"TASK:\n{task}", _language_block(language_mode, customer_message).strip()]
    rendered = _render_thread(thread)
    if rendered:
        parts.append(f"RECENT CONVERSATION:\n{rendered}")
    if knowledge:
        parts.append(f"KNOWLEDGE:\n{knowledge}")
    parts.append(f"CUSTOMER'S LATEST MESSAGE:\n{customer_message}")
    return "\n\n".join(parts)


def _fallback(purpose: str, field_label: str | None, next_field_label: str | None) -> str:
    if purpose not in _FALLBACKS:
        raise ValueError(f"unknown intake copy purpose: {purpose}")
    return _FALLBACKS[purpose].format(
        field_label_lower=(field_label or "details").lower(),
        next_field_label_lower=(next_field_label or "details").lower(),
    )


async def compose_line(
    purpose: str,
    *,
    tenant_id: str,
    language_mode: str,
    customer_message: str,
    field_label: str | None = None,
    next_field_label: str | None = None,
    thread: list[dict] | None = None,
    knowledge: str = "",
) -> str:
    """One outgoing collector line, worded in the tenant's configured language."""
    if purpose not in PURPOSES:
        raise ValueError(f"unknown intake copy purpose: {purpose}")
    task = _TASKS[purpose].format(
        field_label=field_label or "the detail",
        next_field_label=next_field_label or "the next detail",
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _user_prompt(task, language_mode, customer_message, thread, knowledge),
        },
    ]
    try:
        text = (await _llm_chat(messages, max_tokens=_MAX_COMPOSE_TOKENS, tenant_id=tenant_id) or "").strip()
    except Exception as e:
        logger.warning("Intake copy compose failed (%s), using fallback: %s", purpose, e)
        return _fallback(purpose, field_label, next_field_label)
    text = _URL_RE.sub("", text).strip()
    if not text:
        logger.warning("Intake copy compose returned empty (%s), using fallback", purpose)
        return _fallback(purpose, field_label, next_field_label)
    return text


async def compose_wrapped(
    purpose: str,
    *,
    tenant_id: str,
    language_mode: str,
    customer_message: str,
    block: str,
    thread: list[dict] | None = None,
) -> str:
    """A code-rendered block (collected values, or the priced option list) wrapped in an
    intro and a closing question written in the tenant's language. The block is inserted
    verbatim -- the model never gets a chance to rewrite a value or a price."""
    if purpose not in _WRAPPER_FALLBACKS:
        raise ValueError(f"unknown intake copy wrapper purpose: {purpose}")
    intro_fb, question_fb = _WRAPPER_FALLBACKS[purpose]
    user_prompt = _user_prompt(
        _WRAPPER_TASKS[purpose] + '\n\nReturn JSON only: {"intro": "...", "question": "..."}',
        language_mode, customer_message, thread, "",
    )
    try:
        data = await _llm_chat_json(_SYSTEM_PROMPT, user_prompt, tenant_id)
        intro = _URL_RE.sub("", str(data.get("intro") or "")).strip()
        question = _URL_RE.sub("", str(data.get("question") or "")).strip()
    except Exception as e:
        logger.warning("Intake copy wrap failed (%s), using fallback: %s", purpose, e)
        intro, question = "", ""
    if not intro or not question:
        intro, question = intro_fb, question_fb
    return f"{intro}\n\n{block}\n\n{question}"
