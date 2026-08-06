"""Generic, per-tenant paid expert handoff: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging

from app.services.gemini_client import gemini_chat_completion_json

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "enabled": False,
    "trigger_description": "",
    "offer_message": "",
    "fields": [],  # list of {"key": str, "label": str, "type": "text"|"date"|"choice", "options": list[str]?}
    "amount_paise": 0,
}


def get_expert_handoff_config(tenant_id: str, db=None) -> dict:
    """Return expert_handoff_config from app_settings, merged with defaults."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "expert_handoff_config")
        .maybe_single()
        .execute()
    )
    if row and row.data:
        try:
            stored = json.loads(row.data["value"])
            return {**_DEFAULT_CONFIG, **stored}
        except Exception:
            logger.warning(f"Failed to parse expert_handoff_config for tenant {tenant_id}")
    return dict(_DEFAULT_CONFIG)


def save_expert_handoff_config(tenant_id: str, config: dict, db=None) -> None:
    """Persist expert_handoff_config to app_settings."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "expert_handoff_config",
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


async def detect_expert_handoff_intent(message: str, trigger_description: str, tenant_id: str) -> bool:
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
        logger.warning(f"Expert handoff detection failed, defaulting to no-match: {e}")
        return False


def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]:
    return [f["label"] for f in fields if not collected_data.get(f["key"])]


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
        logger.warning(f"Expert handoff extraction failed, keeping existing collected_data: {e}")
        return dict(collected_data)

    valid_keys = {f["key"] for f in fields}
    new_values = {k: v for k, v in data.items() if k in valid_keys and v}
    return {**collected_data, **new_values}
