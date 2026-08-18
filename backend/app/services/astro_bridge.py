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
    normalize_date,
    normalize_gender,
    normalize_phone,
    normalize_time,
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


def _bridge_config(tenant_id: str) -> tuple[str, str] | None:
    base_url = get_setting("astro_bridge_url", tenant_id=tenant_id)
    api_key = get_setting("astro_bridge_api_key", tenant_id=tenant_id)
    if not base_url or not api_key:
        return None
    return base_url.rstrip("/"), api_key


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


async def push_consultation(session: dict, lead: dict, tenant_id: str) -> dict | None:
    """Create the Django question for a paid session. Returns Django's response, or None."""
    session = session or {}
    lead = lead or {}
    external_ref = str(session.get("id") or "")
    if not external_ref:
        logger.error("Astro bridge consultation push skipped for tenant %s: session has no id", tenant_id)
        return None

    collected = session.get("collected_data") or {}
    person_name = str(_pick(collected, "person_name") or lead.get("name") or "").strip()
    phone = normalize_phone(_pick(collected, "phone") or lead.get("phone"))
    birth_date = normalize_date(_pick(collected, "birth_date"))
    birth_time = normalize_time(_pick(collected, "birth_time"))
    gender = normalize_gender(_pick(collected, "gender"))
    birth_place = str(_pick(collected, "birth_place") or "").strip()
    question_text = str(_pick(collected, "question") or session.get("trigger_reason") or "").strip()

    unusable = [
        label
        for label, value in (
            ("phone", phone),
            ("birth date", birth_date),
            ("birth time", birth_time),
            ("gender", gender),
            ("question", question_text),
        )
        if not value
    ]
    if unusable:
        logger.error(
            "Astro bridge refusing to push session %s (tenant=%s): unusable %s — "
            "a wrong horoscope is worse than none. collected_data keys=%s",
            external_ref, tenant_id, ", ".join(unusable), sorted(collected.keys()),
        )
        return None

    if not birth_place:
        logger.warning("Astro bridge pushing session %s with no birth place", external_ref)

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
