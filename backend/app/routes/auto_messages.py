"""Auto-Messages routes. See services/auto_messages.py and docs/designs/auto-messages.md.

Public (no auth): the tenant is identified by an opaque token in the path, the
same shape as marketplace_intake.py. The token is NOT secret in practice -- the
website form puts it in the page -- so all it can do is create a lead and
trigger the tenant's own approved templates, and it is rate-limited per IP and
per tenant. It can never read data.
  POST /in/{token}          JSON or form fields (website form, Zapier, Pabbly, apps, billing software)
  GET  /in/{token}/form.js  the copy-paste website form

Authenticated: setup (URL + snippet), rules, product aliases, shop quick-add, send log.
"""
import json
import logging
import secrets
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.config import settings as env_settings
from app.config_dynamic import get_setting, save_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services import auto_messages as svc

logger = logging.getLogger(__name__)

public_router = APIRouter()
router = APIRouter()

require_settings_manage = require_permission("settings.manage")
require_settings_view = require_permission("settings.view")
require_leads_manage = require_permission("leads.manage")
require_catalog_manage = require_permission("catalog.manage")

TOKEN_KEY = "auto_messages_ingest_token"
_RENDER_BASE_URL = "https://aira-ai-5tfr.onrender.com"
_PUBLIC_HEADERS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"}


class _SlidingWindow:
    """`limit` hits per `window` seconds per key, in-process (same approach as
    brain_sandbox: slowapi in main.py is per IP only and can't express per tenant)."""

    def __init__(self, limit: int, window_seconds: float):
        self._limit, self._window = limit, window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# One person filling a form a few times is fine; a script hammering it is not.
_per_ip = _SlidingWindow(10, 10 * 60)
# A busy billing system can post a lot; this only stops a runaway loop or abuse.
_per_tenant = _SlidingWindow(1000, 60 * 60)


def _base_url() -> str:
    base_url = get_setting("public_base_url") or env_settings.public_base_url or _RENDER_BASE_URL
    return base_url.rstrip("/")


def _urls(token: str) -> dict:
    base = f"{_base_url()}/api/v1/auto-messages/in/{token}"
    return {"ingest_url": base, "form_script_url": f"{base}/form.js"}


def _resolve_tenant(db, token: str) -> str | None:
    if not token or len(token) > 100:
        return None
    rows = (
        db.table("app_settings").select("tenant_id").eq("key", TOKEN_KEY).eq("value", token).limit(1).execute()
    ).data or []
    return rows[0]["tenant_id"] if rows else None


def _client_ip(request: Request) -> str:
    """The first X-Forwarded-For entry is whatever the client sent, so it can't
    key a rate limit. Prefer the edge-set client IP headers, then the entry
    the nearest proxy appended (rightmost)."""
    for header in ("cf-connecting-ip", "true-client-ip"):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def _read_payload(request: Request) -> dict:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        return {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Send JSON or form fields")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    return payload


def _public(status_code: int, content: dict) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=_PUBLIC_HEADERS)


# The website form posts form-encoded fields, a CORS "simple request" with no
# preflight, so the global CORSMiddleware allow-list never blocks it and the
# Access-Control-Allow-Origin: * on the response lets the form read the result.
@public_router.post("/in/{token}")
async def ingest(token: str, request: Request):
    db = get_supabase()
    tenant_id = _resolve_tenant(db, token)
    if not tenant_id:
        return _public(401, {"error": "Unauthorized", "code": "unauthorized"})
    try:
        payload = await _read_payload(request)
    except HTTPException as e:
        return _public(400, {"error": e.detail, "code": "bad_request"})
    source = "website" if payload.get("_src") == "form" else "api"
    # The per-IP limit is for the website form (one visitor = one IP). An app or
    # billing server sends every customer from the same IP, so API calls are
    # held only by the per-tenant cap.
    ip_ok = source != "website" or _per_ip.allow(f"{token}:{_client_ip(request)}")
    if not ip_ok or not _per_tenant.allow(tenant_id):
        return _public(429, {"error": "Too many requests, try again later", "code": "rate_limited"})

    # Hidden honeypot field on the website form: bots fill it, people can't see it.
    honeypot = payload.get("_hp")
    if isinstance(honeypot, str) and honeypot.strip():
        return _public(200, {"status": "ok"})

    data = svc.parse_payload(payload)
    result = await svc.handle_event(tenant_id, source, data, db=db)
    if result["status"] != "ok":
        return _public(422, {"error": result.get("detail"), "code": "ignored"})
    return _public(200, {k: result.get(k) for k in ("status", "event", "matched_product", "message_status", "reason")})


@public_router.get("/in/{token}/form.js")
def form_script(token: str):
    db = get_supabase()
    tenant_id = _resolve_tenant(db, token)
    if not tenant_id:
        return Response("/* Aira: this form link is no longer valid. Copy the new snippet from Aira. */",
                        media_type="application/javascript", headers=_PUBLIC_HEADERS)
    # Only finished ("ready") products are offered to the public; drafts still match by name.
    products = sorted({i["name"] for i in svc.tenant_catalog(db, tenant_id) if i.get("name") and i.get("status") == "ready"})
    script = _FORM_JS.replace("__ENDPOINT__", json.dumps(_urls(token)["ingest_url"])).replace(
        "__PRODUCTS__", json.dumps(products[:300])
    )
    return Response(script, media_type="application/javascript",
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=300"})


# The website form. Renders into every <div data-aira-form>. Options on the div:
#   data-product="Konarc"   fixed product (product page) -> no product dropdown
#   data-event="signed_up"  default "interested"
#   data-title, data-button, data-success  text overrides
# Plain DOM, no dependencies, styles scoped under .aira-f so it can't break the host page.
_FORM_JS = r"""(function () {
  var ENDPOINT = __ENDPOINT__;
  var PRODUCTS = __PRODUCTS__;
  var css = ".aira-f{font-family:inherit;max-width:380px;display:grid;gap:10px;padding:18px;border:1px solid #e3e3e3;border-radius:12px;background:#fff;color:#1a1a1a;box-sizing:border-box}" +
    ".aira-f *{box-sizing:border-box}.aira-f h3{margin:0 0 2px;font-size:17px;font-weight:600}" +
    ".aira-f input,.aira-f select{width:100%;padding:10px 12px;border:1px solid #cfcfcf;border-radius:8px;font:inherit;font-size:15px;background:#fff;color:inherit}" +
    ".aira-f input:focus,.aira-f select:focus{outline:2px solid #25d366;outline-offset:1px;border-color:#25d366}" +
    ".aira-f button{padding:11px 14px;border:0;border-radius:8px;background:#25d366;color:#fff;font:inherit;font-size:15px;font-weight:600;cursor:pointer}" +
    ".aira-f button[disabled]{opacity:.6;cursor:default}.aira-f .aira-n{font-size:12px;color:#666;margin:0}" +
    ".aira-f .aira-e{font-size:13px;color:#c0392b;margin:0}.aira-f .aira-ok{font-size:15px;margin:0;padding:6px 0}" +
    ".aira-f .aira-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}";
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in attrs) { if (attrs[k] !== undefined) e.setAttribute(k, attrs[k]); }
    if (text) e.textContent = text;
    return e;
  }
  function render(host) {
    if (host.getAttribute("data-aira-ready")) return;
    host.setAttribute("data-aira-ready", "1");
    var fixed = host.getAttribute("data-product") || "";
    var form = el("form", { "class": "aira-f", novalidate: "" });
    form.appendChild(el("h3", {}, host.getAttribute("data-title") || "Get details on WhatsApp"));
    var name = el("input", { name: "name", placeholder: "Your name", autocomplete: "name", maxlength: "80" });
    var phone = el("input", { name: "phone", placeholder: "WhatsApp number", type: "tel", autocomplete: "tel", inputmode: "tel", maxlength: "16", required: "" });
    form.appendChild(name); form.appendChild(phone);
    var product = null;
    if (!fixed && PRODUCTS.length) {
      product = el("select", { name: "product" });
      product.appendChild(el("option", { value: "" }, "Which product?"));
      PRODUCTS.forEach(function (p) { product.appendChild(el("option", { value: p }, p)); });
      form.appendChild(product);
    }
    var hp = el("div", { "class": "aira-hp", "aria-hidden": "true" });
    hp.appendChild(el("input", { name: "_hp", tabindex: "-1", autocomplete: "off" }));
    form.appendChild(hp);
    var err = el("p", { "class": "aira-e", role: "alert" });
    var btn = el("button", { type: "submit" }, host.getAttribute("data-button") || "Send me details");
    form.appendChild(err); form.appendChild(btn);
    form.appendChild(el("p", { "class": "aira-n" }, "We'll send you updates on WhatsApp."));
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      err.textContent = "";
      var digits = (phone.value || "").replace(/[^0-9]/g, "");
      if (digits.length < 10 || digits.length > 13) { err.textContent = "Please enter a valid WhatsApp number."; phone.focus(); return; }
      if (product && !product.value) { err.textContent = "Please choose a product."; product.focus(); return; }
      btn.disabled = true;
      var body = new URLSearchParams();
      body.set("name", name.value.trim()); body.set("phone", phone.value.trim());
      body.set("product", fixed || (product ? product.value : ""));
      body.set("event", host.getAttribute("data-event") || "interested");
      body.set("product_url", location.href); body.set("_src", "form");
      body.set("_hp", form.querySelector("[name=_hp]").value);
      fetch(ENDPOINT, { method: "POST", body: body }).then(function (r) {
        if (r.status === 429) throw new Error("Too many tries. Please wait a few minutes.");
        if (!r.ok) throw new Error("Please check your number and try again.");
        form.innerHTML = "";
        form.appendChild(el("p", { "class": "aira-ok" }, host.getAttribute("data-success") || "Thanks! Check WhatsApp in a few minutes."));
      }).catch(function (e) { err.textContent = e.message || "Something went wrong. Please try again."; btn.disabled = false; });
    });
    host.appendChild(form);
  }
  function init() {
    if (!document.getElementById("aira-f-css")) { var s = el("style", { id: "aira-f-css" }); s.textContent = css; document.head.appendChild(s); }
    var hosts = document.querySelectorAll("[data-aira-form]");
    for (var i = 0; i < hosts.length; i++) render(hosts[i]);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
"""


# ---------------------------------------------------------------- setup

@router.get("/setup")
def get_setup(ctx: dict = Depends(require_settings_manage)):
    token = get_setting(TOKEN_KEY, tenant_id=ctx["tenant_id"])
    return _urls(token) if token else {"ingest_url": None, "form_script_url": None}


@router.post("/setup/token")
def rotate_token(ctx: dict = Depends(require_settings_manage)):
    """(Re)generates the intake link. Rotating breaks the old link at once: the
    website snippet and any Zapier/app setup must be updated."""
    token = secrets.token_urlsafe(24)
    save_setting(TOKEN_KEY, token, tenant_id=ctx["tenant_id"])
    return _urls(token)


# ---------------------------------------------------------------- rules

class VariableSpec(BaseModel):
    source: str = Field(pattern="^(first_name|full_name|product|price|product_url|phone|extra|text)$")
    key: str | None = Field(default=None, max_length=50)
    value: str | None = Field(default=None, max_length=200)
    fallback: str | None = Field(default=None, max_length=200)


class RuleIn(BaseModel):
    event: str = Field(pattern="^(interested|signed_up|purchased)$")
    catalog_item_id: str | None = None
    template_id: str
    delay_minutes: int = Field(default=0, ge=0, le=10080)
    variables: list[VariableSpec] = Field(default_factory=list, max_length=20)
    button_param: VariableSpec | None = None
    enabled: bool = True


class RulePatch(BaseModel):
    template_id: str | None = None
    delay_minutes: int | None = Field(default=None, ge=0, le=10080)
    variables: list[VariableSpec] | None = Field(default=None, max_length=20)
    button_param: VariableSpec | None = None
    enabled: bool | None = None


def _check_template(db, tenant_id: str, template_id: str) -> None:
    rows = (
        db.table("message_templates").select("status").eq("id", template_id).eq("tenant_id", tenant_id)
        .limit(1).execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")
    if (rows[0].get("status") or "").upper() != "APPROVED":
        raise HTTPException(status_code=400, detail="Pick a template that Meta has approved")


def _check_item(db, tenant_id: str, item_id: str) -> None:
    rows = (
        db.table("catalog_items").select("id").eq("id", item_id).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Product not found")


@router.get("/rules")
def list_rules(ctx: dict = Depends(require_settings_view)):
    rows = (
        get_supabase().table("auto_message_rules").select("*").eq("tenant_id", ctx["tenant_id"])
        .order("created_at").execute()
    ).data or []
    return {"rules": rows}


@router.post("/rules")
def create_rule(payload: RuleIn, ctx: dict = Depends(require_settings_manage)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    _check_template(db, tenant_id, payload.template_id)
    if payload.catalog_item_id:
        _check_item(db, tenant_id, payload.catalog_item_id)
    q = db.table("auto_message_rules").select("id").eq("tenant_id", tenant_id).eq("event", payload.event)
    q = q.eq("catalog_item_id", payload.catalog_item_id) if payload.catalog_item_id else q.is_("catalog_item_id", "null")
    if (q.limit(1).execute().data or []):
        raise HTTPException(status_code=409, detail="There is already a message for this event and product")
    row = {
        **payload.model_dump(exclude={"variables", "button_param"}),
        "variables": [v.model_dump() for v in payload.variables],
        "button_param": payload.button_param.model_dump() if payload.button_param else None,
        "tenant_id": tenant_id,
    }
    inserted = db.table("auto_message_rules").insert(row).execute().data or []
    if not inserted:
        raise HTTPException(status_code=500, detail="Could not save")
    return inserted[0]


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, payload: RulePatch, ctx: dict = Depends(require_settings_manage)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    patch = payload.model_dump(exclude_unset=True)
    if "template_id" in patch:
        if not patch["template_id"]:
            raise HTTPException(status_code=400, detail="Pick a template")
        _check_template(db, tenant_id, patch["template_id"])
    if "variables" in patch and patch["variables"] is not None:
        patch["variables"] = [v.model_dump() for v in payload.variables or []]
    elif "variables" in patch:
        patch.pop("variables")
    if "button_param" in patch:
        patch["button_param"] = payload.button_param.model_dump() if payload.button_param else None
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to change")
    from datetime import datetime, timezone
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = (
        db.table("auto_message_rules").update(patch).eq("id", rule_id).eq("tenant_id", tenant_id).execute()
    ).data or []
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found")
    return updated[0]


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, ctx: dict = Depends(require_settings_manage)):
    deleted = (
        get_supabase().table("auto_message_rules").delete().eq("id", rule_id).eq("tenant_id", ctx["tenant_id"])
        .execute()
    ).data or []
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True}


# ---------------------------------------------------------------- product aliases

class AliasesIn(BaseModel):
    aliases: list[str] = Field(default_factory=list, max_length=30)


@router.put("/products/{item_id}/aliases")
def set_aliases(item_id: str, payload: AliasesIn, ctx: dict = Depends(require_catalog_manage)):
    cleaned, seen = [], set()
    for a in payload.aliases:
        a = (a or "").strip()[:80]
        if a and a.lower() not in seen:
            seen.add(a.lower())
            cleaned.append(a)
    updated = (
        get_supabase().table("catalog_items").update({"aliases": cleaned})
        .eq("id", item_id).eq("tenant_id", ctx["tenant_id"]).execute()
    ).data or []
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"id": item_id, "aliases": cleaned}


@router.get("/templates")
def list_templates(ctx: dict = Depends(require_settings_view)):
    """Approved templates with what the rule editor needs: the body's {{n}}
    count, the header type and whether a URL button has a {{1}} suffix."""
    rows = (
        get_supabase().table("message_templates")
        .select("id, name, category, language, status, body_text, header_media_type, header_text, buttons")
        .eq("tenant_id", ctx["tenant_id"]).execute()
    ).data or []
    out = []
    for t in rows:
        if (t.get("status") or "").upper() != "APPROVED":
            continue
        out.append({
            "id": t["id"], "name": t["name"], "category": t.get("category"), "language": t.get("language"),
            "body_text": t.get("body_text") or "", "header_media_type": t.get("header_media_type"),
            "variable_count": len(set(svc.VAR_RE.findall(t.get("body_text") or ""))),
            "has_dynamic_button": any(
                (b.get("type") or "").upper() == "URL" and svc.VAR_RE.search(b.get("url") or "")
                for b in (t.get("buttons") or [])
            ),
            "buttons": [b.get("text") for b in (t.get("buttons") or []) if b.get("text")],
        })
    return {"templates": sorted(out, key=lambda t: t["name"])}


@router.get("/products")
def list_products(ctx: dict = Depends(require_settings_view)):
    items = svc.tenant_catalog(get_supabase(), ctx["tenant_id"])
    return {"products": [
        {"id": i["id"], "name": i["name"], "aliases": i.get("aliases") or [], "price_paise": i.get("price_paise")}
        for i in sorted(items, key=lambda i: (i.get("name") or "").lower())
    ]}


# ---------------------------------------------------------------- shop quick-add

class QuickAddIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str = Field(min_length=6, max_length=20)
    event: str = Field(default="purchased", pattern="^(interested|signed_up|purchased)$")
    catalog_item_id: str | None = None
    product: str | None = Field(default=None, max_length=200)


@router.post("/quick-add")
async def quick_add(payload: QuickAddIn, ctx: dict = Depends(require_leads_manage)):
    db = get_supabase()
    product = (payload.product or "").strip()
    if payload.catalog_item_id:
        rows = (
            db.table("catalog_items").select("name").eq("id", payload.catalog_item_id)
            .eq("tenant_id", ctx["tenant_id"]).limit(1).execute()
        ).data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Product not found")
        product = rows[0]["name"]
    result = await svc.handle_event(ctx["tenant_id"], "store", {
        "phone": payload.phone, "name": (payload.name or "").strip(), "event_raw": payload.event,
        "product": product, "product_url": "", "extra": {},
    }, db=db)
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail="Enter a valid mobile number")
    return result


@router.get("/quick-add/products")
def quick_add_products(ctx: dict = Depends(require_leads_manage)):
    """Product picker for counter staff, who usually have leads.manage but not settings.view."""
    items = svc.tenant_catalog(get_supabase(), ctx["tenant_id"])
    return {"products": [
        {"id": i["id"], "name": i["name"], "aliases": [], "price_paise": i.get("price_paise")}
        for i in sorted(items, key=lambda i: (i.get("name") or "").lower()) if i.get("status") == "ready"
    ]}


@router.get("/quick-add/recent")
def quick_add_recent(ctx: dict = Depends(require_leads_manage)):
    rows = (
        get_supabase().table("auto_message_sends")
        .select("id, phone, name, event, source, product_raw, catalog_item_id, status, reason, send_at, sent_at, created_at")
        .eq("tenant_id", ctx["tenant_id"]).eq("source", "store").order("created_at", desc=True).limit(10).execute()
    ).data or []
    return {"sends": rows}


# ---------------------------------------------------------------- send log

@router.get("/sends")
def list_sends(status: str | None = None, limit: int = 100, ctx: dict = Depends(require_settings_view)):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    q = (
        db.table("auto_message_sends")
        .select("id, lead_id, phone, name, event, source, product_raw, catalog_item_id, template_id, status, reason, send_at, sent_at, created_at")
        .eq("tenant_id", tenant_id)
    )
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", desc=True).limit(max(1, min(limit, 500))).execute().data or []

    item_ids = list({r["catalog_item_id"] for r in rows if r.get("catalog_item_id")})
    template_ids = list({r["template_id"] for r in rows if r.get("template_id")})
    items = {
        i["id"]: i["name"] for i in (
            db.table("catalog_items").select("id, name").eq("tenant_id", tenant_id).in_("id", item_ids).execute().data or []
        )
    } if item_ids else {}
    templates = {
        t["id"]: t["name"] for t in (
            db.table("message_templates").select("id, name").eq("tenant_id", tenant_id).in_("id", template_ids).execute().data or []
        )
    } if template_ids else {}
    for r in rows:
        r["product_name"] = items.get(r.get("catalog_item_id"))
        r["template_name"] = templates.get(r.get("template_id"))
    return {"sends": rows}
