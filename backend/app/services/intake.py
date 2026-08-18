"""Generic, per-tenant paid intake: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging
import re
import uuid

from app.services.gemini_client import gemini_chat_completion_json
from app.services.intake_copy import (
    collector_identity,
    compose_line,
    compose_wrapped,
    gather_context,
    localized_fields,
    resolve_language_mode,
)
from app.services.notify import notify_pool
from app.services.payment_razorpay import create_payment_link

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "enabled": False,
    "trigger_description": "",
    "offer_message": "",
    "fields": [],  # list of {"key": str, "label": str, "type": "text"|"date"|"choice", "options": list[str]?}
    "packages": [],  # list of {"key": str, "name": str, "amount_paise": int, "description": str}
    "service_noun": "consultation",
    "amount_paise": 0,  # legacy single fee; superseded by packages, kept for auto-migration
}


def get_intake_config(tenant_id: str, db=None) -> dict:
    """Return intake_config from app_settings, merged with defaults."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "intake_config")
        .maybe_single()
        .execute()
    )
    if row and row.data:
        try:
            stored = json.loads(row.data["value"])
            return {**_DEFAULT_CONFIG, **stored}
        except Exception:
            logger.warning(f"Failed to parse intake_config for tenant {tenant_id}")
    return dict(_DEFAULT_CONFIG)


def save_intake_config(tenant_id: str, config: dict, db=None) -> None:
    """Persist intake_config to app_settings."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "intake_config",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()


_DETECTION_SYSTEM_PROMPT = """You are a classifier. Given a business's description of what
kind of message should trigger a paid human-expert handoff, and one incoming customer
message, decide if THIS message matches that description.

Respond with JSON only: {"matches": true} or {"matches": false}. No other text."""


async def detect_intake_intent(message: str, trigger_description: str, tenant_id: str) -> bool:
    """Fail closed: any error, empty trigger_description, or unparseable response -> False.
    A missed offer is recoverable (the lead can ask again); a wrongly-triggered paid
    flow from a classifier hiccup is not."""
    if not trigger_description:
        return False
    user_prompt = f"Trigger description: {trigger_description}\n\nCustomer message: {message}"
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_DETECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=50,
            tenant_id=tenant_id,
            purpose="expert_handoff_detection",
        )
        return bool(data.get("matches") is True)
    except Exception as e:
        logger.warning(f"Intake detection failed, defaulting to no-match: {e}")
        return False


# Tenants name their own intake fields, so the key holding a person's name is
# whatever they typed into the console -- full_name for an astrologer,
# patient_name for a clinic, member_name for a gym. Matching on the literal key
# "name" found none of them. Live evidence 2026-08-15: a lead who typed
# "Prem Kumar D" got "Customer, Payment success aayiduchu" when their payment
# cleared, and staff were notified about "Lead 'Customer'".
#
# The token list is deliberately short and honest: it cannot cover every language
# a tenant might label a field in, which is exactly why resolve_customer_name
# returns None rather than a placeholder when nothing matches. A missing greeting
# is invisible; a wrong one is not.
_NAME_TOKENS = ("name", "naam", "peyar")


def _looks_like_a_name_field(key: str, label: str = "") -> bool:
    haystack = f"{key} {label}".lower()
    return any(token in haystack for token in _NAME_TOKENS)


def resolve_customer_name(
    collected_data: dict | None,
    fields: list[dict] | None = None,
    lead_name: str | None = None,
) -> str | None:
    """The customer's own name, or None when it genuinely cannot be identified.

    Never returns a placeholder: callers decide how to degrade (the receipt drops
    the greeting, the staff notification says "a lead", the Razorpay description
    falls back to the phone number). Config order is respected so a form asking
    for both a customer and a nominee resolves to the customer.
    """
    collected = collected_data or {}

    def _clean(value) -> str | None:
        text = str(value or "").strip()
        return text or None

    if fields:
        for field in fields:
            key = field.get("key", "")
            if _looks_like_a_name_field(key, field.get("label", "")):
                found = _clean(collected.get(key))
                if found:
                    return found
    else:
        for key, value in collected.items():
            if _looks_like_a_name_field(key):
                found = _clean(value)
                if found:
                    return found

    return _clean(lead_name)


def adopt_lead_name(db, lead_id: str, tenant_id: str, name: str | None) -> None:
    """Fill in leads.name from what the customer told the collector, but only when
    the lead has no name yet -- the guard lives in the query rather than a prior
    read, so a name a human set by hand is never overwritten. Best effort: the
    dashboard label is not worth failing a payment or a reply over."""
    if not name:
        return
    try:
        (
            db.table("leads")
            .update({"name": name})
            .eq("id", lead_id)
            .eq("tenant_id", tenant_id)
            .is_("name", "null")
            .execute()
        )
    except Exception as e:
        logger.warning(f"Could not adopt collected name onto lead {lead_id}: {e}")


def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]:
    return [f["label"] for f in fields if not collected_data.get(f["key"])]


_MAX_FIELD_ATTEMPTS = 2

# A message that yields no field value is not automatically a failed attempt at the
# pending field. Live evidence 2026-08-13: a lead's fresh "Hii" was recorded as the
# second failed attempt at place of birth, so the field was skipped and the flow
# jumped to the summary. Greetings, withdrawals and questions are not attempts.
_GREETING_WORDS = frozenset({
    "hi", "hii", "hiii", "hello", "helo", "hey", "hai", "haai",
    "vanakkam", "வணக்கம்", "namaskaram", "good", "morning", "evening", "afternoon",
})

_CANCEL_WORDS = frozenset({
    "vendaam", "vendam", "venam", "veanam", "cancel", "stop", "quit", "exit",
    "later", "apparam", "aprm", "baduve", "வேண்டாம்", "வேண்டாம",
})

_QUESTION_WORDS = frozenset({
    "eppo", "eppa", "enna", "evlo", "evvalavu", "yaar", "yaaru", "epdi", "eppadi",
    "yen", "ean", "when", "what", "how", "why", "who", "where", "will", "can", "does",
    "is", "are", "எப்போ", "எப்படி", "என்ன", "எவ்வளவு", "ஏன்", "யார்",
})


def classify_non_answer(message: str) -> str:
    """Why a message contained no field value: 'greeting' | 'cancel' | 'question' |
    'attempt'. Only 'attempt' counts toward the skip ceiling.

    Deliberately deterministic rather than another LLM call: this runs on every
    collecting turn, and a keyword miss just falls through to 'attempt', which is
    the old behaviour -- no worse than before, and no extra latency on the flow.
    """
    import re
    tokens = set(re.findall(r"[\w஀-௿]+", message.strip().lower()))
    if not tokens:
        return "attempt"
    # Cancel first: a withdrawal outranks everything else in the message.
    if tokens & _CANCEL_WORDS:
        return "cancel"
    # Greeting only when that is essentially the whole message -- "hi, my name is
    # Prem" carries a real answer and must not be treated as a bare greeting.
    if tokens <= _GREETING_WORDS:
        return "greeting"
    if "?" in message or (tokens & _QUESTION_WORDS):
        return "question"
    return "attempt"


def pending_fields(fields: list[dict], collected_data: dict, skipped=()) -> list[dict]:
    """Fields still needed: neither collected nor given up on. Ordered by config, so
    the collector always asks for the first outstanding one."""
    skipped_set = set(skipped)
    return [
        f for f in fields
        if not collected_data.get(f["key"]) and f["key"] not in skipped_set
    ]


_EXTRACTION_SYSTEM_PROMPT = """You extract structured field values from one customer chat
message. You are given a list of fields the business needs and the values already
collected from earlier turns. Read the new message and return ONLY the fields you can
confidently find IN THIS MESSAGE, as flat JSON: {"field_key": "value", ...}.

Rules:
- Only include a key if this message actually contains that value.
- Never guess or invent a value that isn't stated.
- Do not repeat values that weren't in this message, even if already collected.
- If this message contains none of the requested fields, return {}.
- JSON only, no other text."""


async def extract_fields(message: str, fields: list[dict], collected_data: dict, tenant_id: str) -> dict:
    """Never drops already-collected data: the LLM only ever contributes additions
    for THIS message, which are merged on top of (never replacing) collected_data."""
    field_list = "\n".join(f"- {f['key']}: {f['label']} ({f['type']})" for f in fields)
    already = ", ".join(f"{k}={v}" for k, v in collected_data.items()) or "(none yet)"
    user_prompt = (
        f"Fields needed:\n{field_list}\n\n"
        f"Already collected: {already}\n\n"
        f"New message: {message}"
    )
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=300,
            tenant_id=tenant_id,
            purpose="expert_handoff_extraction",
        )
    except Exception as e:
        logger.warning(f"Intake extraction failed, keeping existing collected_data: {e}")
        return dict(collected_data)

    valid_keys = {f["key"] for f in fields}
    new_values = {k: v for k, v in data.items() if k in valid_keys and v}
    return {**collected_data, **new_values}


def normalize_packages(config: dict) -> list[dict]:
    """The tenant's packages, with the pre-packages single `amount_paise` config
    auto-migrated to one 'standard' package so an existing tenant keeps working
    without touching their settings."""
    packages = config.get("packages") or []
    if packages:
        return [dict(p) for p in packages]
    legacy_fee = config.get("amount_paise") or 0
    if legacy_fee > 0:
        return [{
            "key": "standard",
            "name": "Consultation",
            "amount_paise": legacy_fee,
            "description": "",
        }]
    return []


def _rupees(amount_paise: int) -> str:
    """Whole rupees when the amount is exact, two decimals otherwise."""
    if amount_paise % 100 == 0:
        return f"₹{amount_paise // 100}"
    return f"₹{amount_paise / 100:.2f}"


def package_list_block(packages: list[dict]) -> str:
    """Rendered in Python, never by the LLM: these are prices the customer will
    be held to, and a hallucinated figure is a real liability. The surrounding
    intro/question are composed in the tenant's language by intake_copy."""
    lines = []
    for p in packages:
        line = f"• {p['name']} — {_rupees(p['amount_paise'])}"
        if p.get("description"):
            line += f"\n  {p['description']}"
        lines.append(line)
    return "\n".join(lines)


def package_list_message(packages: list[dict], service_noun: str) -> str:
    """English-only wrapper, kept for callers outside route_intake."""
    return (
        f"Here are our {service_noun} options:\n\n"
        + package_list_block(packages)
        + "\n\nWhich one would you like?"
    )


_PACKAGE_MATCH_SYSTEM_PROMPT = """You match a customer's reply to one of a fixed list of
packages. You are given the packages (key and name) and the customer's message.

Respond with JSON only: {"key": "<the matching package key>"} or {"key": null} if the
message does not clearly indicate one of the listed packages.

Rules:
- The key MUST be one of the keys given. Never invent a key.
- If the customer is ambiguous or asking a question rather than choosing, return null.
- JSON only, no other text."""


async def match_package(message: str, packages: list[dict], tenant_id: str) -> dict | None:
    """Match a lead's free-text reply to one configured package. Exact name or key
    matches short-circuit the LLM. Fails closed: any error or unknown key returns
    None so the caller re-asks rather than charging the wrong amount."""
    if not packages:
        return None

    cleaned = message.strip().lower()
    for p in packages:
        if cleaned == p["name"].strip().lower() or cleaned == p["key"].strip().lower():
            return dict(p)

    package_list = "\n".join(f"- {p['key']}: {p['name']}" for p in packages)
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_PACKAGE_MATCH_SYSTEM_PROMPT,
            user_prompt=f"Packages:\n{package_list}\n\nCustomer message: {message}",
            temperature=0.0,
            max_tokens=50,
            tenant_id=tenant_id,
            purpose="intake_package_match",
        )
    except Exception as e:
        logger.warning(f"Intake package match failed, treating as no-match: {e}")
        return None

    key = data.get("key")
    for p in packages:
        if key == p["key"]:
            return dict(p)
    return None


_ACTIVE_STATUSES = (
    "offer_pending", "awaiting_package_choice", "collecting",
    "awaiting_confirmation", "awaiting_payment", "paid",
)

_PACKAGE_CHANGEABLE_STATUSES = (
    "awaiting_package_choice", "collecting", "awaiting_confirmation", "awaiting_payment",
)


def _get_active_session(lead_id: str, tenant_id: str, db) -> dict | None:
    result = (
        db.table("intake_sessions")
        .select("*")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .neq("status", "resolved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    active = [r for r in rows if r["status"] in _ACTIVE_STATUSES]
    return active[0] if active else None


def _create_session(lead_id: str, tenant_id: str, db) -> dict:
    result = (
        db.table("intake_sessions")
        .insert({"lead_id": lead_id, "tenant_id": tenant_id, "status": "offer_pending", "collected_data": {}})
        .execute()
    )
    return result.data[0]


def _update_session(session_id: str, patch: dict, db) -> None:
    db.table("intake_sessions").update(patch).eq("id", session_id).execute()


def _package_patch(package: dict) -> dict:
    """Snapshot the chosen package onto the session row. Repricing or renaming a
    package later must not rewrite what a past lead was actually offered."""
    return {
        "package_key": package["key"],
        "package_name": package["name"],
        "package_amount_paise": package["amount_paise"],
    }


async def _send_and_log(phone: str, text: str, tenant_id: str, lead_id: str, db) -> None:
    from app.services.ai_reply import send_whatsapp
    mid = await send_whatsapp(phone, text, tenant_id=tenant_id)
    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": text,
        "is_ai_generated": True,
        "meta_message_id": mid,
        "reply_source": "expert_handoff",
    }).execute()


# Roman-script Tamil is deliberately included: the moment the offer message is
# written in Tanglish, leads answer in Tanglish ("seri", "aama"), and anything
# unmatched here is treated as a refusal that cancels the session and loses the
# sale. Spellings vary a lot in real chat, so the common ones are all listed.
# Deliberately excluded: bare verbs like "pannunga"/"venum", which appear just as
# often in requests that are not a yes ("call pannunga").
_AFFIRMATIVE_RE_WORDS = frozenset({
    # English
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "okey", "correct", "right", "fine",
    # Tanglish / romanized Tamil
    "seri", "sari", "seriyaa", "seriya", "aama", "aamaa", "aamam", "ama", "amaam", "nalladhu",
    # Tamil script
    "ஆம்", "சரி", "ஆமாம்",
    # Hindi
    "हाँ", "ठीक", "haan", "theek", "thik",
})


def _is_affirmative(message: str) -> bool:
    import re
    tokens = set(re.findall(r"[\w஀-௿ऀ-ॿ]+", message.strip().lower()))
    return bool(tokens & _AFFIRMATIVE_RE_WORDS)


def is_brain_led(tenant_id: str, phone: str) -> bool:
    """Thin indirection so this module never imports intake_brain at module level --
    intake_brain imports its state primitives from here, and the cycle would be real."""
    from app.services.intake_brain import is_brain_led as _gate
    return _gate(tenant_id, phone)


def _summary_block(fields: list[dict], collected_data: dict, skipped=()) -> str:
    """The collected values, rendered in Python. Never LLM-written -- these are the
    details the expert works from, and a rewritten value is a wrong reading. A field
    the lead could not answer is marked distinctly from one still blank."""
    skipped_set = set(skipped)
    lines = []
    for f in fields:
        value = collected_data.get(f["key"])
        if not value:
            value = "— (not provided)" if f["key"] in skipped_set else "—"
        lines.append(f"{f['label']}: {value}")
    return "\n".join(lines)


async def route_intake(lead_id: str, tenant_id: str, phone: str, body: str, db=None) -> bool:
    """Webhook-level routing for the intake session. Returns True if the
    inbound message was consumed (caller must skip generate_reply for this turn)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    if not body:
        return False

    try:
        config = get_intake_config(tenant_id, db=db)
        if not config.get("enabled"):
            return False

        session = _get_active_session(lead_id, tenant_id, db)

        # A paid customer whose expert has already answered is in follow-up mode:
        # everything they say goes to that same expert and the AI stays out of it.
        # Ahead of the brain-led check on purpose — this applies in both modes.
        if session is not None and session.get("status") == "paid":
            if await forward_followup_to_astrologer(session, lead_id, tenant_id, phone, body, db):
                return True

        # Brain-led leads (see intake_brain.py): once the offer is out, this state
        # machine composes and sends nothing. Reporting the turn as unconsumed hands
        # it to generate_reply, which drives the rest of the sign-up through tools.
        # The trigger classifier and the tenant's own offer copy below are identical
        # in both modes, so they stay here.
        if session is not None and is_brain_led(tenant_id, phone):
            logger.info(f"Brain-led intake: yielding turn for lead {lead_id} (session {session['id']})")
            return False

        # Resolved once per turn and shared by every line this turn may send.
        language_mode = resolve_language_mode(lead_id, tenant_id, db)
        thread, knowledge = await gather_context(db, lead_id, tenant_id, body)
        brain_prompt = collector_identity(db, lead_id, tenant_id, body)

        async def _say(purpose: str, collected: dict | None = None, **kwargs) -> None:
            text = await compose_line(
                purpose,
                tenant_id=tenant_id,
                language_mode=language_mode,
                customer_message=body,
                thread=thread,
                knowledge=knowledge,
                brain_prompt=brain_prompt,
                collected=collected if collected is not None else (session.get("collected_data") or {}),
                **kwargs,
            )
            await _send_and_log(phone, text, tenant_id, lead_id, db)

        async def _say_summary(collected: dict, skipped=()) -> None:
            fields = await localized_fields(config["fields"], language_mode, tenant_id)
            text = await compose_wrapped(
                "summary",
                tenant_id=tenant_id,
                language_mode=language_mode,
                customer_message=body,
                block=_summary_block(fields, collected, skipped),
                thread=thread,
            )
            await _send_and_log(phone, text, tenant_id, lead_id, db)

        if session is None:
            matched = await detect_intake_intent(body, config["trigger_description"], tenant_id)
            if not matched:
                return False
            new_session = _create_session(lead_id, tenant_id, db)
            await _send_and_log(phone, config["offer_message"], tenant_id, lead_id, db)
            _update_session(new_session["id"], {"trigger_reason": body[:500]}, db)
            return True

        status = session["status"]

        if status == "offer_pending":
            if not _is_affirmative(body):
                _update_session(session["id"], {"status": "cancelled"}, db)
                return False
            packages = normalize_packages(config)
            if len(packages) == 1:
                # Single package: nothing to choose, snapshot it and go straight
                # to field collection — same as the pre-packages flow, just with
                # the package recorded on the row.
                collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
                missing = missing_field_labels(config["fields"], collected)
                patch = _package_patch(packages[0]) | {"collected_data": collected, "field_schema": config["fields"]}
                if missing:
                    _update_session(session["id"], patch | {"status": "collecting"}, db)
                    await _say("ask_field", field_label=missing[0], collected=collected)
                else:
                    _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                    await _say_summary(collected)
                return True
            if not packages:
                logger.error(f"Intake session {session['id']} has no packages configured despite being enabled")
                await _say("no_packages")
                return True
            _update_session(session["id"], {"status": "awaiting_package_choice"}, db)
            await _send_and_log(
                phone,
                await compose_wrapped(
                    "packages",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    block=package_list_block(packages),
                    thread=thread,
                ),
                tenant_id, lead_id, db,
            )
            return True

        if status == "awaiting_package_choice":
            packages = normalize_packages(config)
            chosen = await match_package(body, packages, tenant_id)
            if chosen is None:
                intro = await compose_line(
                    "package_reask",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    thread=thread,
                    knowledge=knowledge,
                )
                await _send_and_log(
                    phone,
                    f"{intro}\n\n{package_list_block(packages)}",
                    tenant_id, lead_id, db,
                )
                return True
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            patch = _package_patch(chosen) | {
                "collected_data": collected,
                "field_schema": config["fields"],
            }
            if missing:
                _update_session(session["id"], patch | {"status": "collecting"}, db)
                await _say("ask_field", field_label=missing[0], collected=collected)
            else:
                _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                await _say_summary(collected)
            return True

        if status == "collecting":
            before = session.get("collected_data") or {}
            collected = await extract_fields(body, config["fields"], before, tenant_id)
            attempts = dict(session.get("ask_attempts") or {})
            skipped = list(session.get("skipped_fields") or [])
            pending = pending_fields(config["fields"], collected, skipped)

            purpose = "ask_field"
            given_up_label: str | None = None
            if pending and collected == before:
                # This message added nothing -- but that does not make it a failed
                # attempt at the pending field. Only a genuine try counts toward the
                # skip ceiling; a greeting or a question is answered on its own terms
                # and leaves the counter alone, and a withdrawal ends the flow.
                kind = classify_non_answer(body)
                if kind == "cancel":
                    _update_session(session["id"], {"status": "cancelled"}, db)
                    logger.info(f"Intake session {session['id']} cancelled by lead during collection")
                    return False
                if kind == "greeting":
                    purpose = "greeting_reask"
                elif kind == "question":
                    purpose = "reask_field"
                else:
                    # After _MAX_FIELD_ATTEMPTS give up on the field rather than asking
                    # a third time -- live evidence 2026-08-12: the same question went
                    # out three times to a lead who had twice said they did not know it.
                    key = pending[0]["key"]
                    attempts[key] = attempts.get(key, 0) + 1
                    if attempts[key] >= _MAX_FIELD_ATTEMPTS:
                        given_up_label = pending[0]["label"]
                        skipped.append(key)
                        pending = pending_fields(config["fields"], collected, skipped)
                        purpose = "skip_field"
                    else:
                        purpose = "reask_field"

            patch = {
                "collected_data": collected,
                "ask_attempts": attempts,
                "skipped_fields": skipped,
            }
            if pending:
                _update_session(session["id"], patch, db)
                if purpose == "skip_field":
                    await _say(
                        "skip_field",
                        field_label=given_up_label,
                        next_field_label=pending[0]["label"],
                        collected=collected,
                    )
                else:
                    await _say(purpose, field_label=pending[0]["label"], collected=collected)
            else:
                _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                await _say_summary(collected, skipped)
            return True

        if status == "awaiting_confirmation":
            if not _is_affirmative(body):
                # Not a yes, but not necessarily unrelated either -- the lead may be
                # correcting or supplying a field they see is wrong or missing on the
                # summary. Live evidence 2026-08-13: "Time of birth is 6:30 am" sent
                # right after a summary that showed that field as not provided. Try
                # extraction before giving up the turn; only a message that adds
                # nothing usable is released to the AI.
                before = session.get("collected_data") or {}
                skipped = list(session.get("skipped_fields") or [])
                updated = await extract_fields(body, config["fields"], before, tenant_id)
                changed = [k for k, v in updated.items() if v and v != before.get(k)]
                if not changed:
                    return False
                skipped = [k for k in skipped if k not in changed]
                _update_session(
                    session["id"],
                    {"collected_data": updated, "skipped_fields": skipped},
                    db,
                )
                await _say_summary(updated, skipped)
                return True
            ref = f"IN-{uuid.uuid4().hex[:8].upper()}"
            collected = session.get("collected_data") or {}
            # Razorpay needs a string here, so an unidentifiable customer falls back
            # to their phone -- always real, always that person.
            customer_name = resolve_customer_name(collected, config["fields"]) or phone
            amount_paise = session.get("package_amount_paise")
            if not amount_paise:
                logger.error(f"Intake session {session['id']} reached payment with no package amount")
                await _say("payment_delay")
                return True
            service_noun = config["service_noun"].capitalize()
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
                _update_session(session["id"], {
                    "status": "awaiting_payment",
                    "amount_paise": amount_paise,
                    "payment_link": link["payment_link_url"],
                }, db)
                intro = await compose_line(
                    "payment_intro",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    thread=thread,
                    knowledge=knowledge,
                )
                await _send_and_log(
                    phone,
                    f"{intro}\n{link['payment_link_url']}",
                    tenant_id, lead_id, db,
                )
            except Exception as e:
                logger.error(f"Intake payment link creation failed for session {session['id']}: {e}")
                await _say("payment_delay")
            return True

        # awaiting_payment: nothing to do here, wait for the Razorpay webhook.
        return False
    except Exception as e:
        logger.error(f"route_intake failed for lead {lead_id}: {e}")
        return False


_FOLLOWUP_REF_RE = re.compile(r"^(?P<sid>.+?)::f\d+$")


def session_ref_to_id(external_ref: str) -> str | None:
    """Resolve a bridge external_ref to its session uuid, or None.

    A follow-up's ref is ``{session_id}::f{n}`` (see astro_bridge.push_followup);
    a consultation's ref is the bare session id. The column is uuid-typed, so a
    non-uuid must never reach the DB — PostgREST rejects it with an APIError
    that would surface as a 500 on a public route instead of the intended 401."""
    ref = str(external_ref or "").strip()
    m = _FOLLOWUP_REF_RE.match(ref)
    if m:
        ref = m.group("sid")
    try:
        return str(uuid.UUID(ref))
    except (ValueError, AttributeError, TypeError):
        return None


_FOLLOWUP_CLAIM_ATTEMPTS = 3


async def forward_followup_to_astrologer(session: dict, lead_id: str, tenant_id: str, phone: str, body: str, db) -> bool:
    """Hand a paid customer's next message to the astrologer who already answered
    them, and tell the customer it landed. Returns True when the message was
    consumed, meaning the AI must not also reply to it.

    Only fires once the expert has actually answered: before that the lead is in
    the paid-and-waiting state, where ai_reply's _intake_paid_prompt_block keeps
    the AI reassuring them rather than silent (see the 2026-08-07..11 incident in
    .agents/context/subsystem-notes.md — muting a paid lead is what we are NOT
    doing here). Every failure path returns False for the same reason: an
    undelivered follow-up is bad, an undelivered follow-up plus total silence is
    what actually cost us before.
    """
    from app.services import astro_bridge

    if session.get("astro_question_id") is None:
        # The consultation never reached the bridge; astro-push-reconcile still
        # owes it a push. A follow-up would have no thread to join.
        return False
    if session.get("astro_last_reply_id") is None:
        return False

    session_id = session["id"]

    # n must be monotonic per session: Django keys idempotency off "{sid}::f{n}"
    # and silently swallows a repeat. Claim it with a compare-and-set so two
    # messages landing together can't both take the same number.
    n = None
    current = int(session.get("astro_followup_count") or 0)
    for _ in range(_FOLLOWUP_CLAIM_ATTEMPTS):
        claimed = (
            db.table("intake_sessions")
            .update({"astro_followup_count": current + 1})
            .eq("id", session_id)
            .eq("tenant_id", tenant_id)
            .eq("astro_followup_count", current)
            .execute()
        )
        if claimed and claimed.data:
            n = current + 1
            break
        fresh = (
            db.table("intake_sessions")
            .select("astro_followup_count")
            .eq("id", session_id)
            .eq("tenant_id", tenant_id)
            .maybe_single()
            .execute()
        )
        row = (fresh.data if fresh else None) or {}
        current = int(row.get("astro_followup_count") or 0)
    if n is None:
        logger.error(f"Intake follow-up: could not claim a number for session {session_id} — yielding to the AI")
        return False

    lead_row = (
        db.table("leads")
        .select("id,name,phone")
        .eq("id", lead_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {"phone": phone}

    pushed = None
    try:
        pushed = await astro_bridge.push_followup(session, lead, body, tenant_id, n)
    except Exception as e:
        logger.error(f"Intake follow-up push raised for session {session_id}: {e}")

    if not pushed:
        # Give the number back so the next message can retry it, rather than
        # burning n and leaving a permanent gap in the astrologer's thread.
        try:
            (
                db.table("intake_sessions")
                .update({"astro_followup_count": n - 1})
                .eq("id", session_id)
                .eq("tenant_id", tenant_id)
                .eq("astro_followup_count", n)
                .execute()
            )
        except Exception as e:
            logger.warning(f"Intake follow-up counter rollback failed for session {session_id}: {e}")
        try:
            notify_pool(
                tenant_id,
                "intake_paid",
                "Follow-up did not reach the expert",
                f"A paid customer ({phone}) sent a follow-up that could not be delivered to the expert platform.",
                db=db,
            )
        except Exception as e:
            logger.warning(f"Intake follow-up notify_pool failed for session {session_id}: {e}")
        return False

    language_mode = resolve_language_mode(lead_id, tenant_id, db)
    thread, knowledge = await gather_context(db, lead_id, tenant_id, body)
    receipt = await compose_line(
        "followup_sent",
        tenant_id=tenant_id,
        language_mode=language_mode,
        customer_message=body,
        thread=thread,
        knowledge=knowledge,
        brain_prompt=collector_identity(db, lead_id, tenant_id, body),
    )
    try:
        await _send_and_log(phone, receipt, tenant_id, lead_id, db)
    except Exception as e:
        # The expert has the question either way; failing to send the receipt is
        # not a reason to also let the AI answer it.
        logger.error(f"Intake follow-up receipt send failed for session {session_id}: {e}")
    logger.info(f"Intake follow-up #{n} forwarded to the expert for session {session_id}")
    return True


def get_session_tenant_id(session_id: str, db=None) -> str | None:
    """Look up which tenant owns a session, so the webhook route can verify the
    Razorpay signature against that tenant's own webhook secret rather than the
    default tenant's. Safe to call before the signature is verified: an attacker
    supplying a forged session_id just gets a lookup miss or another tenant's
    id, and the subsequent HMAC check against that tenant's real secret still
    fails without it. Accepts a follow-up ref ("{sid}::f{n}") and treats any
    malformed/non-uuid ref as a plain miss, never an exception."""
    resolved = session_ref_to_id(session_id)
    if not resolved:
        return None
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    try:
        row = (
            db.table("intake_sessions")
            .select("tenant_id")
            .eq("id", resolved)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.warning(f"Session tenant lookup failed for ref {session_id!r}: {e}")
        return None
    if not row or not row.data:
        return None
    return row.data.get("tenant_id")


def confirm_intake_payment(
    session_id: str,
    razorpay_payment_id: str,
    amount_paid_paise: int | None = None,
    db=None,
) -> dict | None:
    """Mark a session paid. The AI stays live for the lead (see
    get_paid_unresolved_session / _intake_paid_prompt_block in
    ai_reply.py) so a lead asking "when will the expert contact me" isn't met
    with silence while waiting for staff to pick up the notification. Returns
    {phone, tenant_id, lead_id, customer_name, session, lead} on success, None if
    the session doesn't exist or was already paid (idempotent — Razorpay may
    retry webhooks, and two retries may land concurrently). ``session`` and
    ``lead`` are what the AstroTamil bridge push needs; see routes/intake.py."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    from datetime import datetime, timezone

    existing = (
        db.table("intake_sessions")
        .select("id,status,lead_id,tenant_id,collected_data,field_schema,"
                "package_key,package_name,package_amount_paise,trigger_reason")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data or existing.data.get("status") == "paid":
        return None

    session = existing.data
    now_iso = datetime.now(timezone.utc).isoformat()
    expected = session.get("package_amount_paise")
    charged = amount_paid_paise if amount_paid_paise is not None else expected
    # The status filter is the whole point: it turns the read-then-write above into
    # a single conditional UPDATE, so of two concurrent Razorpay retries exactly one
    # gets a row back and the other cannot bill/consult the lead twice. Filtering on
    # "not already paid" rather than "is awaiting_payment" keeps the pre-bridge
    # behaviour: money arriving against a cancelled or resolved session still
    # surfaces to staff instead of vanishing.
    claimed = (
        db.table("intake_sessions")
        .update({
            "status": "paid",
            "razorpay_payment_id": razorpay_payment_id,
            "paid_at": now_iso,
            "amount_paise": charged,
            # A lead can pay a link that was just superseded by a package change.
            # Record what actually arrived and flag the gap for staff rather than
            # trusting config.
            "amount_mismatch": bool(expected and charged and expected != charged),
        })
        .eq("id", session_id)
        .neq("status", "paid")
        .execute()
    )
    if not claimed or not claimed.data:
        logger.info(f"Intake session {session_id} already claimed by a concurrent confirm — skipping")
        return None

    session = {**session, **(claimed.data[0] or {})}
    lead_id = session["lead_id"]
    tenant_id = session["tenant_id"]

    lead_row = (
        db.table("leads")
        .select("id,phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = resolve_customer_name(
        session.get("collected_data"),
        session.get("field_schema") or get_intake_config(tenant_id, db=db).get("fields"),
        lead.get("name"),
    )
    adopt_lead_name(db, lead_id, tenant_id, customer_name if not lead.get("name") else None)

    try:
        notify_pool(
            tenant_id,
            "intake_paid",
            "New paid consultation",
            (
                f"Lead '{customer_name}' paid for a consultation — check Intake."
                if customer_name
                else "A lead paid for a consultation — check Intake."
            ),
            db=db,
        )
    except Exception as e:
        logger.warning(f"intake_paid notify_pool failed for session {session_id}: {e}")

    return {
        "phone": phone,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "customer_name": customer_name,
        "session": session,
        "lead": lead,
    }


def get_paid_unresolved_session(lead_id: str, tenant_id: str, db=None) -> dict | None:
    """The lead's most recent paid-but-not-yet-resolved session, if any. Used by
    ai_reply.py to keep the AI reassuring the lead instead of going silent, and
    by route_intake/_get_active_session to stop a lead being offered a
    second paid consultation while the first is still unresolved."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    result = (
        db.table("intake_sessions")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "paid")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


_IN_PROGRESS_STATUSES = frozenset({
    "awaiting_package_choice", "collecting", "awaiting_confirmation", "awaiting_payment",
})


def get_in_progress_session(lead_id: str, tenant_id: str, db=None) -> dict | None:
    """The lead's most recent intake session that is actively in motion -- past the
    initial offer, not yet paid or resolved. Used by ai_reply.py so the AI does not
    derail a near-closed sale. Live evidence 2026-08-13: a lead corrected a field at
    awaiting_confirmation instead of saying yes; route_intake correctly handed the
    turn to the AI (that's not a yes), but with zero context the AI answered from the
    business's general knowledge base and told the lead to download the app and
    resubmit there -- abandoning a ₹29 payment one message from completing."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    result = (
        db.table("intake_sessions")
        .select("id,status")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    row = rows[0]
    return row if row.get("status") in _IN_PROGRESS_STATUSES else None


def resolve_intake_session(session_id: str, tenant_id: str, db=None) -> bool:
    """Staff marks a paid intake session as handled — the AI reassurance context
    (get_paid_unresolved_session) stops applying and the session leaves the
    Intake "Paid" list. Only transitions from 'paid'; returns False if
    the session doesn't exist, belongs to another tenant, or isn't paid yet."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    from datetime import datetime, timezone

    result = (
        db.table("intake_sessions")
        .update({"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "paid")
        .execute()
    )
    return bool(result.data)


async def change_session_package(session_id: str, tenant_id: str, package_key: str, db=None) -> dict | None:
    """Re-point an unpaid session at a different package and clear the stale
    payment link. Returns None if the session is missing, already paid, or the
    key is not configured — the caller turns that into a 404/400."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    row = (
        db.table("intake_sessions")
        .select("id,tenant_id,lead_id,status,collected_data,package_key")
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    session = (row.data if row else None) or None
    if not session or session["status"] not in _PACKAGE_CHANGEABLE_STATUSES:
        return None

    config = get_intake_config(tenant_id, db=db)
    chosen = next((p for p in normalize_packages(config) if p["key"] == package_key), None)
    if chosen is None:
        return None

    # The old Razorpay link stays live until Razorpay processes the cancel, so
    # confirm_intake_payment records the amount that actually arrives rather
    # than assuming this one. See D16.
    patch = _package_patch(chosen) | {"payment_link": None, "amount_paise": None}
    db.table("intake_sessions").update(patch).eq("id", session_id).eq("tenant_id", tenant_id).execute()
    return {**session, **patch}


# --------------------------------------------------------------------------
# AstroTamil bridge: outbound push of a paid session, and delivery of the
# astrologer's reply back into the lead's WhatsApp thread.
# The wire contract (paths, payload keys, header names, external_ref format)
# is shared with the astrobackmatrimony Django app — see
# ConsultationAPIEndpoints.md. Do not rename anything that crosses the wire.
# --------------------------------------------------------------------------

_WA_SESSION_WINDOW_HOURS = 24

_AUDIO_MIMES = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "amr": "audio/amr",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
}


def record_astro_bridge_ids(session_id: str, tenant_id: str, bridge_response: dict, db=None) -> None:
    """Persist the ids Django created for a pushed session, so its reply callback maps back here."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    patch = {
        "astro_question_id": (bridge_response or {}).get("question_id"),
        "astro_horoscope_id": (bridge_response or {}).get("horoscope_id"),
        "astro_user_id": (bridge_response or {}).get("astro_user_id"),
    }
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        logger.warning(f"Astro bridge returned no ids for session {session_id} — nothing to persist")
        return
    (
        db.table("intake_sessions")
        .update(patch)
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )


async def reconcile_pending_astro_pushes(db=None) -> int:
    """Re-drive the Django consultation push for paid sessions it never reached.

    The confirm-time push is best-effort: if Django is down for the one webhook
    that flips a session to paid, the paid transition is idempotent and never
    re-fires, so without this sweep the customer has paid, been told "our expert
    will be in touch", and no astrologer ever sees the consultation. Django's
    side is idempotent on the session id (UNIQUE order id), so re-driving is
    always safe. Window: 3 days — older stuck sessions need a human anyway."""
    from datetime import datetime, timedelta, timezone

    from app.services import astro_bridge

    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    try:
        rows = (
            db.table("intake_sessions")
            .select("id,tenant_id,lead_id,collected_data,trigger_reason,amount_paise")
            .eq("status", "paid")
            .is_("astro_question_id", "null")
            .gte("created_at", cutoff)
            .limit(20)
            .execute()
        )
    except Exception as e:
        logger.error(f"Astro push reconcile query failed: {e}")
        return 0

    pushed = 0
    for session in rows.data or []:
        tenant_id = session.get("tenant_id")
        try:
            lead_row = (
                db.table("leads")
                .select("id,name,phone")
                .eq("id", session.get("lead_id"))
                .eq("tenant_id", tenant_id)
                .maybe_single()
                .execute()
            )
            lead = (lead_row.data if lead_row else None) or {}
            result = await astro_bridge.push_consultation(session, lead, tenant_id)
            if result:
                record_astro_bridge_ids(session["id"], tenant_id, result, db=db)
                pushed += 1
                logger.info(f"Astro push reconciled for session {session['id']} (tenant {tenant_id})")
        except Exception as e:
            logger.error(f"Astro push reconcile failed for session {session.get('id')}: {e}")
    return pushed


def _within_whatsapp_window(last_inbound_at) -> bool:
    from datetime import datetime, timedelta, timezone

    if not last_inbound_at:
        return False
    try:
        last = datetime.fromisoformat(str(last_inbound_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last <= timedelta(hours=_WA_SESSION_WINDOW_HOURS)


def _astro_phone_number_id(tenant_id: str, db) -> str | None:
    """The tenant's inbound WhatsApp number, so the astrologer's reply lands in the lead's existing thread."""
    try:
        rows = (
            db.table("phone_numbers")
            .select("meta_phone_number_id")
            .eq("tenant_id", tenant_id)
            .eq("role", "primary")
            .limit(1)
            .execute()
        )
        return ((rows.data or [{}])[0] or {}).get("meta_phone_number_id")
    except Exception as e:
        logger.warning(f"Could not resolve primary phone_number_id for tenant {tenant_id}: {e}")
        return None


def _media_mime(url: str, wa_type: str) -> tuple[str, str]:
    found = re.search(r"\.([a-z0-9]{2,5})(?:\?|$)", str(url or "").lower())
    ext = found.group(1) if found else ""
    if wa_type == "image":
        return ("image/png", "reply.png") if ext == "png" else ("image/jpeg", "reply.jpg")
    return _AUDIO_MIMES.get(ext, "audio/mpeg"), f"reply.{ext or 'mp3'}"


def _log_astro_message(db, lead_id: str, tenant_id: str, content: str, mid: str | None) -> None:
    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": content,
        "is_ai_generated": False,
        "meta_message_id": mid,
        # Constrained value from migration 173; the feature was renamed to
        # "intake" but the stored reply_source was deliberately left alone.
        "reply_source": "expert_handoff",
    }).execute()


async def _send_astro_media(phone: str, url: str, wa_type: str, tenant_id: str, phone_number_id: str | None) -> str | None:
    import httpx

    from app.services.meta_cloud import send_media_message, upload_media_to_meta

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()

    mime_type, filename = _media_mime(url, wa_type)
    media_id = await upload_media_to_meta(
        file_bytes=resp.content,
        mime_type=mime_type,
        filename=filename,
        tenant_id=tenant_id,
        phone_number_id=phone_number_id,
    )
    data = await send_media_message(
        to_number=phone,
        media_id=media_id,
        wa_type=wa_type,
        tenant_id=tenant_id,
        phone_number_id=phone_number_id,
    )
    return (data.get("messages") or [{}])[0].get("id")


async def deliver_astro_reply(payload: dict, tenant_id: str, db=None) -> dict:
    """Deliver one astrologer reply from the Django bridge to the lead's WhatsApp thread."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    from app.services.ai_reply import send_whatsapp

    external_ref = str(payload.get("external_ref") or "")
    session_id = session_ref_to_id(external_ref)
    if not session_id:
        logger.warning(f"Astro reply with malformed external_ref {external_ref!r} (tenant {tenant_id})")
        return {"ok": True, "delivered": [], "reason": "unknown_session"}
    try:
        reply_id = int(payload.get("reply_id"))
    except (TypeError, ValueError):
        logger.error(f"Astro reply for session {external_ref} has no usable reply_id — cannot dedupe, dropping")
        return {"ok": True, "delivered": [], "reason": "missing_reply_id"}

    row = (
        db.table("intake_sessions")
        .select("id,lead_id,tenant_id,astro_last_reply_id")
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    session = (row.data if row else None) or {}
    if not session:
        logger.warning(f"Astro reply for unknown session {external_ref} (tenant {tenant_id})")
        return {"ok": True, "delivered": [], "reason": "unknown_session"}

    prior_reply_id = session.get("astro_last_reply_id")

    # Claim the reply id before sending, not after: a Django retry that overlaps
    # the first delivery must lose here rather than send the astrologer's answer
    # to the customer twice. Monotonic (.lt) rather than mere inequality, so a
    # replayed OLDER reply arriving after a newer one is also a duplicate.
    claimed = (
        db.table("intake_sessions")
        .update({"astro_last_reply_id": reply_id})
        .eq("id", session_id)
        .eq("tenant_id", tenant_id)
        .or_(f"astro_last_reply_id.is.null,astro_last_reply_id.lt.{reply_id}")
        .execute()
    )
    if not claimed or not claimed.data:
        logger.info(f"Astro reply {reply_id} for session {external_ref} already delivered — ignoring duplicate")
        return {"ok": True, "duplicate": True}

    lead_id = session.get("lead_id")
    lead_row = (
        db.table("leads")
        .select("id,phone,last_inbound_at")
        .eq("id", lead_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone") or ""
    if not phone:
        logger.error(f"Astro reply {reply_id} for session {external_ref} undeliverable: lead {lead_id} has no phone")
        return {"ok": True, "delivered": [], "reason": "no_phone"}

    if not _within_whatsapp_window(lead.get("last_inbound_at")):
        logger.error(
            f"Astro reply {reply_id} for session {external_ref} NOT delivered: the lead's 24h WhatsApp "
            f"window closed (last_inbound_at={lead.get('last_inbound_at')}). The astrologer believes "
            f"the customer has been answered — they have not."
        )
        try:
            notify_pool(
                tenant_id,
                "intake_paid",
                "Astrologer reply could not be delivered",
                f"The 24h WhatsApp window for this consultation has closed — reach {phone} another way.",
                db=db,
            )
        except Exception as e:
            logger.warning(f"Astro reply window notify_pool failed for session {external_ref}: {e}")
        return {"ok": True, "delivered": [], "outside_24h_window": True}

    phone_number_id = _astro_phone_number_id(tenant_id, db)
    delivered: list[str] = []
    failed: list[str] = []

    text = str(payload.get("reply_text") or "").strip()
    if text:
        try:
            mid = await send_whatsapp(phone, text, tenant_id=tenant_id, phone_number_id=phone_number_id)
        except Exception as e:
            logger.error(f"Astro reply {reply_id} text send failed for session {external_ref}: {e}")
            mid = None
        if mid:
            _log_astro_message(db, lead_id, tenant_id, text, mid)
            delivered.append("text")
        else:
            failed.append("text")

    for part, url, wa_type in (
        ("image", payload.get("reply_image_url"), "image"),
        ("voice", payload.get("reply_voice_url"), "audio"),
    ):
        if not url:
            continue
        try:
            mid = await _send_astro_media(phone, str(url), wa_type, tenant_id, phone_number_id)
            _log_astro_message(db, lead_id, tenant_id, str(url), mid)
            delivered.append(part)
        except Exception as e:
            logger.error(f"Astro reply {reply_id} {part} send failed for session {external_ref}: {e}")
            failed.append(part)

    if failed and not delivered:
        # Total in-window failure: every part the astrologer sent was attempted
        # and none went out. Returning bare success here would strand the reply
        # forever — the claim above blocks any retry, Django never retries on
        # 2xx, and the astrologer's UI already shows it as sent. Roll the claim
        # back so a re-push can re-drive it, and surface it to staff.
        logger.error(f"Astro reply {reply_id} for session {external_ref} delivered nothing (failed={failed})")
        try:
            (
                db.table("intake_sessions")
                .update({"astro_last_reply_id": prior_reply_id})
                .eq("id", session_id)
                .eq("tenant_id", tenant_id)
                .eq("astro_last_reply_id", reply_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"Astro reply {reply_id} claim rollback failed for session {external_ref}: {e}")
        try:
            notify_pool(
                tenant_id,
                "intake_paid",
                "Astrologer reply could not be delivered",
                f"WhatsApp delivery to {phone} failed for a paid consultation "
                f"(parts failed: {', '.join(failed)}) — reach the customer another way.",
                db=db,
            )
        except Exception as e:
            logger.warning(f"Astro reply failure notify_pool failed for session {external_ref}: {e}")
        return {"ok": True, "delivered": [], "failed": failed, "delivery_failed": True}

    return {"ok": True, "delivered": delivered, "failed": failed}
