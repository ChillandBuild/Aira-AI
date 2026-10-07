"""Pure ports of the backend's message-building logic (backend/app/services/auto_messages.py and
backend/app/routes/upload.py::_normalize_phone). Behaviour must stay identical: the shared vectors in
sdk/spec/vectors/*.json prove it. No I/O in this module."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

EVENTS = ("interested", "signed_up", "purchased")

_EVENT_ALIASES = {
    "interested": "interested", "interest": "interested", "enquiry": "interested", "inquiry": "interested",
    "lead": "interested", "enquired": "interested",
    "signed_up": "signed_up", "signup": "signed_up", "sign_up": "signed_up", "register": "signed_up",
    "registered": "signed_up", "registration": "signed_up",
    "purchased": "purchased", "purchase": "purchased", "order": "purchased", "order_placed": "purchased",
    "bought": "purchased", "paid": "purchased", "sale": "purchased",
}
_PHONE_KEYS = ("phone", "mobile", "phone_number", "mobile_number", "whatsapp", "whatsapp_number", "contact", "number")
_NAME_KEYS = ("name", "full_name", "customer_name", "your_name")
_URL_KEYS = ("page_url", "url", "link")
_EVENT_KEYS = ("event", "type", "trigger")
_RESERVED = set(_PHONE_KEYS + _NAME_KEYS + _URL_KEYS + _EVENT_KEYS + ("first_name", "last_name"))
_MAX_EXTRA_KEYS = 20
_MAX_FIELD_CHARS = 200
_MAX_PARAM_CHARS = 500

VAR_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_LINK_RE = re.compile(
    r"(https?://|www\.|\b[a-z0-9-]+\.(com|in|net|org|io|co|xyz|link|ly|me|info|biz|app|site|online|shop|top|club|live)\b)",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PHONE_RE = re.compile(r"[^\d+]")
_UNTRUSTED = {"first_name", "full_name", "extra"}


def _text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()[:_MAX_FIELD_CHARS]


def _first(payload: Dict[str, Any], keys: tuple) -> str:
    lowered = {str(k).strip().lower(): v for k, v in payload.items()}
    for key in keys:
        val = _text(lowered.get(key))
        if val:
            return val
    return ""


def normalize_event(raw: Optional[str]) -> Optional[str]:
    """None for an unknown event (the caller rejects it); empty/None means 'interested'."""
    if not raw:
        return "interested"
    return _EVENT_ALIASES.get(_NON_ALNUM.sub("_", raw.strip().lower()).strip("_"))


def parse_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = _first(payload, _NAME_KEYS)
    if not name:
        name = " ".join(p for p in (_first(payload, ("first_name",)), _first(payload, ("last_name",))) if p)
    extra: Dict[str, str] = {}
    for key, value in payload.items():
        k = str(key).strip().lower()
        if k in _RESERVED or k.startswith("_") or not _text(value):
            continue
        if len(extra) >= _MAX_EXTRA_KEYS:
            break
        extra[k[:50]] = _text(value)
    return {
        "phone": _first(payload, _PHONE_KEYS),
        "name": name,
        "event_raw": _first(payload, _EVENT_KEYS),
        "page_url": _first(payload, _URL_KEYS),
        "extra": extra,
    }


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits_only = _PHONE_RE.sub("", raw.strip())
    if not digits_only:
        return None
    digits_only = digits_only.lstrip("+").lstrip("0")
    if len(digits_only) == 10 and digits_only[0] in "6789":
        return "+91" + digits_only
    if len(digits_only) == 12 and digits_only.startswith("91") and digits_only[2] in "6789":
        return "+" + digits_only
    if raw.strip().startswith("+"):
        return "+" + digits_only if 8 <= len(digits_only) <= 15 else None
    if 8 <= len(digits_only) <= 15:
        return "+" + digits_only
    return None


def clean(value: Any) -> str:
    """Meta rejects text parameters with newlines, tabs or long runs of spaces."""
    return _WS_RE.sub(" ", str(value or "")).strip()[:_MAX_PARAM_CHARS]


def resolve(spec: Optional[Dict[str, Any]], ctx: Dict[str, Any], default_source: str) -> str:
    spec = spec or {"source": default_source}
    source = spec.get("source") or default_source
    if source == "text":
        value = spec.get("value") or ""
    elif source == "extra":
        value = (ctx.get("extra") or {}).get((spec.get("key") or "").strip().lower(), "")
    else:
        value = ctx.get(source) or ""
    value = clean(value)
    if source in _UNTRUSTED and _LINK_RE.search(value):
        value = ""
    return value or clean(spec.get("fallback")) or "-"


def _header_component(template: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    media_type = (template.get("header_media_type") or "").upper()
    if media_type in ("IMAGE", "VIDEO", "DOCUMENT"):
        link = template.get("header_media_url")
        if not link:
            return None
        kind = media_type.lower()
        return {"type": "header", "parameters": [{"type": kind, kind: {"link": link}}]}
    if VAR_RE.search(template.get("header_text") or ""):
        text = resolve({"source": "first_name", "fallback": "there"}, ctx, "first_name")
        return {"type": "header", "parameters": [{"type": "text", "text": text}]}
    return None


def _body_component(template: Dict[str, Any], rule: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    var_count = len(set(VAR_RE.findall(template.get("body_text") or "")))
    if not var_count:
        return None
    specs = list(rule.get("variables") or [])
    params = []
    for i in range(var_count):
        spec = specs[i] if i < len(specs) else None
        params.append({"type": "text", "text": resolve(spec, ctx, "first_name" if i == 0 else "text")})
    return {"type": "body", "parameters": params}


def _button_components(template: Dict[str, Any], rule: Dict[str, Any], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for index, btn in enumerate(template.get("buttons") or []):
        if (btn.get("type") or "").upper() == "URL" and VAR_RE.search(btn.get("url") or ""):
            suffix = quote(resolve(rule.get("button_param"), ctx, "text"), safe="/?=&-_.~")
            out.append({
                "type": "button", "sub_type": "url", "index": str(index),
                "parameters": [{"type": "text", "text": suffix}],
            })
    return out


def build_components(template: Dict[str, Any], rule: Dict[str, Any], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts = [_header_component(template, ctx), _body_component(template, rule, ctx)]
    return [p for p in parts if p] + _button_components(template, rule, ctx)


def build_context(name: Optional[str], phone: str, extra: Optional[Dict[str, Any]], page_url: Optional[str]) -> Dict[str, Any]:
    """The ctx the backend's send_one builds: first_name, full_name, page_url, phone, extra."""
    full_name = (name or "").strip()
    extras = {str(k).strip().lower()[:50]: _text(v) for k, v in (extra or {}).items() if _text(v)}
    if page_url:
        extras = {**extras, "page_url": _text(page_url)}
    return {
        "first_name": full_name.split(" ")[0] if full_name else "",
        "full_name": full_name,
        "page_url": extras.get("page_url", ""),
        "phone": phone,
        "extra": extras,
    }
