"""Outbound half of the AstroTamil bridge: hands a paid intake session to the
Django astrologer backend, and verifies the signature on its reply callback.

Follow-up questions are NOT sent from here — once the astrologer has answered,
the customer is nudged into the AstroTamil app and the conversation continues
there. push_followup() and its endpoint were removed 2026-08-18.

Django does not normalise anything it is sent — a birth date it cannot split on
"-" raises, and a gender that is not exactly "M"/"F" silently becomes "M". So
every field is normalised here and the push is abandoned when a field cannot be
trusted: a wrong horoscope is worse than no horoscope.
"""
import hashlib
import hmac
import logging
import re

import httpx

from app.config_dynamic import get_setting
from app.services.astro_normalize import (
    is_unknown_time,
    normalize_date,
    normalize_gender,
    normalize_phone,
    normalize_place,
    normalize_time,
    time_needs_meridiem,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_CONSULTATION_PATH = "/api/astrologer-welcome/bridge/consultation/"

# collected_data keys are tenant-authored (expert_handoff_config.fields), so the
# same value arrives as "dob", "date_of_birth" or "Date Of Birth" depending on who
# set the client up. Match on the squashed key rather than forcing one spelling.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "person_name": ("personname", "name", "fullname", "customername", "yourname"),
    "gender": ("gender", "persongender", "sex"),
    "birth_date": ("birthdate", "dateofbirth", "dob", "personbirthdate", "birthday"),
    "birth_time": ("birthtime", "timeofbirth", "tob", "personbirthtime"),
    "birth_place": ("birthplace", "placeofbirth", "pob", "personbirthplace", "nativeplace"),
    "question": ("question", "questiontext", "query", "concern", "problem"),
    "phone": (
        "phone", "mobile", "phonenumber", "mobilenumber", "mobileno",
        "contact", "whatsapp", "whatsappnumber",
    ),
}

# A short alias like "dob"/"sex"/"name" would false-match unrelated keys ("unisex",
# "nickname") as a substring, so only aliases at least this long fall back to a
# substring match. Exact matches always win first regardless of length.
_MIN_SUBSTRING_ALIAS_LEN = 5


def _squash(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _pick(collected: dict, field: str):
    squashed = {_squash(k): v for k, v in collected.items()}
    aliases = _FIELD_ALIASES[field]
    # Exact match wins — highest confidence.
    for alias in aliases:
        value = squashed.get(alias)
        if value not in (None, ""):
            return value
    # Fall back to substring so a tenant key like "dateofbirthdmy" still resolves
    # to "dateofbirth". Guard on alias length so short tokens can't false-match.
    for alias in aliases:
        if len(alias) < _MIN_SUBSTRING_ALIAS_LEN:
            continue
        for key, value in squashed.items():
            if alias in key and value not in (None, ""):
                return value
    return None


def field_role(key) -> str | None:
    """Which AstroTamil field a tenant-authored form key feeds ("date_of_birth" -> birth_date),
    or None when no alias matches ("place_of_birh"). The same matching _pick uses, so a form the
    setup check accepts is a form the push can read."""
    squashed = _squash(key)
    for role, aliases in _FIELD_ALIASES.items():
        if squashed in aliases:
            return role
    for role, aliases in _FIELD_ALIASES.items():
        if any(len(alias) >= _MIN_SUBSTRING_ALIAS_LEN and alias in squashed for alias in aliases):
            return role
    return None


# What the Services form must be able to collect for AstroTamil to cast a horoscope.
_REQUIRED_FORM_ROLES = (
    ("birth_date", "Date of birth"),
    ("birth_time", "Time of birth"),
    ("gender", "Gender"),
    ("birth_place", "Place of birth"),
    ("question", "Question"),
)


def missing_form_fields(fields: list[dict]) -> list[str]:
    """Labels of the AstroTamil details the form has no field for."""
    present = {field_role(f.get("key")) for f in fields or []}
    return [label for role, label in _REQUIRED_FORM_ROLES if role not in present]


def unrecognised_form_keys(fields: list[dict]) -> list[str]:
    """Form keys matching no AstroTamil detail: usually the typo behind a missing one."""
    return [f["key"] for f in fields or [] if f.get("key") and field_role(f["key"]) is None]


def _bridge_config(tenant_id: str) -> tuple[str, str] | None:
    base_url = get_setting("astro_bridge_url", tenant_id=tenant_id)
    api_key = get_setting("astro_bridge_api_key", tenant_id=tenant_id)
    if not base_url or not api_key:
        return None
    return base_url.rstrip("/"), api_key


def is_connected(tenant_id: str) -> bool:
    """True for a client with the AstroTamil connection saved (URL and key). Everything that
    only AstroTamil needs, such as the stricter detail checks, is switched on by this."""
    return _bridge_config(tenant_id) is not None


def get_bridge_secret(tenant_id: str) -> str | None:
    """The HMAC secret Django signs its reply callback with, for this tenant."""
    return get_setting("astro_bridge_secret", tenant_id=tenant_id)


async def _post(path: str, payload: dict, external_ref: str, tenant_id: str) -> dict | None:
    config = _bridge_config(tenant_id)
    if not config:
        logger.info("Astro bridge not configured for tenant %s — skipping %s", tenant_id, path)
        return None
    base_url, api_key = config

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{base_url}{path}",
                json=payload,
                headers={"X-API-Key": api_key},
            )
    except Exception as exc:
        logger.error(
            "Astro bridge POST %s failed for ref=%s tenant=%s: %s",
            path, external_ref, tenant_id, exc,
        )
        return None

    try:
        data = response.json()
    except Exception:
        data = None

    if not isinstance(data, dict) or not data.get("success"):
        detail = data.get("error") if isinstance(data, dict) else (response.text or "")[:300]
        logger.error(
            "Astro bridge rejected %s for ref=%s tenant=%s: HTTP %s %s",
            path, external_ref, tenant_id, response.status_code, detail,
        )
        return None
    return data


UNKNOWN_TIME_PLACEHOLDER = "12:00:00"
UNKNOWN_TIME_NOTE = (
    "[Note for the astrologer: the customer does not know their birth time. "
    "12:00 noon was sent as a placeholder.]"
)


def _prepare(session: dict, lead: dict) -> tuple[dict, list[str]]:
    """The normalised values the push sends, and the names of any the push cannot send. The one
    place that decides, so the payment-link check and the push can never disagree.

    A customer who does not know their birth time (marked skipped, or answering "theriyathu")
    is sent as 12:00 with a note appended to the question: they can still be helped, and the
    astrologer is told the time is not real. Any other detail that cannot be read is unusable."""
    collected = session.get("collected_data") or {}
    skipped_roles = {field_role(k) for k in session.get("skipped_fields") or []}
    raw_time = _pick(collected, "birth_time")
    # A readable time wins even inside an "I don't know exactly, maybe 6 am" answer.
    time_unknown = not normalize_time(raw_time) and (
        is_unknown_time(raw_time) or (not raw_time and "birth_time" in skipped_roles)
    )

    values = {
        "person_name": str(_pick(collected, "person_name") or lead.get("name") or "").strip(),
        "phone": normalize_phone(_pick(collected, "phone") or lead.get("phone")),
        "birth_date": normalize_date(_pick(collected, "birth_date")),
        # 5:30 could be 05:30 or 17:30, and a chart cast for the wrong one is wrong: whichever path
        # saved it, the push refuses until AM or PM is settled.
        "birth_time": UNKNOWN_TIME_PLACEHOLDER if time_unknown else (
            None if time_needs_meridiem(raw_time) else normalize_time(raw_time)
        ),
        "gender": normalize_gender(_pick(collected, "gender")),
        "birth_place": normalize_place(_pick(collected, "birth_place")) or "",
        "question_text": str(_pick(collected, "question") or session.get("trigger_reason") or "").strip(),
    }
    if time_unknown and values["question_text"]:
        values["question_text"] = f"{values['question_text']}\n\n{UNKNOWN_TIME_NOTE}"
    unusable = [
        label
        for label, key in (
            ("phone", "phone"),
            ("birth date", "birth_date"),
            ("birth time", "birth_time"),
            ("birth place", "birth_place"),
            ("gender", "gender"),
            ("question", "question_text"),
        )
        if not values[key]
    ]
    return values, unusable


def unusable_for_push(
    collected: dict, skipped: list | None, phone: str | None, trigger_reason: str | None = None,
) -> list[str]:
    """What the push would refuse for this answers-so-far: checked before a payment link is made.
    trigger_reason matters because the push falls back to it when no question was collected."""
    session = {"collected_data": collected or {}, "skipped_fields": skipped or [], "trigger_reason": trigger_reason}
    return _prepare(session, {"phone": phone})[1]


async def push_consultation(session: dict, lead: dict, tenant_id: str) -> dict | None:
    """Create the Django question for a paid session. Returns Django's response, or None."""
    session = session or {}
    lead = lead or {}
    external_ref = str(session.get("id") or "")
    if not external_ref:
        logger.error("Astro bridge consultation push skipped for tenant %s: session has no id", tenant_id)
        return None

    values, unusable = _prepare(session, lead)
    if unusable:
        logger.error(
            "Astro bridge refusing to push session %s (tenant=%s): unusable %s — "
            "a wrong horoscope is worse than none. collected_data keys=%s",
            external_ref, tenant_id, ", ".join(unusable), sorted((session.get("collected_data") or {}).keys()),
        )
        return None

    person_name, phone, gender = values["person_name"], values["phone"], values["gender"]
    birth_date, birth_time, birth_place = values["birth_date"], values["birth_time"], values["birth_place"]
    question_text = values["question_text"]

    payload = {
        "external_ref": external_ref,
        "phone": phone,
        "customer_name": person_name or "Customer",
        "person_name": person_name or "Customer",
        "person_gender": gender,
        "person_birth_date": birth_date,
        "person_birth_time": birth_time,
        "person_birth_place": birth_place,
        "question_text": question_text,
        "amount": round((session.get("amount_paise") or 0) / 100, 2),
        "tenant_id": tenant_id,
    }
    return await _post(_CONSULTATION_PATH, payload, external_ref, tenant_id)


def verify_astro_signature(raw_body: bytes, header: str, secret: str) -> bool:
    """Verify the X-Astro-Signature HMAC-SHA256 over the raw callback body."""
    if not header or not secret:
        return False
    received = header.strip()
    if received.lower().startswith("sha256="):
        received = received[len("sha256="):]
    try:
        expected = hmac.new(secret.encode(), raw_body or b"", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received.lower())
    except Exception as exc:
        logger.error("Astro bridge signature verification error: %s", exc)
        return False
