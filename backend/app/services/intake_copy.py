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
    "ask_field", "reask_field", "skip_field", "greeting_reask",
    "payment_intro", "payment_delay", "payment_receipt", "package_reask", "no_packages",
    "reply_ready",
})

_TASKS = {
    "ask_field": (
        "Ask the customer for exactly one detail: {field_label}. Ask for nothing else."
    ),
    "reask_field": (
        "The customer's last message did not contain their {field_label}. Ask for that "
        "same one detail again, worded differently from last time -- acknowledge what "
        "they said, and if an example of {field_label} would help them answer, give one. "
        "Ask for {field_label} and nothing else: do not ask for any other detail, and "
        "never ask for something listed under ALREADY COLLECTED."
    ),
    "greeting_reask": (
        "The customer just greeted you in the middle of the signup. Greet them back in "
        "a few words, then ask again for their {field_label}. Do not restart the "
        "conversation and do not re-introduce the service -- you are already mid-signup."
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
    "payment_delay": (
        "The payment link could not be generated right now. Tell the customer their "
        "details are received and the team will send the payment link shortly. Do not "
        "apologise at length, do not explain the failure, and do not write any link."
    ),
    "payment_receipt": (
        "The customer's payment just went through. Thank them and confirm their "
        "{field_label} is booked -- our expert is working on it and we will message "
        "them here as soon as their answer is ready. Do not promise a specific time "
        "or name a person. Do not say where they will read the answer and do not "
        "write any link: that comes later, in its own message. Do not include the "
        "customer's own name in your sentence -- the system adds it separately."
    ),
    "reply_ready": (
        "The expert has answered the {field_label} this customer paid for. The answer "
        "is waiting for them in our app, not here. In one or two short lines, tell them "
        "their answer is ready and that they can read it in full by opening the app and "
        "signing in with this same phone number. Do NOT write a link or a URL of any "
        "kind -- one is added automatically after your line. Do not attempt to summarise "
        "or hint at what the expert said: you have not seen it."
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
    "greeting_reask": "Hi! Could you share your {field_label_lower}?",
    "skip_field": "No problem. And your {next_field_label_lower}?",
    "payment_intro": "Great, here's your payment link:",
    "payment_delay": "We've received your details — our team will send the payment link shortly.",
    "payment_receipt": "Your {field_label_lower} is confirmed — our expert is working on it and we'll message you as soon as your answer is ready.",
    "reply_ready": "Your answer is ready. Open our app and sign in with this number to read it in full:",
    "package_reask": "Sorry, I didn't catch which one —",
    "no_packages": "Thanks! Our team will follow up shortly with the next steps.",
}

_WRAPPER_FALLBACKS = {
    "summary": ("Here's what I've got:", "Is that correct?"),
    "packages": ("Here are our options:", "Which one would you like?"),
    "addons": ("Want to add any of these?", "Reply with the ones you'd like, or say no thanks."),
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
    "addons": (
        "You are showing the customer optional add-ons available on top of the package "
        "they just picked. The confirmed package name (and its description, if any) is "
        "inserted between your two lines, above the addon list -- do not name or "
        "describe the package yourself, and do not assume the package name matches the "
        "customer's last message, which may only name a broader category. Write a short "
        "intro line and a short closing question asking which add-ons they want, or "
        "none. Do not mention any price -- the list with prices is inserted between "
        "your two lines."
    ),
}

# Live evidence 2026-08-13: a lead asked "eppo astrologer enne contact pannuvange"
# (when will the astrologer contact me) mid-collection. The composer ignored "eppo"
# entirely and just re-asked the pending field -- the old system prompt only allowed
# answering a question if it came from retrieved KNOWLEDGE, and "when does the expert
# reply" isn't a business fact, it's flow state the composer was never told. FLOW_FACTS
# is always present (unlike KNOWLEDGE, which depends on retrieval) so this exact
# question class is answerable regardless of which purpose is composing.
_FLOW_FACTS = (
    "FLOW FACTS (use only these if asked; never invent beyond them):\n"
    "- After the customer confirms their details and pays, a human expert reviews "
    "their case and replies here on this same WhatsApp chat. No fixed time is "
    "promised -- never state a number of minutes/hours or name a person.\n"
    "- Before payment, no expert has been assigned yet -- never claim one is already "
    "reviewing anything."
)

_SYSTEM_PROMPT = (
    "You are the same WhatsApp assistant this customer has been chatting with. You are "
    "in the middle of signing them up for a paid consultation.\n"
    "Rules:\n"
    "- If the customer's message is a real question -- not just a missing answer to "
    "the pending field -- answer it first, in one short sentence, using FLOW FACTS or "
    "KNOWLEDGE below if relevant. Then do the TASK in the same message. If the message "
    "is not a question, just do the TASK.\n"
    "- One or two short sentences total, the way a person texts on WhatsApp.\n"
    "- No greetings, no sign-offs, no emoji, no bullet lists.\n"
    "- Never state a price, a fee, or a URL. Never invent details about the customer "
    "or the expert.\n"
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


def _brain_prompt(db, lead_id: str, tenant_id: str, lead_data: dict, message: str) -> str:
    """The main brain's own system prompt -- master prompt, business description, app
    link rule, campaign and lead context. Passed to the collector so it speaks as the
    same assistant rather than a thinner stand-in.

    include_intake_context=False: this IS the intake flow, so being told an intake is
    in progress is noise, and the 'do not mention the app' rule there would fight the
    collector's own task wording. catalog_context is left empty deliberately -- product
    recommendations have no business interrupting a payment flow.
    """
    from app.services.ai_reply import build_reply_system_prompt
    prompt, _mode, _intake_active = build_reply_system_prompt(
        db, lead_id, tenant_id, lead_data, message,
        include_intake_context=False,
    )
    return prompt


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


_LABEL_TRANSLATE_SYSTEM_PROMPT = """Translate each of these field labels into natural,
native Tamil script. These are short field names on a form (like "Full Name" or "Date
of birth"), not sentences -- keep each translation short, the way a Tamil form would
label that field.

Respond with JSON only: {"<field_key>": "<Tamil label>", ...} -- one entry per key
given, same keys, nothing added or removed. No other text."""


async def localized_fields(fields: list[dict], language_mode: str, tenant_id: str) -> list[dict]:
    """Field labels translated into native Tamil script, only when language_mode is
    the locked "tamil" mode -- every other mode (mirror, tanglish, english, or
    tanglish_escalate_tamil before the lock fires) returns fields unchanged, no LLM
    call at all. Live decision 2026-08-14: labels should only ever move to native
    Tamil once the lead is genuinely locked into it; a Tanglish conversation keeps
    its English labels exactly as before this existed.

    Only 'key' and 'type' identify a field to the rest of the system -- 'label' is
    display text with zero downstream meaning, so translating it carries none of the
    risk that translating a collected VALUE would. This never sees a collected value;
    only the label text is sent to the model. All-or-nothing: any missing key in the
    response discards the whole translation and keeps the original English labels,
    the same as a network failure would.
    """
    if language_mode != "tamil" or not fields:
        return fields
    label_list = "\n".join(f"- {f['key']}: {f['label']}" for f in fields)
    try:
        data = await _llm_chat_json(
            _LABEL_TRANSLATE_SYSTEM_PROMPT,
            f"Field labels:\n{label_list}",
            tenant_id,
        )
    except Exception as e:
        logger.warning("Field label translation failed, using English labels: %s", e)
        return fields
    if not all(f["key"] in data and str(data[f["key"]]).strip() for f in fields):
        logger.warning("Field label translation incomplete, using English labels")
        return fields
    return [{**f, "label": str(data[f["key"]]).strip()} for f in fields]


async def compose_payment_receipt(
    lead_id: str, tenant_id: str, customer_name: str | None, service_noun: str
) -> str:
    """The payment-confirmation receipt, in the lead's actual language. Fired from
    the Razorpay webhook route -- a code path outside the WhatsApp message flow
    entirely, so it never went through resolve_language_mode or the composer at
    all. Live evidence 2026-08-14: a lead locked into native Tamil for the whole
    collection got a plain English 'Payment received, thank you...' the moment
    payment cleared.

    customer_name is prepended in code, never sent to the model, same protection
    as every other literal value in this flow. It is optional: when the tenant's
    schema holds no identifiable name field the greeting is dropped entirely
    rather than falling back to a placeholder -- see resolve_customer_name.
    """
    from app.db.supabase import get_supabase
    db = get_supabase()
    language_mode = resolve_language_mode(lead_id, tenant_id, db)
    body = await compose_line(
        "payment_receipt",
        tenant_id=tenant_id,
        language_mode=language_mode,
        customer_message="",
        field_label=service_noun,
    )
    return f"{customer_name}, {body}" if customer_name else body


def collector_identity(db, lead_id: str, tenant_id: str, message: str) -> str:
    """The main brain's system prompt for this lead, for the collector to speak with.
    Best-effort: on any failure the collector falls back to its own minimal prompt,
    which is exactly how it behaved before -- a thinner voice, never a broken one."""
    try:
        row = (
            db.table("leads")
            .select("name,segment,needs_human_attention,tamil_locked")
            .eq("id", str(lead_id))
            .maybe_single()
            .execute()
        )
        lead_data = (row.data if row else None) or {}
        return _brain_prompt(db, lead_id, tenant_id, lead_data, message)
    except Exception:
        logger.warning("Collector identity build failed for lead %s -- using base prompt", lead_id)
        return ""


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
    collected: dict | None = None,
) -> str:
    parts = [f"TASK:\n{task}", _language_block(language_mode, customer_message).strip(), _FLOW_FACTS]
    if collected:
        # Without this the model has no way to know a detail is already on file, and
        # will happily re-ask for it (live 2026-08-13: asked for a date of birth it
        # had already been given, while re-asking for time of birth).
        have = "\n".join(f"- {k}: {v}" for k, v in collected.items() if v)
        if have:
            parts.append(f"ALREADY COLLECTED (never ask for these again):\n{have}")
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
    brain_prompt: str = "",
    collected: dict | None = None,
) -> str:
    """One outgoing collector line, worded in the tenant's configured language.

    brain_prompt is the main brain's system prompt (see _brain_prompt). When present
    the collector speaks with the business's real identity and rules; the collector's
    own rules are appended after it so they win on conflict.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"unknown intake copy purpose: {purpose}")
    task = _TASKS[purpose].format(
        field_label=field_label or "the detail",
        next_field_label=next_field_label or "the next detail",
    )
    system_content = f"{brain_prompt}\n\n{_SYSTEM_PROMPT}" if brain_prompt else _SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": _user_prompt(
                task, language_mode, customer_message, thread, knowledge, collected
            ),
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
