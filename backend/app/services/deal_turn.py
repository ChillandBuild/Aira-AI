"""One reply turn of the AI-native deal engine: build the context, ask the model (with the
deal tools alongside the catalog and quick-reply tools), run the tools through
deal_actions, and make the message safe to send.

generate_reply (services/ai_reply.py) calls this for every reply that can use tools: package
selling (WhatsApp, when the tenant has packages), product recommendations and quotes, and
quick-reply blocks all run through the same guarded loop.
The pure prompt and tool schemas are in services/deal_engine.py, the guarded executors in
services/deal_actions.py. Design: docs/plans/ai-native-conversation.md.
"""
import dataclasses
import difflib
import json
import logging
import re

from app.services import deal_actions, deal_engine, intake

logger = logging.getLogger(__name__)

REPLY_MAX_TOKENS = 600
MAX_ROUNDS = 2
REPEAT_MIN_CHARS = 25
REPEAT_SIMILARITY = 0.9
HANDOVER_LINE_PROBE_CHARS = 40
REPEATED_HANDOVER_REASON = "Aira had no answer for the customer twice in a row"
PAYMENT_COMPLAINT_REASON = "Lead says they paid, asks about payment status, or wants a refund"
HANDOVER_OPENED_NOTE = (
    "\n\nPAYMENT CONCERN — a person on this team has just been alerted to check this customer's "
    "payment or refund request, right here in this chat. Do not approve or refuse a refund yourself. "
    "Your reply must: (1) first acknowledge exactly what they told you, specifically (for example "
    "that they paid and have not heard back), with real empathy and no emoji; (2) say plainly that "
    "the team is checking it and will reply here. Do NOT send them anywhere else (not the app, not a "
    "support desk, not the HANDOVER RULE line): a person here is already on it. Never say the payment "
    "is confirmed or missing, never promise a time, and do not send the exact same sentence you sent "
    "before. If you already told them the team is checking, respond to their new point specifically "
    "(their frustration, their question, the amount they mention)."
)


# "[Payment Link]", "<link>", "[URL]": the model sometimes writes a stand-in for a link it
# was told the system would attach. Code attaches the real one; the stand-in must not reach
# the customer.
_PLACEHOLDER_RE = re.compile(r"\[\s*(?:payment\s+)?(?:link|url)[^\]]*\]|<\s*(?:payment\s+)?(?:link|url)[^>]*>", re.IGNORECASE)


# Payment links are only ever attached by code. A payment URL in the model's own words is
# copied from history (possibly an old link for a different amount) or invented.
_PAYMENT_URL_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:rzp\.io|razorpay\.(?:com|me))\S*", re.IGNORECASE)


def strip_payment_urls(text: str) -> tuple[str, bool]:
    """(text without payment URLs, whether any was removed)."""
    cleaned, count = _PAYMENT_URL_RE.subn("", text or "")
    if not count:
        return text, False
    return strip_placeholders(cleaned), True


# Grief, illness, anger: a smiley under a condolence reads as a bot. The model does not
# reliably follow the no-emoji rule, so code removes them on these messages.
_SOMBRE_RE = re.compile(
    r"passed away|\bdied\b|\bdeath\b|funeral|\bhospital|\baccident|cancer|\bserious\b|"
    r"\bworst\b|\bcheat|\bfraud|\bscam|\bgarbage\b|\bangry\b|\bdisgust|"
    r"இறந்|மரண|காலமான|இறப்பு",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def sombre(message: str) -> bool:
    return bool(_SOMBRE_RE.search(message or ""))


def without_emoji(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _EMOJI_RE.sub("", text)).replace(" .", ".").strip()


def strip_placeholders(text: str) -> str:
    cleaned = _PLACEHOLDER_RE.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _known_prices(db, tenant_id: str, lead_id: str) -> frozenset:
    """Every product price (1..10 units) and recent order total for the price guard. The
    catalog block only lists this turn's matching items, so the guard reads all of them."""
    prices: set[float] = set()
    try:
        rows = (
            db.table("catalog_items").select("price_paise")
            .eq("tenant_id", tenant_id).eq("status", "ready").execute()
        ).data or []
        prices |= deal_engine.price_multiples(r.get("price_paise") for r in rows)
    except Exception:
        logger.warning("Catalog price lookup failed for tenant %s", tenant_id)
    prices |= {(d.get("total_paise") or 0) / 100 for d in deal_actions.lead_orders(db, tenant_id, lead_id)}
    return frozenset(p for p in prices if p)


def build_context(
    db, tenant_id: str, lead_id: str, phone: str | None, *,
    channel: str = "whatsapp", catalog: dict | None = None, max_images: int = 0,
) -> deal_actions.DealContext:
    """Always returns a context: every reply runs through the same guards. Package selling
    (DEAL STATE + package tools) is on only for WhatsApp tenants with active packages."""
    try:
        config = intake.get_intake_config(tenant_id, db=db)
    except Exception:
        logger.exception("Intake config read failed for tenant %s -- replying without package tools", tenant_id)
        config = {}
    return deal_actions.DealContext(
        config=config, db=db, lead_id=lead_id, tenant_id=tenant_id, phone=phone or "",
        catalog=dict(catalog or {}), max_images=max_images,
        offerings_enabled=channel == "whatsapp" and deal_engine.is_enabled(config),
        known_prices=_known_prices(db, tenant_id, lead_id),
    )


def pre_turn_guards(ctx: deal_actions.DealContext, message: str) -> bool:
    """Code-level backstop that does not wait for the model: a lead who says they already
    paid, or asks about payment status, gets a person on the case immediately. Returns
    True when a handover was requested."""
    if not deal_engine.is_payment_complaint(message):
        return False
    deal_actions.open_handover(ctx, PAYMENT_COMPLAINT_REASON)
    return True


CAPTURE_LOOKBACK = 6


async def capture_details(
    ctx: deal_actions.DealContext, message: str, *, extractor=None, earlier: list[str] | None = None,
) -> dict:
    """Save any required details the customer's message contains, BEFORE the model runs.

    The model is asked to call save_details, but in live tests it sometimes says "noted" and
    never calls it, then asks for the same detail again. This is the code-level backstop: the
    same extractor the old intake flow used, saved through the same guarded save_details
    executor, so the DEAL STATE the model reads already holds what the customer just said.
    Runs only while details are still missing. Never raises. Returns what it newly saved."""
    if not ctx.offerings_enabled:
        return {}
    try:
        session = deal_actions._session(ctx)
        if not session or not session.get("package_key") or session["status"] == deal_engine.PAID_STATUS:
            return {}
        fields = ctx.config.get("fields") or []
        collected = session.get("collected_data") or {}
        if not deal_engine.missing_details(fields, collected, session.get("skipped_fields") or []):
            return {}
        extract = extractor or intake.extract_fields
        # Details are often given before a package is chosen (no session yet to save them to),
        # so read the customer's recent messages too, not only this one.
        recent = [m for m in (earlier or [])[-CAPTURE_LOOKBACK:] if m] + [message]
        merged = await extract("\n".join(recent), fields, collected, ctx.tenant_id)
        new = {k: v for k, v in merged.items() if v and v != collected.get(k)}
        if not new:
            return {}
        call = {"function": {"name": deal_engine.TOOL_SAVE_DETAILS, "arguments": json.dumps({"fields": new})}}
        await deal_actions.apply_tool_calls([call], ctx)
        return new
    except Exception:
        logger.exception("Detail capture failed for lead %s -- the model will still see the raw message", ctx.lead_id)
        return {}


def menu_log_text(body: str, menu: dict) -> str:
    return body + "\n\n" + "  ".join(f"[{title}]" for title in menu["options"])


def _last_assistant_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return message.get("content") or ""
    return ""


def _state_line(ctx: deal_actions.DealContext) -> str:
    if not ctx.offerings_enabled:
        return ""
    try:
        return deal_engine.deal_state_block(ctx.config, deal_actions._session(ctx))
    except Exception:
        logger.exception("Deal state refresh failed for lead %s", ctx.lead_id)
        return ""


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


def _price_refusals(text: str, ctx: deal_actions.DealContext, customer_message: str) -> tuple[str, ...]:
    wrong = deal_engine.unknown_prices(text, ctx.config, customer_message, ctx.known_prices)
    if not wrong:
        return ()
    shown = ", ".join(f"₹{p:g}" for p in wrong)
    return (
        f"Your draft quotes {shown}, which is not a current price (OFFERINGS, CATALOG or ORDERS). "
        "Quote only those prices, or leave the price out.",
    )


REPEAT_LOOKBACK = 3


def _repeat_refusals(text: str, earlier: list[str]) -> tuple[str, ...]:
    """A long reply that is (nearly) word for word one of the last few sent reads like a bot."""
    a = text.strip().lower()
    if len(a) < REPEAT_MIN_CHARS:
        return ()
    recent = [t.strip().lower() for t in earlier[-REPEAT_LOOKBACK:] if t.strip()]
    if not any(difflib.SequenceMatcher(None, a, b).ratio() >= REPEAT_SIMILARITY for b in recent):
        return ()
    return (
        "You already said this in your previous message, nearly word for word. Say something "
        "different: respond to what they just wrote, specifically.",
    )


def _bare_handover_refusals(draft: str, handover_line: str, handover_opened: bool) -> tuple[str, ...]:
    """After a payment concern, a reply that is only the client's stock help line ignores what
    the customer said. It must acknowledge them first."""
    if not handover_opened or not _said_handover_line(draft, handover_line):
        return ()
    return (
        "Do not send them to the stock help line: a person on this team is already checking their "
        "payment here. Acknowledge what they told you and say the team is checking it and will reply "
        "in this chat.",
    )


def _payment_url_refusals(removed_url: bool, attached: "_Attached") -> tuple[str, ...]:
    """The model wrote a payment link itself. If code attached a real one this turn, dropping the
    model's copy is enough; otherwise its words promise a link that will not be there."""
    if not removed_url or attached.link or attached.quote:
        return ()
    return (
        "Do not write any payment link yourself; links are attached by the system only. If they "
        "want to pay, call create_payment_link (packages) or send_quote (products); otherwise do not "
        "mention a link.",
    )


def _earlier_assistant_texts(messages: list[dict]) -> list[str]:
    return [m.get("content") or "" for m in messages if m.get("role") == "assistant"]


def _repeated_line_refusals(draft: str, handover_line: str, line_said_before: bool) -> tuple[str, ...]:
    if not line_said_before or not _said_handover_line(draft, handover_line):
        return ()
    return (
        "You already gave the customer the help line earlier in this chat; do not repeat it. A "
        "person on the team has now been asked to help. Respond to what they just wrote, in your "
        "own words, and tell them the team will get back to them (no time promised).",
    )


def _said_handover_line(text: str, handover_line: str) -> bool:
    probe = handover_line.strip().lower()[:HANDOVER_LINE_PROBE_CHARS]
    return bool(probe) and probe in text.lower()


class _Attached:
    """What the system will send along with the words, accumulated across rounds."""

    def __init__(self):
        self.menu: dict | None = None
        self.link: str | None = None
        self.quote: str | None = None
        self.images: list[str] = []
        self.handover = False

    def add(self, outcome: deal_actions.Outcome) -> None:
        self.menu = outcome.menu or self.menu
        self.link = outcome.payment_link or self.link
        self.quote = outcome.quote_text or self.quote
        self.images += [i for i in outcome.image_item_ids if i not in self.images]
        self.handover = self.handover or outcome.handover

    def any(self) -> bool:
        return bool(self.menu or self.link or self.quote or self.images)

    def notes(self, ctx: deal_actions.DealContext) -> list[str]:
        lines = []
        if self.menu:
            lines.append("The tappable options are already attached; do not call show_options again.")
        if self.link:
            lines.append("The payment link is already created and will be attached; do not write any link.")
        if self.quote:
            lines.append("The itemised quote with its payment link will be attached after your words; do not repeat the prices or write any link.")
        if self.images:
            names = ", ".join((ctx.catalog.get(i) or {}).get("name", i) for i in self.images)
            lines.append(f"Photos of {names} will be sent after your message.")
        return lines

    def outcome(self, refusals: tuple[str, ...]) -> deal_actions.Outcome:
        return deal_actions.Outcome(
            self.menu, self.link, refusals, self.handover, self.quote, tuple(self.images),
        )


def _round_note(ctx: deal_actions.DealContext, refusals: tuple[str, ...], attached: _Attached, *, text_only: bool = False) -> str:
    lines = ["[System note, not from the customer]"]
    if refusals:
        lines.append("The system refused part of your last reply:")
        lines.extend(f"- {r}" for r in refusals)
    else:
        lines.append("Your actions were applied.")
    lines.append(_state_line(ctx))
    lines.extend(attached.notes(ctx))
    ask = (
        "Now write the message to send to the customer: same language and tone, claim nothing "
        "that was refused, and ask for any detail still needed."
    )
    if text_only:
        lines.append(f"{ask} Do not call any tool and do not write any link. Output only the message.")
    elif ctx.offerings_enabled:
        lines.append(f"{ask} If nothing is still needed and no payment link exists yet, call create_payment_link. Output only the message.")
    else:
        lines.append(f"{ask} Output only the message.")
    return "\n".join(line for line in lines if line)


async def _final_text(messages, ctx, refusals, attached, tenant_id, llm) -> str:
    """Tool rounds can end with no words at all (this provider writes no text on a turn where it
    calls a tool). One last call with no tools offered, only to say what just happened."""
    final = [
        *messages,
        {"role": "assistant", "content": "(no text)"},
        {"role": "user", "content": _round_note(ctx, refusals, attached, text_only=True)},
    ]
    try:
        return strip_payment_urls(strip_placeholders(await llm(final, max_tokens=REPLY_MAX_TOKENS, tenant_id=tenant_id)))[0]
    except Exception:
        logger.exception("Deal reply final text call failed for lead %s", ctx.lead_id)
        return ""


async def converse_once(
    chat_messages: list[dict],
    other_tools: list[dict],
    ctx: deal_actions.DealContext,
    *,
    tenant_id: str,
    llm_with_tools=None,
    llm=None,
    append_link: bool = True,
    handover_opened: bool = False,
    handover_line: str = "",
) -> tuple[str, list[dict], deal_actions.Outcome]:
    """(reply text, the model's tool calls, what to attach).

    One model call in the normal case. A second round runs only when the model wrote no
    text, or the system refused something (a tool, a price not in the catalog/offerings, a
    near-repeat of the last message): the model is shown what happened and the fresh DEAL
    STATE, and may write the message or make the next call (e.g. create_payment_link right
    after select_offering). If the words are still missing, one tool-free call writes them.

    The package payment link is appended by code after the text (append_link=False lets the
    caller do it after its own post-processing). A product quote's text and link are in
    outcome.quote_text for the caller to append the same way."""
    if llm_with_tools is None or llm is None:
        from app.services import ai_reply
        llm_with_tools = llm_with_tools or ai_reply._llm_chat_with_tools
        llm = llm or ai_reply._llm_chat
    tools = (deal_engine.deal_tools(ctx.config) if ctx.offerings_enabled else []) + list(other_tools)
    last_text = _last_assistant_text(chat_messages)
    customer_message = _last_user_text(chat_messages)
    line_said_before = any(_said_handover_line(t, handover_line) for t in _earlier_assistant_texts(chat_messages))
    wanted_line_again = False
    messages = list(chat_messages)
    if handover_opened:
        ctx = dataclasses.replace(ctx, payment_concern=True)
    if handover_opened and messages and messages[0].get("role") == "system":
        messages[0] = {**messages[0], "content": messages[0]["content"] + HANDOVER_OPENED_NOTE}
    all_calls: list[dict] = []
    attached = _Attached()
    text = ""
    refusals: tuple[str, ...] = ()
    text_only = not tools
    for attempt in range(MAX_ROUNDS):
        try:
            if text_only:
                # No tools, or every action is done and only the words are missing: offer no
                # tools, so the model cannot answer with yet another silent tool call.
                draft, calls = await llm(messages, max_tokens=REPLY_MAX_TOKENS, tenant_id=tenant_id), []
            else:
                draft, calls = await llm_with_tools(
                    messages, tools=tools, max_tokens=REPLY_MAX_TOKENS, tenant_id=tenant_id,
                )
        except Exception:
            if attempt == 0:
                raise
            logger.exception("Deal reply second round failed -- keeping what we have")
            break
        draft, removed_url = strip_payment_urls(strip_placeholders(draft))
        if attempt == 0 and line_said_before and _said_handover_line(draft, handover_line):
            # The model reached for the "I can't help" line a second time: it has nothing
            # more to offer here. Bring a person in; the message itself gets rewritten below.
            wanted_line_again = True
        text = draft or text
        all_calls.extend(calls)
        outcome = (
            deal_actions.Outcome() if not calls
            else await deal_actions.apply_tool_calls(calls, ctx, last_assistant_text=last_text, auto_link=True)
        )
        attached.add(outcome)
        refusals = (
            *outcome.refusals,
            *_price_refusals(draft, ctx, customer_message),
            *_repeat_refusals(draft, _earlier_assistant_texts(chat_messages)),
            *_bare_handover_refusals(draft, handover_line, handover_opened),
            *_repeated_line_refusals(draft, handover_line, line_said_before),
            *_payment_url_refusals(removed_url, attached),
        )
        if draft and not refusals:
            break
        text_only = not tools or (attached.any() and not refusals and not draft)
        if attempt < MAX_ROUNDS - 1:
            messages = [
                *messages,
                {"role": "assistant", "content": draft or "(no text)"},
                {"role": "user", "content": _round_note(ctx, refusals, attached)},
            ]
    if not text:
        text = await _final_text(messages, ctx, refusals, attached, tenant_id, llm)
    text, _ = strip_payment_urls(text)
    if sombre(customer_message):
        text = without_emoji(text)
    if refusals and deal_engine.unknown_prices(text, ctx.config, customer_message, ctx.known_prices):
        logger.warning("Reply still quotes a price outside the catalog/offerings for lead %s", ctx.lead_id)
    if wanted_line_again and not attached.handover:
        deal_actions.open_handover(ctx, REPEATED_HANDOVER_REASON)
        attached.handover = True
    if attached.link and append_link:
        text = f"{text}\n{attached.link}".strip()
    return text, all_calls, attached.outcome(refusals)


async def send_menu(phone: str, body: str, menu: dict, *, tenant_id: str, phone_number_id: str | None = None) -> str | None:
    """Send the AI's text with tappable options attached. Falls back to plain text with the
    options listed, so a WhatsApp interactive-message failure never costs the customer the turn."""
    from app.services import meta_cloud
    try:
        if menu["kind"] == "buttons":
            data = await meta_cloud.send_interactive_buttons(
                to_number=phone, body_text=body, buttons=menu["buttons"],
                tenant_id=tenant_id, phone_number_id=phone_number_id,
            )
        else:
            data = await meta_cloud.send_list_message(
                to_number=phone, body_text=body, button_text=menu["button_text"], sections=menu["sections"],
                tenant_id=tenant_id, phone_number_id=phone_number_id,
            )
        return (data.get("messages") or [{}])[0].get("id")
    except Exception:
        logger.exception("Interactive menu send failed -- falling back to plain text")
        from app.services.ai_reply import send_whatsapp
        listing = "\n".join(f"• {title}" for title in menu["options"])
        return await send_whatsapp(phone, f"{body}\n\n{listing}", tenant_id=tenant_id, phone_number_id=phone_number_id)
