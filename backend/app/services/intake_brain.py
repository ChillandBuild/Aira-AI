"""Brain-led intake: the main reply engine drives the paid intake flow directly.

The default flow is composer-led — `route_intake` owns every decision (what to
ask, when to skip, when to charge) and calls `intake_copy` for a narrow, cheap
line of copy. That is deterministic and safe, but the collector only understands
the handful of situations the state machine has branches for; anything else
(a voice note, an unrelated complaint, "put me on to a person") falls through to
a re-ask.

Brain-led is the alternative being evaluated: `route_intake` steps aside, the
real `generate_reply` handles the turn with its full pipeline, and the intake
state is advanced through function-calling tools instead of Python branches.
The model chooses what to say AND what to record; the code still owns every
consequence that costs money:

- the charge is always the amount snapshotted on the session, never a number the
  model produced — `send_payment_link` deliberately takes no arguments;
- the payment tool is not even offered until a package and every field are held,
  and `_send_payment_link` re-checks that anyway;
- only configured field keys are stored, only configured package keys accepted;
- the payment URL is rendered in Python and appended verbatim to the reply.

Gated to an explicit per-tenant phone allowlist (`intake_brain_led_phones`) so
it can be exercised on one real number while every other lead stays on the
composer-led path. Fails closed: no setting, bad JSON, or any lookup error means
the gate is off.
"""
import json
import logging
import re
import uuid

from app.config_dynamic import get_setting
from app.services.intake import (
    _package_patch,
    _rupees,
    _update_session,
    normalize_packages,
    pending_fields,
)
from app.services.payment_razorpay import create_payment_link

logger = logging.getLogger(__name__)

BRAIN_LED_SETTING_KEY = "intake_brain_led_phones"

# Indian numbers arrive as +91XXXXXXXXXX from Meta but get typed into the console
# in every shape a human types a phone number. Compare the last 10 digits only.
_SIGNIFICANT_DIGITS = 10


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")[-_SIGNIFICANT_DIGITS:]


def is_brain_led(tenant_id: str, phone: str) -> bool:
    """Whether this lead's turns should be handled by the main brain instead of
    the composer-led state machine. Fails closed on anything unexpected."""
    if not phone:
        return False
    try:
        raw = get_setting(BRAIN_LED_SETTING_KEY, fallback="", tenant_id=tenant_id) or ""
        if not raw.strip():
            return False
        listed = json.loads(raw)
        if not isinstance(listed, list):
            return False
    except Exception as e:
        logger.warning(f"Brain-led allowlist unreadable for tenant {tenant_id}, staying composer-led: {e}")
        return False

    target = _digits(phone)
    if not target:
        return False
    return any(_digits(str(entry)) == target for entry in listed)


def _outstanding(config: dict, session: dict) -> list[dict]:
    return pending_fields(
        config.get("fields") or [],
        session.get("collected_data") or {},
        session.get("skipped_fields") or [],
    )


def _ready_to_charge(config: dict, session: dict) -> bool:
    return bool(session.get("package_amount_paise")) and not _outstanding(config, session)


def intake_tools(config: dict, session: dict) -> list[dict]:
    """The tools available on THIS turn. Availability is itself a guardrail: a
    tool that isn't on the menu is one the model cannot talk itself into."""
    fields = config.get("fields") or []
    service_noun = config.get("service_noun") or "consultation"

    tools: list[dict] = [
        {
            "type": "function",
            "function": {
                "name": "save_intake_details",
                "description": (
                    "Record details the customer just gave you for their "
                    f"{service_noun}. Call this the moment they provide any of these "
                    "values, in the same reply where you acknowledge them. Pass the "
                    "value exactly as the customer wrote it — never reformat, "
                    "translate, or correct it. Omit any field they did not mention."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        f["key"]: {
                            "type": "string",
                            "description": f"{f['label']} ({f.get('type', 'text')})",
                        }
                        for f in fields
                    },
                },
            },
        },
    ]

    outstanding = _outstanding(config, session)
    if outstanding:
        # Without this the brain can decide to move on but has no way to say so:
        # the field stays pending, send_payment_link is never offered, and the flow
        # has no exit. Live evidence 2026-08-15 -- it improvised one, by starting
        # the reading itself, unpaid.
        tools.append({
            "type": "function",
            "function": {
                "name": "skip_intake_field",
                "description": (
                    "Give up on one detail and move on. Call this when the customer "
                    "has said twice that they do not know it, or clearly cannot "
                    "provide it. The expert will work without it. Always call this "
                    "rather than silently dropping the question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field_key": {
                            "type": "string",
                            "enum": [f["key"] for f in outstanding],
                            "description": "The detail the customer cannot provide",
                        }
                    },
                    "required": ["field_key"],
                },
            },
        })

    tools.append(
        {
            "type": "function",
            "function": {
                "name": "cancel_intake",
                "description": (
                    f"Call this only when the customer clearly no longer wants the paid "
                    f"{service_noun} — they say to stop, cancel, forget it, or maybe later. "
                    "Do not call it because they asked a question or hesitated."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        }
    )

    if not session.get("package_key"):
        packages = normalize_packages(config)
        if packages:
            # The name -> key mapping lives here rather than in the prompt block:
            # tool descriptions are never read out to the customer, and the block
            # was leaking internal keys into replies (live evidence 2026-08-15,
            # "namma Basic (basic) package irukku").
            mapping = "; ".join(f'"{p["name"]}" = {p["key"]}' for p in packages)
            tools.append({
                "type": "function",
                "function": {
                    "name": "choose_package",
                    "description": (
                        "Record which package the customer picked. Only call this once "
                        f"they have actually chosen one. Package names map to keys as: {mapping}."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "package_key": {
                                "type": "string",
                                "enum": [p["key"] for p in packages],
                                "description": "The key of the package the customer chose",
                            }
                        },
                        "required": ["package_key"],
                    },
                },
            })

    if _ready_to_charge(config, session):
        tools.append({
            "type": "function",
            "function": {
                "name": "send_payment_link",
                "description": (
                    "Generate the payment link and attach it to your reply. Call this "
                    "only after the customer has confirmed the details you read back to "
                    "them are correct. The system appends the real link to your message "
                    "automatically — write your sentence as if the link follows it, and "
                    "never type a link or a price yourself."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        })

    return tools


def intake_prompt_block(config: dict, session: dict, *, just_sent_link: bool = False) -> str:
    """What the brain needs to know about the sale in progress. Prices are
    rendered here in Python for the same reason package_list_block does it: the
    customer is held to these figures.

    just_sent_link=True is for the second pass after send_payment_link fired on
    THIS turn: the session already reads awaiting_payment, but telling the model
    the link "has already been sent" would make it write about an old link
    instead of the one about to be appended to its own sentence.
    """
    service_noun = config.get("service_noun") or "consultation"
    collected = session.get("collected_data") or {}
    fields = config.get("fields") or []
    outstanding = _outstanding(config, session)

    lines = [f"\n\nPAID {service_noun.upper()} IN PROGRESS:"]
    lines.append(
        f"This customer is signing up for a paid one-on-one {service_noun} with our "
        "human expert. You are handling that sign-up yourself, in this conversation, "
        "using your tools. Keep sounding like yourself — this is the same chat, not a form."
    )

    if not session.get("package_key"):
        packages = normalize_packages(config)
        if packages:
            lines.append("\nPACKAGES (quote these exactly, never invent a price):")
            for p in packages:
                line = f"- {p['name']} — {_rupees(p['amount_paise'])}"
                if p.get("description"):
                    line += f": {p['description']}"
                lines.append(line)
            lines.append("Once they pick one, call choose_package.")
    else:
        lines.append(
            f"\nChosen package: {session.get('package_name') or session['package_key']} "
            f"— {_rupees(session.get('package_amount_paise') or 0)}"
        )

    held = [f"{f['label']}: {collected[f['key']]}" for f in fields if collected.get(f["key"])]
    if held:
        lines.append("\nDETAILS ALREADY GIVEN (never ask for these again):")
        lines.extend(held)

    if outstanding:
        lines.append("\nSTILL NEEDED (ask for ONE at a time, in this order):")
        lines.extend(f"- {f['label']}" for f in outstanding)
        lines.append(
            "Call save_intake_details as soon as they answer. If they say twice that "
            "they do not know one, call skip_intake_field for it and move to the next — "
            "never just stop asking, and never move on without calling it. If they ask "
            "you something else, answer that first, then re-ask."
        )
    elif just_sent_link:
        lines.append(
            "\nYou have just generated their payment link. Write ONE short sentence "
            "telling them to pay using the link that follows your message — the system "
            "appends the real link right after your text. Do not type a link yourself."
        )
    elif session.get("status") == "awaiting_payment":
        lines.append(
            "\nA payment link has already been sent and is waiting on them. Do not send "
            "another one. Answer their questions and let them know the link is still open."
        )
    elif _ready_to_charge(config, session):
        lines.append(
            "\nYou have everything. Read the details back to them exactly as recorded, "
            "ask them to confirm, and once they do, call send_payment_link."
        )

    lines.append(
        "\nRules:\n"
        "- Never type a payment link, a price, or an amount that is not listed above.\n"
        "- Never claim payment is done — that is confirmed separately.\n"
        "- Never tell them to use an app, a website, or any other way to reach an "
        f"expert — this {service_noun} is the way.\n"
        # Live evidence 2026-08-15: mid-collection and unpaid, the model wrote "tell me
        # your question now and I'll send it to our astrologer", then offered guidance
        # by voice note or text -- handing over the paid service for free.
        f"- The {service_noun} itself has NOT started and will not start until they "
        "have paid. Do not ask them for their question, do not take it, do not answer "
        "it, and do not say the expert is looking at it or will reply to it. Your only "
        "job right now is to finish the sign-up.\n"
        "- Keep replies short, one question at a time, in the conversation's language."
    )
    return "\n".join(lines)


async def _save_details(args: dict, *, session: dict, config: dict, db) -> None:
    valid_keys = {f["key"] for f in (config.get("fields") or [])}
    new_values = {k: str(v).strip() for k, v in args.items() if k in valid_keys and str(v).strip()}
    if not new_values:
        return

    collected = {**(session.get("collected_data") or {}), **new_values}
    session["collected_data"] = collected
    patch = {"collected_data": collected}

    # A customer who first said "I don't know" and later remembers must not have
    # their answer filed under a field the flow has already given up on.
    skipped = [k for k in (session.get("skipped_fields") or []) if k not in new_values]
    if skipped != (session.get("skipped_fields") or []):
        session["skipped_fields"] = skipped
        patch["skipped_fields"] = skipped

    # Status is derived from the data rather than stepped through a ladder --
    # brain-led turns can fill several fields at once, or fill the last one out
    # of order, and the session must land in the right place either way.
    if session.get("package_key") and not _outstanding(config, session):
        if session.get("status") not in ("awaiting_payment", "paid"):
            patch["status"] = "awaiting_confirmation"
            session["status"] = "awaiting_confirmation"
    _update_session(session["id"], patch, db)


async def _skip_field(args: dict, *, session: dict, config: dict, db) -> None:
    """Record that a detail has been given up on, so it stops blocking the flow.
    Only an actually-outstanding field can be skipped -- skipping one the customer
    already answered would silently discard their answer."""
    key = args.get("field_key")
    if key not in {f["key"] for f in _outstanding(config, session)}:
        logger.warning(f"Brain-led intake: refused to skip {key!r} (not an outstanding field)")
        return

    skipped = [*(session.get("skipped_fields") or []), key]
    session["skipped_fields"] = skipped
    patch = {"skipped_fields": skipped}
    if session.get("package_key") and not _outstanding(config, session):
        if session.get("status") not in ("awaiting_payment", "paid"):
            patch["status"] = "awaiting_confirmation"
            session["status"] = "awaiting_confirmation"
    _update_session(session["id"], patch, db)


async def _choose_package(args: dict, *, session: dict, config: dict, db) -> None:
    key = args.get("package_key")
    chosen = next((p for p in normalize_packages(config) if p["key"] == key), None)
    if chosen is None:
        logger.warning(f"Brain-led intake: model chose unknown package {key!r}, ignoring")
        return
    patch = _package_patch(chosen)
    session.update(patch)
    patch["status"] = "awaiting_confirmation" if not _outstanding(config, session) else "collecting"
    session["status"] = patch["status"]
    _update_session(session["id"], patch, db)


async def _send_payment_link(
    *, session: dict, config: dict, tenant_id: str, phone: str, db
) -> str:
    """Returns the URL to append to the reply, or "" if no charge should happen.
    Re-checks readiness even though the tool is only offered when ready -- a
    hallucinated call must not be able to bill anyone."""
    if not _ready_to_charge(config, session):
        logger.warning(
            f"Brain-led intake: send_payment_link called on session {session['id']} "
            "before package/details were complete — refused"
        )
        return ""
    if session.get("status") in ("awaiting_payment", "paid"):
        logger.info(f"Brain-led intake: session {session['id']} already has a live link — not re-sending")
        return ""

    amount_paise = session["package_amount_paise"]
    collected = session.get("collected_data") or {}
    customer_name = collected.get("name") or collected.get("full_name") or "Customer"
    ref = f"IN-{uuid.uuid4().hex[:8].upper()}"
    service_noun = (config.get("service_noun") or "consultation").capitalize()

    try:
        link = await create_payment_link(
            booking_id=session["id"],
            booking_ref=ref,
            amount_paise=amount_paise,
            customer_name=customer_name,
            customer_phone=phone,
            description=f"{service_noun} — {customer_name} ({ref})",
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.error(f"Brain-led intake: payment link creation failed for session {session['id']}: {e}")
        return ""

    url = link["payment_link_url"]
    _update_session(
        session["id"],
        {"status": "awaiting_payment", "amount_paise": amount_paise, "payment_link": url},
        db,
    )
    session["status"] = "awaiting_payment"
    return url


async def execute_intake_tools(
    tool_calls: list[dict],
    *,
    session: dict,
    config: dict,
    tenant_id: str,
    lead_id: str,
    phone: str,
    db,
) -> str:
    """Run whatever the model asked for. Returns text to append verbatim to the
    reply (currently only a payment URL), or "" if there is nothing to append.

    Never raises: a tool failure must degrade to a reply without that side
    effect, not to no reply at all.
    """
    appended = ""
    for call in tool_calls or []:
        func = call.get("function") or {}
        name = func.get("name")
        try:
            args = json.loads(func.get("arguments") or "{}")
        except (ValueError, TypeError):
            logger.warning(f"Brain-led intake: unparseable arguments for tool {name!r}, skipping")
            continue
        if not isinstance(args, dict):
            continue

        try:
            if name == "save_intake_details":
                await _save_details(args, session=session, config=config, db=db)
            elif name == "skip_intake_field":
                await _skip_field(args, session=session, config=config, db=db)
            elif name == "choose_package":
                await _choose_package(args, session=session, config=config, db=db)
            elif name == "send_payment_link":
                appended = await _send_payment_link(
                    session=session, config=config, tenant_id=tenant_id, phone=phone, db=db
                )
            elif name == "cancel_intake":
                _update_session(session["id"], {"status": "cancelled"}, db)
                session["status"] = "cancelled"
                logger.info(f"Brain-led intake: session {session['id']} cancelled by lead")
            else:
                logger.warning(f"Brain-led intake: ignoring unknown tool {name!r}")
        except Exception as e:
            logger.error(f"Brain-led intake: tool {name!r} failed for lead {lead_id}: {e}")

    return appended
