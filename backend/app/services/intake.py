"""Generic, per-tenant paid intake: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging
import uuid

from app.services.gemini_client import gemini_chat_completion_json
from app.services.intake_copy import (
    compose_line,
    compose_wrapped,
    gather_context,
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


def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]:
    return [f["label"] for f in fields if not collected_data.get(f["key"])]


_MAX_FIELD_ATTEMPTS = 2


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

        # Resolved once per turn and shared by every line this turn may send.
        language_mode = resolve_language_mode(lead_id, tenant_id, db)
        thread, knowledge = await gather_context(db, lead_id, tenant_id, body)

        async def _say(purpose: str, **kwargs) -> None:
            text = await compose_line(
                purpose,
                tenant_id=tenant_id,
                language_mode=language_mode,
                customer_message=body,
                thread=thread,
                knowledge=knowledge,
                **kwargs,
            )
            await _send_and_log(phone, text, tenant_id, lead_id, db)

        async def _say_summary(collected: dict, skipped=()) -> None:
            text = await compose_wrapped(
                "summary",
                tenant_id=tenant_id,
                language_mode=language_mode,
                customer_message=body,
                block=_summary_block(config["fields"], collected, skipped),
                thread=thread,
            )
            await _send_and_log(phone, text, tenant_id, lead_id, db)

        session = _get_active_session(lead_id, tenant_id, db)

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
                    await _say("ask_field", field_label=missing[0])
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
                await _say("ask_field", field_label=missing[0])
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
                # This message added nothing. Escalate how we ask, and after
                # _MAX_FIELD_ATTEMPTS give up on the field rather than asking a third
                # time -- live evidence 2026-08-12: the same question went out three
                # times to a lead who had twice said they did not know the answer.
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
                    )
                else:
                    await _say(purpose, field_label=pending[0]["label"])
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
            customer_name = collected.get("name", "Customer")
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


def get_session_tenant_id(session_id: str, db=None) -> str | None:
    """Look up which tenant owns a session, so the webhook route can verify the
    Razorpay signature against that tenant's own webhook secret rather than the
    default tenant's. Safe to call before the signature is verified: an attacker
    supplying a forged session_id just gets a lookup miss or another tenant's
    id, and the subsequent HMAC check against that tenant's real secret still
    fails without it."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    row = (
        db.table("intake_sessions")
        .select("tenant_id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not row or not row.data:
        return None
    return row.data.get("tenant_id")


def confirm_intake_payment(
    session_id: str,
    razorpay_payment_id: str,
    amount_paid_paise: int | None = None,
    db=None,
) -> tuple[str, str, str, str] | None:
    """Mark a session paid. The AI stays live for the lead (see
    get_paid_unresolved_session / _intake_paid_prompt_block in
    ai_reply.py) so a lead asking "when will the expert contact me" isn't met
    with silence while waiting for staff to pick up the notification. Returns
    (phone, tenant_id, lead_id, customer_name) on success, None if the session
    doesn't exist or was already paid (idempotent — Razorpay may retry webhooks)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    from datetime import datetime, timezone

    existing = (
        db.table("intake_sessions")
        .select("id,status,lead_id,tenant_id,collected_data,package_amount_paise")
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
    db.table("intake_sessions").update({
        "status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
        "paid_at": now_iso,
        "amount_paise": charged,
        # A lead can pay a link that was just superseded by a package change.
        # Record what actually arrived and flag the gap for staff rather than
        # trusting config.
        "amount_mismatch": bool(expected and charged and expected != charged),
    }).eq("id", session_id).execute()

    lead_id = session["lead_id"]
    tenant_id = session["tenant_id"]

    lead_row = (
        db.table("leads")
        .select("phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"

    try:
        notify_pool(
            tenant_id,
            "intake_paid",
            "New paid consultation",
            f"Lead '{customer_name}' paid for a consultation — check Intake.",
            db=db,
        )
    except Exception as e:
        logger.warning(f"intake_paid notify_pool failed for session {session_id}: {e}")

    return (phone, tenant_id, lead_id, customer_name)


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
