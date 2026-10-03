"""Auto-Messages: a customer's number + an event + a product arrives (website
form, API call, shop counter) and the tenant's matching approved template goes
out once, optionally after a delay. See docs/designs/auto-messages.md.

Flow: parse -> lead (create_inbound_lead) -> match product to catalog_items ->
pick rule (product rule beats the event's default rule) -> duplicate check ->
auto_message_sends row (queued) -> sent now (delay 0) or by the scheduler
(process_due_sends). Every outcome, including "no rule" and "duplicate", is a
row in auto_message_sends so the owner can see why someone got nothing.
"""
import logging
import re
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

EVENTS = ("interested", "signed_up", "purchased")
SOURCES = ("website", "api", "store")
_OPT_IN_SOURCE = {"website": "website_form", "api": "api", "store": "offline_event"}
DUPLICATE_WINDOW = timedelta(hours=24)

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
_PRODUCT_KEYS = ("product", "product_name", "model", "item", "interest", "interested_in", "service")
_URL_KEYS = ("product_url", "url", "link", "page_url")
_EVENT_KEYS = ("event", "type", "trigger")
_RESERVED = set(_PHONE_KEYS + _NAME_KEYS + _PRODUCT_KEYS + _URL_KEYS + _EVENT_KEYS + ("first_name", "last_name"))
_MAX_EXTRA_KEYS = 20
_MAX_FIELD_CHARS = 200

VAR_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
# Anything that looks like a link. Names, products and extra fields come from a
# public form, so a link there would be sent inside the tenant's own template.
_LINK_RE = re.compile(
    r"(https?://|www\.|\b[a-z0-9-]+\.(com|in|net|org|io|co|xyz|link|ly|me|info|biz|app|site|online|shop|top|club|live)\b)",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
STUCK_AFTER = timedelta(minutes=15)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _text(value) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()[:_MAX_FIELD_CHARS]


def _first(payload: dict, keys: tuple) -> str:
    lowered = {str(k).strip().lower(): v for k, v in payload.items()}
    for key in keys:
        val = _text(lowered.get(key))
        if val:
            return val
    return ""


def normalize_event(raw: str | None) -> str | None:
    """None for an event we don't know -- the caller rejects it rather than
    guessing, so a typo never sends the wrong template."""
    if not raw:
        return "interested"
    return _EVENT_ALIASES.get(_NON_ALNUM.sub("_", raw.strip().lower()).strip("_"))


def parse_payload(payload: dict) -> dict:
    """Flat JSON / form fields from a website form, Zapier, Pabbly or a billing
    app. Field names vary by tool, so the common spellings are all accepted;
    anything else scalar is kept as `extra` (usable as a template variable)."""
    name = _first(payload, _NAME_KEYS)
    if not name:
        name = " ".join(p for p in (_first(payload, ("first_name",)), _first(payload, ("last_name",))) if p)
    extra = {}
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
        "product": _first(payload, _PRODUCT_KEYS),
        "product_url": _first(payload, _URL_KEYS),
        "extra": extra,
    }


def _norm(value: str) -> str:
    return _NON_ALNUM.sub(" ", (value or "").lower()).strip()


def match_product(items: list[dict], product_raw: str) -> dict | None:
    """Exact name/alias match first; otherwise the longest name/alias that
    appears as whole words inside what was sent ("Ather Konarc S 161 km" ->
    "Konarc S" beats "Konarc")."""
    wanted = _norm(product_raw)
    if not wanted:
        return None
    best: tuple[int, dict] | None = None
    for item in items:
        for label in [item.get("name") or ""] + list(item.get("aliases") or []):
            label_n = _norm(label)
            if not label_n:
                continue
            if label_n == wanted:
                return item
            if f" {label_n} " in f" {wanted} " and (best is None or len(label_n) > best[0]):
                best = (len(label_n), item)
    return best[1] if best else None


def tenant_catalog(db, tenant_id: str) -> list[dict]:
    return (
        db.table("catalog_items").select("id, name, aliases, price_paise, status")
        .eq("tenant_id", tenant_id).limit(2000).execute()
    ).data or []


def pick_rule(db, tenant_id: str, event: str, catalog_item_id: str | None) -> dict | None:
    rows = (
        db.table("auto_message_rules").select("*")
        .eq("tenant_id", tenant_id).eq("event", event).eq("enabled", True).execute()
    ).data or []
    if catalog_item_id:
        for r in rows:
            if r.get("catalog_item_id") == catalog_item_id:
                return r
    for r in rows:
        if not r.get("catalog_item_id"):
            return r
    return None


def _is_duplicate(db, tenant_id: str, phone: str, event: str, catalog_item_id: str | None, product_raw: str) -> bool:
    since = (datetime.now(timezone.utc) - DUPLICATE_WINDOW).isoformat()
    rows = (
        db.table("auto_message_sends").select("catalog_item_id, product_raw")
        .eq("tenant_id", tenant_id).eq("phone", phone).eq("event", event)
        .in_("status", ["queued", "sending", "sent"]).gte("created_at", since).limit(50).execute()
    ).data or []
    for r in rows:
        if catalog_item_id or r.get("catalog_item_id"):
            if r.get("catalog_item_id") == catalog_item_id:
                return True
        elif _norm(r.get("product_raw") or "") == _norm(product_raw):
            return True
    return False


def _add_note(db, tenant_id: str, lead_id: str, content: str) -> None:
    try:
        db.table("lead_notes").insert({
            "lead_id": lead_id, "tenant_id": tenant_id, "content": content, "is_pinned": False, "structured": False,
        }).execute()
    except Exception as e:
        logger.warning(f"auto_messages: note insert failed for lead {lead_id}: {e}")


_EVENT_LABEL = {"interested": "Interested in", "signed_up": "Signed up for", "purchased": "Purchased"}
_SOURCE_LABEL = {"website": "website form", "api": "API", "store": "shop counter"}


async def handle_event(tenant_id: str, source: str, data: dict, db=None) -> dict:
    """data = parse_payload() output (or the same keys from quick-add).
    Returns {"status": "ok"|"ignored", ...}. Never raises for a send failure:
    the send row records it."""
    from app.routes.upload import _normalize_phone
    from app.services.inbound_lead import create_inbound_lead

    db = db or get_supabase()
    event = normalize_event(data.get("event_raw"))
    if not event:
        return {"status": "ignored", "detail": f"unknown event {data.get('event_raw')!r}"}
    phone = _normalize_phone(data.get("phone") or "")
    if not phone:
        return {"status": "ignored", "detail": "missing or invalid phone"}

    lead_id = create_inbound_lead(
        tenant_id, phone, source, name=data.get("name") or None,
        opt_in_source=_OPT_IN_SOURCE[source], db=db,
    )
    if not lead_id:
        return {"status": "ignored", "detail": "missing or invalid phone"}

    product_raw = data.get("product") or ""
    item = match_product(tenant_catalog(db, tenant_id), product_raw) if product_raw else None
    catalog_item_id = item["id"] if item else None
    product_label = (item or {}).get("name") or product_raw
    note = f"{_EVENT_LABEL[event]} {product_label or 'a product'} (via {_SOURCE_LABEL[source]})"
    _add_note(db, tenant_id, lead_id, note)

    rule = pick_rule(db, tenant_id, event, catalog_item_id)
    row = {
        "tenant_id": tenant_id, "lead_id": lead_id, "phone": phone, "name": data.get("name") or None,
        "event": event, "source": source, "product_raw": product_raw or None, "catalog_item_id": catalog_item_id,
        "extra": {**(data.get("extra") or {}), **({"product_url": data["product_url"]} if data.get("product_url") else {})},
    }
    if not rule:
        row.update(status="skipped", reason="no_rule")
    elif _is_duplicate(db, tenant_id, phone, event, catalog_item_id, product_raw):
        row.update(status="skipped", reason="duplicate", rule_id=rule["id"], template_id=rule["template_id"])
    else:
        send_at = datetime.now(timezone.utc) + timedelta(minutes=rule.get("delay_minutes") or 0)
        row.update(status="queued", rule_id=rule["id"], template_id=rule["template_id"], send_at=send_at.isoformat())

    inserted = db.table("auto_message_sends").insert(row).execute().data or []
    send = inserted[0] if inserted else row
    if send.get("status") == "queued" and rule and not rule.get("delay_minutes"):
        await send_one(db, send)
        refreshed = (
            db.table("auto_message_sends").select("status, reason").eq("id", send["id"]).limit(1).execute()
        ).data or []
        if refreshed:
            send.update(refreshed[0])
    return {
        "status": "ok", "lead_id": lead_id, "event": event, "matched_product": product_label if item else None,
        "message_status": send.get("status"), "reason": send.get("reason"),
    }


# ---------------------------------------------------------------- sending

def format_inr(paise) -> str:
    if paise is None:
        return ""
    rupees = int(paise) // 100
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"₹{s}"


def _clean(value) -> str:
    """Meta rejects text parameters with newlines, tabs or long runs of spaces."""
    return _WS_RE.sub(" ", str(value or "")).strip()[:500]


# Customer-supplied sources: a link in any of these is dropped (the fallback is used instead).
_UNTRUSTED = {"first_name", "full_name", "product", "extra"}


def _resolve(spec: dict | None, ctx: dict, default_source: str) -> str:
    spec = spec or {"source": default_source}
    source = spec.get("source") or default_source
    if source == "text":
        value = spec.get("value") or ""
    elif source == "extra":
        value = (ctx.get("extra") or {}).get((spec.get("key") or "").strip().lower(), "")
    else:
        value = ctx.get(source) or ""
    value = _clean(value)
    if source in _UNTRUSTED and _LINK_RE.search(value):
        value = ""
    return value or _clean(spec.get("fallback")) or "-"


def build_components(template: dict, rule: dict, ctx: dict) -> list[dict]:
    """Body variables in {{n}} order from rule.variables (defaults: name, then
    product), an image/video/document header, a {{1}} header text, and the
    suffix of a dynamic URL button."""
    components: list[dict] = []

    media_type = (template.get("header_media_type") or "").upper()
    if media_type in ("IMAGE", "VIDEO", "DOCUMENT"):
        link = (ctx.get("product_image") if media_type == "IMAGE" else None) or template.get("header_media_url")
        if link:
            components.append({"type": "header", "parameters": [{"type": media_type.lower(), media_type.lower(): {"link": link}}]})
    elif VAR_RE.search(template.get("header_text") or ""):
        components.append({"type": "header", "parameters": [{"type": "text", "text": ctx.get("product") or "-"}]})

    var_count = len(set(VAR_RE.findall(template.get("body_text") or "")))
    if var_count:
        specs = list(rule.get("variables") or [])
        defaults = ["first_name", "product"]
        params = []
        for i in range(var_count):
            spec = specs[i] if i < len(specs) else None
            params.append({"type": "text", "text": _resolve(spec, ctx, defaults[i] if i < len(defaults) else "text")})
        components.append({"type": "body", "parameters": params})

    for index, btn in enumerate(template.get("buttons") or []):
        if (btn.get("type") or "").upper() == "URL" and VAR_RE.search(btn.get("url") or ""):
            # The suffix is pasted into the template's URL, so it must be URL-safe.
            suffix = quote(_resolve(rule.get("button_param"), ctx, "product"), safe="/?=&-_.~")
            components.append({
                "type": "button", "sub_type": "url", "index": str(index),
                "parameters": [{"type": "text", "text": suffix}],
            })
    return components


def _product_image(db, catalog_item_id: str | None) -> str | None:
    if not catalog_item_id:
        return None
    rows = (
        db.table("catalog_media").select("storage_path").eq("catalog_item_id", catalog_item_id)
        .order("sort_order").limit(1).execute()
    ).data or []
    if not rows:
        return None
    try:
        return db.storage.from_("catalog-media").get_public_url(rows[0]["storage_path"])
    except Exception:
        return None


def _finish(db, send_id: str, status: str, reason: str | None = None) -> None:
    patch: dict = {"status": status, "reason": (reason or None) and reason[:300]}
    if status == "sent":
        patch["sent_at"] = datetime.now(timezone.utc).isoformat()
    db.table("auto_message_sends").update(patch).eq("id", send_id).execute()


async def send_one(db, send: dict) -> bool:
    """Claims a queued row (queued -> sending, so two runs never double-send),
    then sends. Final status: sent | failed | skipped, with a reason."""
    claimed = (
        db.table("auto_message_sends").update({"status": "sending"})
        .eq("id", send["id"]).eq("status", "queued").execute()
    ).data or []
    if not claimed:
        return False
    tenant_id = send["tenant_id"]

    lead = None
    if send.get("lead_id"):
        rows = (
            db.table("leads").select("id, name, opted_out, deleted_at")
            .eq("id", send["lead_id"]).eq("tenant_id", tenant_id).limit(1).execute()
        ).data or []
        lead = rows[0] if rows else None
    if lead and lead.get("opted_out"):
        _finish(db, send["id"], "skipped", "opted_out")
        return False

    rule_rows = []
    if send.get("rule_id"):
        rule_rows = (
            db.table("auto_message_rules").select("*").eq("id", send["rule_id"]).eq("tenant_id", tenant_id)
            .limit(1).execute()
        ).data or []
    if not rule_rows or not rule_rows[0].get("enabled"):
        _finish(db, send["id"], "skipped", "rule_removed_or_off")
        return False
    rule = rule_rows[0]

    template_rows = (
        db.table("message_templates")
        .select("name, language, body_text, status, header_media_type, header_media_url, header_text, buttons")
        .eq("id", rule["template_id"]).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    if not template_rows or (template_rows[0].get("status") or "").upper() != "APPROVED":
        _finish(db, send["id"], "failed", "template_not_approved")
        return False
    template = template_rows[0]

    item = None
    if send.get("catalog_item_id"):
        rows = (
            db.table("catalog_items").select("id, name, price_paise")
            .eq("id", send["catalog_item_id"]).eq("tenant_id", tenant_id).limit(1).execute()
        ).data or []
        item = rows[0] if rows else None

    full_name = (send.get("name") or (lead or {}).get("name") or "").strip()
    extra = dict(send.get("extra") or {})
    ctx = {
        "first_name": full_name.split(" ")[0] if full_name else "",
        "full_name": full_name,
        "product": (item or {}).get("name") or send.get("product_raw") or "",
        "price": format_inr((item or {}).get("price_paise")),
        "product_url": extra.get("product_url", ""),
        "phone": send.get("phone") or "",
        "extra": extra,
        "product_image": _product_image(db, send.get("catalog_item_id")),
    }

    try:
        from app.services.meta_cloud import send_template_message
        res = await send_template_message(
            send["phone"], template["name"], template.get("language") or "en",
            components=build_components(template, rule, ctx), tenant_id=tenant_id,
        )
    except Exception as e:
        detail = getattr(e, "detail", None) or str(e)
        logger.warning(f"auto_messages: send {send['id']} failed for tenant {tenant_id}: {detail}")
        _finish(db, send["id"], "failed", str(detail))
        return False

    _finish(db, send["id"], "sent")
    if send.get("lead_id"):
        try:
            sid = ((res or {}).get("messages") or [{}])[0].get("id")
            db.table("messages").insert({
                "lead_id": send["lead_id"], "tenant_id": tenant_id, "direction": "outbound", "channel": "whatsapp",
                "content": f"[Auto-message: {template['name']}]", "is_ai_generated": False,
                "meta_message_id": sid or "", "reply_source": "automation",
            }).execute()
        except Exception as e:
            logger.warning(f"auto_messages: message log insert failed for send {send['id']}: {e}")
    return True


async def process_due_sends(limit: int = 50) -> int:
    """Scheduler job: send queued rows whose delay is up. Rows left in
    'sending' by a crash mid-send are marked failed, never re-sent: Meta may
    already have delivered them."""
    db = get_supabase()
    stuck_before = (datetime.now(timezone.utc) - STUCK_AFTER).isoformat()
    db.table("auto_message_sends").update({"status": "failed", "reason": "interrupted"})         .eq("status", "sending").lt("send_at", stuck_before).execute()
    now = datetime.now(timezone.utc).isoformat()
    due = (
        db.table("auto_message_sends").select("*").eq("status", "queued").lte("send_at", now)
        .order("send_at").limit(limit).execute()
    ).data or []
    sent = 0
    for row in due:
        try:
            if await send_one(db, row):
                sent += 1
        except Exception as e:
            logger.error(f"auto_messages: unexpected error on send {row.get('id')}: {e}")
    return sent
