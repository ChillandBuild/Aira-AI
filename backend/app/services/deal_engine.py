"""AI-native selling: the prompt blocks, tool schemas and guardrails that let the main
reply brain sell packages, collect a client's required details and send the payment link
itself, instead of a fixed step-by-step script (services/intake.route_intake).

Design: docs/plans/ai-native-conversation.md.

This module is the pure half: config in, text or schemas out. The executors that touch
the session store and Razorpay live in services/deal_actions.py; the model round-trip is
converse_once in the same file as the executors' caller. Money rules are enforced there,
never trusted to the model: prices come from config, the link comes from Razorpay, and a
link is refused until every required detail is saved or skipped.
"""
import re

PAID_STATUS = "paid"
AWAITING_PAYMENT_STATUS = "awaiting_payment"
COLLECTING_STATUS = "collecting"
CONFIRM_STATUS = "awaiting_confirmation"

TOOL_SHOW_OPTIONS = "show_options"
TOOL_SELECT_OFFERING = "select_offering"
TOOL_SAVE_DETAILS = "save_details"
TOOL_SKIP_DETAIL = "skip_detail"
TOOL_CREATE_PAYMENT_LINK = "create_payment_link"
TOOL_HAND_TO_HUMAN = "hand_to_human"
DEAL_TOOL_NAMES = frozenset({
    TOOL_SHOW_OPTIONS, TOOL_SELECT_OFFERING, TOOL_SAVE_DETAILS,
    TOOL_SKIP_DETAIL, TOOL_CREATE_PAYMENT_LINK, TOOL_HAND_TO_HUMAN,
})

# "I paid", "pay pana", "status of my payment", "money deducted". Deliberately narrow:
# "how do I pay?" and "is it paid or free?" are ordinary buying talk, not a complaint.
_PAYMENT_COMPLAINT_RE = re.compile(
    r"\b(?:i|ive|i've|already|na)\s+(?:have\s+)?(?:\d+\s+)?paid\b"
    r"|\bpaid\s+the\s+money\b"
    r"|\bpay\s*pan(?:a|na|nen)\b"
    r"|\bpayment\s+(?:status|failed|not|done|problem|issue|pending|confirm)"
    r"|\bstatus\s+(?:of|for)\s+my\s+payment\b"
    r"|\bmoney\s+(?:deducted|debited|gone|cut)\b"
    # refunds and cancelling something paid for: a person decides these, never the AI
    r"|\brefund\w*"
    r"|\bmoney\s+back\b"
    r"|\breturn\s+(?:the\s+|my\s+)?(?:amount|money|payment)\b"
    r"|\bcancel\w*\s+(?:my\s+|the\s+)?(?:order|booking|payment|consultation|appointment|course)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"\w", re.UNICODE)


_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT_BEFORE_RE = re.compile(rf"(?:₹|\bRs\.?|\bINR)\s*({_NUMBER})", re.IGNORECASE)
_AMOUNT_AFTER_RE = re.compile(rf"({_NUMBER})\s*(?:Rs\b|rupees?\b|ரூபாய்)", re.IGNORECASE)
_NUMBER_RE = re.compile(_NUMBER)


def _intake():
    from app.services import intake
    return intake


def _active(nodes: list[dict]) -> list[dict]:
    return [n for n in nodes if n.get("active", True)]


def _leaves(nodes: list[dict]) -> list[dict]:
    found: list[dict] = []
    for node in _active(nodes):
        if node.get("options"):
            found.extend(_leaves(node["options"]))
        else:
            found.append(node)
    return found


def is_enabled(config: dict) -> bool:
    """The tenant's off switch plus at least one purchasable package."""
    if not config.get("enabled"):
        return False
    return bool(_leaves(_intake().normalize_packages(config)))


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def _addon_sums(base: int, addons: list[dict]) -> set[int]:
    """The offering price alone and with every combination of its add-ons (paise)."""
    totals = {base}
    for addon in addons:
        totals |= {t + addon["amount_paise"] for t in totals}
    return totals


def allowed_prices(config: dict) -> set[float]:
    """Every rupee figure the business actually charges: each offering, alone or with any
    of its add-ons."""
    allowed: set[float] = set()
    for leaf in _leaves(_intake().normalize_packages(config)):
        allowed |= {t / 100 for t in _addon_sums(leaf["amount_paise"], _active(leaf.get("addons") or []))}
        allowed |= {a["amount_paise"] / 100 for a in _active(leaf.get("addons") or [])}
    return allowed


MAX_QUANTITY_MULTIPLE = 10


def price_multiples(prices_paise) -> set[float]:
    """Rupee figures for 1..10 units of each price: '2 pairs come to Rs 4,998' is a real price."""
    return {p * n / 100 for p in prices_paise if p for n in range(1, MAX_QUANTITY_MULTIPLE + 1)}


def unknown_prices(reply: str, config: dict, customer_message: str, extra_allowed=()) -> list[float]:
    """Rupee amounts in a draft reply that are neither a real price nor a number the
    customer just wrote. The model's knowledge base can hold an older price; code, not the
    model's good intentions, is what keeps it out of a message.

    Only active when the business has structured prices (packages, catalog or orders): a
    business that keeps all its prices in knowledge text has nothing to check against."""
    allowed = allowed_prices(config) | set(extra_allowed)
    if not allowed:
        return []
    found = {_to_float(a) for a in _AMOUNT_BEFORE_RE.findall(reply) + _AMOUNT_AFTER_RE.findall(reply)}
    said = {_to_float(n) for n in _NUMBER_RE.findall(customer_message or "")}
    return sorted(found - allowed - said)


def business_facts_block(details: dict) -> str:
    """The business's own identity (Settings > Business details), so a lead asking for the
    GST number, the registered address or an invoice name gets the real answer, not a
    handover. Only filled fields are shown."""
    details = details or {}
    address = ", ".join(p for p in (details.get("address"), details.get("city")) if p)
    region = " ".join(p for p in (details.get("state"), details.get("pincode")) if p)
    address = ", ".join(p for p in (address, region) if p)
    facts = [
        ("Registered business name", details.get("legal_name")),
        ("Address", address),
        ("GSTIN", details.get("gstin")),
        ("Email", details.get("email")),
        ("Phone", details.get("phone")),
    ]
    lines = [f"- {label}: {value}" for label, value in facts if value]
    if not lines:
        return ""
    gst = (
        "Listed prices include GST."
        if details.get("prices_include_gst", True)
        else "Listed prices exclude GST; a quote adds GST on top, so its total can be higher than the listed price."
    )
    return "\n\nBUSINESS DETAILS (official, share when asked):\n" + "\n".join(lines) + f"\n{gst}"


_ORDER_STAGE_TEXT = {
    "quoted": "price mentioned, no link yet",
    "awaiting_payment": "payment link sent, not paid yet",
    "won": "PAID",
    "lost": "cancelled",
}


def orders_block(deals: list[dict]) -> str:
    """The lead's recent product orders, so Aira knows what was quoted, sent and paid.
    Rendered by code; never includes a link the model could copy."""
    if not deals:
        return ""
    lines = []
    for deal in deals:
        items = ", ".join(f"{i['name']} × {i.get('qty', 1)}" for i in deal.get("items") or []) or "items"
        state = _ORDER_STAGE_TEXT.get(deal.get("stage"), deal.get("stage") or "")
        number = f"D-{int(deal.get('deal_number') or 0):04d}"  # same format as deals.format_deal_number
        lines.append(f"- {number}: {items} — {_rupees(deal.get('total_paise') or 0)} — {state}")
    return (
        "\n\nORDERS (this customer's recent product orders, from the system; trust these over the chat):\n"
        + "\n".join(lines)
        + "\nIf they ask about an order, answer from this. A PAID order is paid; never ask them to pay it "
        "again. If a link is sent but not paid and they want to pay, call send_quote again for the same "
        "items and quantities: the system resends the same link."
    )


def is_blank_message(message: str) -> bool:
    """Only emoji / punctuation ('?', '👍'): no words to answer, so continue the open booking."""
    return not _WORD_RE.search(message or "")


def is_payment_complaint(message: str) -> bool:
    return bool(_PAYMENT_COMPLAINT_RE.search(message or ""))


def missing_details(fields: list[dict], collected: dict, skipped) -> list[str]:
    """Keys of required details that are neither saved nor marked not-provided."""
    skipped_set = set(skipped or [])
    return [
        f["key"] for f in fields
        if not (collected or {}).get(f["key"]) and f["key"] not in skipped_set
    ]


def _rupees(amount_paise: int) -> str:
    return _intake()._rupees(amount_paise)


def _offering_lines(nodes: list[dict], indent: str = "") -> list[str]:
    lines: list[str] = []
    for node in _active(nodes):
        if node.get("options"):
            lines.append(f"{indent}- Category {node['name']} (key: {node['key']}) contains:")
            lines.extend(_offering_lines(node["options"], indent + "    "))
            continue
        line = f"{indent}- {node['name']} — {_rupees(node['amount_paise'])} (key: {node['key']}"
        if node.get("button_label"):
            line += f", button: {node['button_label']}"
        line += ")"
        if node.get("description"):
            line += f": {node['description']}"
        lines.append(line)
        for addon in _active(node.get("addons") or []):
            lines.append(
                f"{indent}    add-on {addon['name']} — +{_rupees(addon['amount_paise'])} (key: {addon['key']})"
            )
    return lines


def offerings_block(config: dict) -> str:
    packages = _intake().normalize_packages(config)
    noun = config.get("service_noun") or "consultation"
    return (
        f"OFFERINGS — the only {noun} options you may sell. Prices are fixed; quote them exactly "
        "as written here and never change, round or invent one:\n" + "\n".join(_offering_lines(packages))
    )


def required_details_block(fields: list[dict]) -> str:
    if not fields:
        return "REQUIRED DETAILS: none. The payment link can go out as soon as they have chosen."
    lines = [
        f"- {f['key']}: {f['label']}" + (f" (one of: {', '.join(f['options'])})" if f.get("options") else "")
        for f in fields
    ]
    return (
        "REQUIRED DETAILS to collect before the payment link (the business chose these):\n"
        + "\n".join(lines)
    )


def _payment_line(session: dict) -> str:
    status = session.get("status")
    amount = session.get("amount_paise") or session.get("total_amount_paise") or session.get("package_amount_paise")
    if status == PAID_STATUS:
        return "PAID"
    if status == AWAITING_PAYMENT_STATUS and session.get("payment_link"):
        return f"link sent ({_rupees(amount)}), not paid yet"
    return "not sent"


def _next_step(session: dict, missing: list[str], labels: dict) -> str:
    status = session.get("status")
    if status == PAID_STATUS:
        return "they have paid. Do not sell or send a link; help with anything else and reassure them."
    if status == AWAITING_PAYMENT_STATUS and session.get("payment_link"):
        return ("the link was already sent. If they want to pay, call create_payment_link to resend "
                "the same link; otherwise just answer them.")
    if missing:
        return f"ask for {labels.get(missing[0], missing[0])} (only after answering anything they asked)."
    return "send the payment link now by calling create_payment_link."


def deal_state_block(config: dict, session: dict | None) -> str:
    header = "DEAL STATE (facts from the system; trust these over the chat history):"
    if not session or not session.get("package_key"):
        return (
            f"{header}\n- Offering: nothing chosen yet\n- Payment: not sent\n"
            "- Next step: help them choose, but only if they show interest; otherwise just answer them."
        )
    fields = config.get("fields") or []
    collected = session.get("collected_data") or {}
    skipped = session.get("skipped_fields") or []
    total = session.get("total_amount_paise") or session.get("package_amount_paise")
    have = "; ".join(f"{k} = {v}" for k, v in collected.items() if v) or "none yet"
    missing = missing_details(fields, collected, skipped)
    labels = {f["key"]: f["label"] for f in fields}
    needed = ", ".join(f"{k} ({labels.get(k, k)})" for k in missing) or "none — ready for the payment link"
    lines = [
        header,
        f"- Offering: {session.get('package_name')} — {_rupees(total)}",
        f"- Details collected: {have}",
        f"- Details still needed: {needed}",
    ]
    if skipped:
        lines.append(f"- Details the customer could not give: {', '.join(skipped)}")
    lines.append(f"- Payment: {_payment_line(session)}")
    lines.append(f"- Next step: {_next_step(session, missing, labels)}")
    return "\n".join(lines)


def _rules_block(config: dict, tapped_key: str | None) -> str:
    noun = config.get("service_noun") or "consultation"
    rules = [
        "Answer the customer's question first, then, only if it helps, move them toward a choice.",
        f"You sell the {noun} right here in this chat. When they ask what you offer, the price, or "
        "whether it is worth it, answer directly from OFFERINGS (name the options and their prices, and "
        "who each suits). Do not send them to an app or website to see prices or to buy these. If "
        "your knowledge says prices or offers are shown in an app, that is a different channel; for "
        "anything in OFFERINGS the price is the one here, and there is no discount unless OFFERINGS shows one.",
        "If DEAL STATE shows a choice already in progress and the customer comes back (a greeting, "
        "'hi', a new day), welcome them back in a few words and continue from exactly where it "
        "stopped: ask for the next missing detail, or offer the link. Do not start over.",
        "Show tappable options with show_options only when they really need to choose. Never "
        "show or list the same options twice in a row (not as buttons and not as a typed list); if "
        "they hesitate or reply vaguely, ask which one in words or recommend one.",
        "When they choose, call select_offering. If that offering has add-ons, ask about them "
        "first and pass addon_keys (an empty list if they want none). If REQUIRED DETAILS is "
        "none and there are no add-ons, call create_payment_link in that same turn, right "
        "after select_offering.",
        "Never ask for a detail the customer already gave anywhere in this chat, even before they "
        "chose; when they choose, save what they already told you straight away. "
        "Collect each required detail from the customer's own words: ask one at a time unless "
        "they give several at once, and call save_details as soon as you have any. If they cannot "
        "or will not answer a detail after you asked, call skip_detail for it.",
        "When DEAL STATE shows nothing is still needed, call create_payment_link in that same "
        "turn. The system attaches the real link; you write only a short lead-in.",
        "Never write a payment link, a URL you were not given, or a price that is not in OFFERINGS. "
        "Your knowledge base may still mention older prices or packages; when it disagrees with "
        "OFFERINGS, OFFERINGS is right and the older figure must never be quoted. "
        "Never say a link was sent unless you called create_payment_link and it worked.",
        "If a tool reply says it was refused, do what its message says. Do not pretend it worked.",
        "If they say they paid, that money was deducted, or ask about payment status: call "
        "hand_to_human right away. Never say the payment is confirmed or missing, and do not "
        "point them to an app or a support desk instead.",
        "Also call hand_to_human when they ask for a person or when you cannot answer the same "
        "thing after a second ask. Follow the HANDOVER RULE wording for what you tell them, "
        "once. On later messages do not repeat that line word for word: acknowledge what they "
        "just said in your own words and say the team has been told, without promising a time.",
        "SOURCE OF TRUTH: OFFERINGS and REQUIRED DETAILS were set by the business on its packages "
        "page and override anything in your description or knowledge that disagrees: the price, "
        "what is sold in this chat, where to buy it, and which details to ask for. If your "
        "description says never to ask for something REQUIRED DETAILS lists, ask for it anyway, "
        f"politely, because it is needed to prepare their {noun}.",
        "Never invent an offering, discount, deadline or policy that is not in your knowledge.",
        f"Never say the {noun} is booked, confirmed or reserved until DEAL STATE shows PAID; before "
        "that, say it gets confirmed once the payment is done. You cannot see a diary or slots, so "
        "never claim a time is free or held.",
        "While a booking is open or after they have paid, show products or photos only if the "
        "customer asks about a product; never push one on your own.",
        "If they clearly say no or ask you to stop, stop selling and close politely in one line.",
        f"Sound like one real person on WhatsApp: short, warm, use their name once known, "
        f"no bot phrases like 'please select an option'. This is a {noun}, not a form.",
    ]
    text = f"HOW TO SELL THE {noun.upper()}:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    if tapped_key:
        text += (
            f"\n\nThe customer just tapped the option with key {tapped_key!r}. Treat that as their choice."
        )
    return text


def _resume_note(config: dict, session: dict | None) -> str:
    """For a bare greeting while a deal is open: weaker models answer 'hi' with a stock
    welcome and forget the half-finished booking, so say exactly what to do, last."""
    if not session or not session.get("package_key") or session.get("status") == PAID_STATUS:
        return ""
    fields = config.get("fields") or []
    missing = missing_details(fields, session.get("collected_data") or {}, session.get("skipped_fields") or [])
    labels = {f["key"]: f["label"] for f in fields}
    if session.get("status") == AWAITING_PAYMENT_STATUS and session.get("payment_link"):
        step = f"gently mention their {session.get('package_name')} payment link is ready whenever they are."
    elif missing:
        step = f"ask for their {labels.get(missing[0], missing[0])}."
    else:
        step = "offer to send the payment link for " + str(session.get("package_name")) + "."
    return (
        f"\n\nTHE CUSTOMER IS BACK after a pause, mid-way through booking {session.get('package_name')}. "
        f"Do not reply with a generic greeting: welcome them back in one short line and, in the same "
        f"message, {step}"
    )


def deal_prompt(config: dict, session: dict | None, *, tapped_key: str | None = None, returning: bool = False) -> str:
    body = "\n\n" + "\n\n".join([
        offerings_block(config),
        required_details_block(config.get("fields") or []),
        deal_state_block(config, session),
        _rules_block(config, tapped_key),
    ]) + "\n"
    return body + (_resume_note(config, session) if returning else "")


def handover_tools() -> list[dict]:
    """hand_to_human alone, for replies with no package selling: every business can bring a
    person in, whether or not it sells packages in chat."""
    return [tool for tool in _all_tools({}) if tool["function"]["name"] == TOOL_HAND_TO_HUMAN]


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


def deal_tools(config: dict) -> list[dict]:
    return _all_tools(config)


def _all_tools(config: dict) -> list[dict]:
    packages = _intake().normalize_packages(config)
    keys = [leaf["key"] for leaf in _leaves(packages)]
    fields = config.get("fields") or []
    field_keys = [f["key"] for f in fields]
    key_prop = {"type": "string", "enum": field_keys} if field_keys else {"type": "string"}
    return [
        _tool(
            TOOL_SHOW_OPTIONS,
            "Send the customer tappable buttons or a list of the offerings (or of an offering's "
            "add-ons). Use only when they need to choose. Your text is the message above the options.",
            {
                "of": {"type": "string", "enum": ["packages", "addons"]},
                "under": {"type": "string", "description": "Category key (packages) or offering key (addons). Omit for the top level."},
            },
            ["of"],
        ),
        _tool(
            TOOL_SELECT_OFFERING,
            "Record the offering the customer chose. Price comes from the configuration.",
            {
                "key": {"type": "string", "enum": keys},
                "addon_keys": {"type": "array", "items": {"type": "string"},
                               "description": "Chosen add-on keys. Empty list if none. Required when the offering has add-ons."},
            },
            ["key"],
        ),
        _tool(
            TOOL_SAVE_DETAILS,
            "Save required details the customer just told you, exactly as they said them.",
            {"fields": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in field_keys},
                "additionalProperties": False,
            }},
            ["fields"],
        ),
        _tool(
            TOOL_SKIP_DETAIL,
            "Mark a required detail as not provided when the customer cannot or will not give it.",
            {"key": key_prop, "reason": {"type": "string"}},
            ["key"],
        ),
        _tool(
            TOOL_CREATE_PAYMENT_LINK,
            "Create the payment link for the chosen offering. Takes no amount: the amount is the "
            "chosen offering's price. Refused until every required detail is saved or skipped.",
            {},
        ),
        _tool(
            TOOL_HAND_TO_HUMAN,
            "Pass this chat to a person on the team.",
            {"reason": {"type": "string"}},
            ["reason"],
        ),
    ]
