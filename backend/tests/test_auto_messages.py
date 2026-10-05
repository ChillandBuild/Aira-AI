"""Auto-Messages end to end against the in-memory Supabase fake: payload parsing,
product matching (the "Konarc gets the Konarc template" requirement), rule
priority, duplicates, delays, failures, template components, and the public /
dashboard routes."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_and_role
from app.routes import auto_messages as routes
from app.services import auto_messages as svc
from tests.fake_supabase import FakeSupabase

T = "tenant-1"
OTHER = "tenant-2"


def _now_stamp():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db():
    d = FakeSupabase()
    d._stamp = _now_stamp
    d.storage.from_.return_value.get_public_url.side_effect = lambda path: f"https://cdn.example/{path}"
    return d


@pytest.fixture(autouse=True)
def _fake_lead_creation(db):
    """create_inbound_lead does scoring/assignment/follow-ups; here it only
    has to find-or-create the lead row by (tenant, phone)."""
    def fake_create(tenant_id, phone, source, *, name=None, opt_in_source=None, db=None, **_):
        from app.routes.upload import _normalize_phone
        normalized = _normalize_phone(phone)
        if not normalized:
            return None
        for r in db.rows("leads"):
            if r["tenant_id"] == tenant_id and r["phone"] == normalized:
                return r["id"]
        return db.add("leads", tenant_id=tenant_id, phone=normalized, name=name, source=source,
                      opt_in_source=opt_in_source, opted_out=False)["id"]
    with patch("app.services.inbound_lead.create_inbound_lead", side_effect=fake_create):
        yield


@pytest.fixture
def send():
    with patch("app.services.meta_cloud.send_template_message",
               new=AsyncMock(return_value={"messages": [{"id": "wamid.1"}]})) as m:
        yield m


def _template(db, name, tenant=T, status="APPROVED", **kw):
    return db.add("message_templates", tenant_id=tenant, name=name, language="en", status=status,
                  body_text=kw.pop("body_text", "Hi {{1}}, here are the details on {{2}}."), **kw)["id"]


def _item(db, name, tenant=T, **kw):
    return db.add("catalog_items", tenant_id=tenant, name=name, status=kw.pop("status", "ready"), aliases=kw.pop("aliases", []), **kw)["id"]


def _rule(db, event, template_id, item_id=None, tenant=T, **kw):
    return db.add("auto_message_rules", tenant_id=tenant, event=event, catalog_item_id=item_id,
                  template_id=template_id, delay_minutes=kw.pop("delay_minutes", 0), enabled=kw.pop("enabled", True),
                  variables=kw.pop("variables", []), button_param=kw.pop("button_param", None), **kw)["id"]


def _event(db, source="api", **data):
    data.setdefault("phone", "9876543210")
    data.setdefault("extra", {})
    data.setdefault("product_url", "")
    return asyncio.run(svc.handle_event(T, source, data, db=db))


def _sends(db):
    return db.rows("auto_message_sends")


# ---------------------------------------------------------------- parsing

def test_parse_accepts_common_field_names_and_keeps_extras():
    p = svc.parse_payload({"Mobile": "+91 98765 43210", "first_name": "Priya", "last_name": "R",
                           "Product_Name": "Konarc", "page_url": "https://x.in/konarc", "order_id": 991, "_hp": ""})
    assert p["phone"] == "+91 98765 43210" and p["name"] == "Priya R"
    assert p["product"] == "Konarc" and p["product_url"] == "https://x.in/konarc"
    assert p["extra"] == {"order_id": "991"}


def test_events_normalise_and_unknown_is_rejected():
    assert svc.normalize_event("Order Placed") == "purchased"
    assert svc.normalize_event("sign-up") == "signed_up"
    assert svc.normalize_event("") == "interested"
    assert svc.normalize_event("refund") is None


# ---------------------------------------------------------------- matching

ITEMS = [
    {"id": "konarc", "name": "Konarc", "aliases": []},
    {"id": "konarc-s", "name": "Konarc S", "aliases": ["konarcs"]},
    {"id": "rizta", "name": "Rizta", "aliases": ["ather rizta"]},
]


@pytest.mark.parametrize("sent,expected", [
    ("konarc", "konarc"),
    ("  KONARC S ", "konarc-s"),
    ("konarcs", "konarc-s"),
    ("Ather Konarc S 161 km", "konarc-s"),   # longest whole-word match wins
    ("I want the Ather Rizta", "rizta"),
    ("kon", None),                           # partial words never match
    ("Apex", None),
])
def test_match_product(sent, expected):
    item = svc.match_product(ITEMS, sent)
    assert (item or {}).get("id") == expected


# ---------------------------------------------------------------- the Konarc requirement

def test_each_product_gets_its_own_template_and_unknown_gets_default(db, send):
    konarc_t = _template(db, "konarc_details")
    rizta_t = _template(db, "rizta_details")
    default_t = _template(db, "thanks_for_interest")
    konarc = _item(db, "Konarc")
    rizta = _item(db, "Rizta")
    _rule(db, "interested", konarc_t, konarc)
    _rule(db, "interested", rizta_t, rizta)
    _rule(db, "interested", default_t)

    r1 = _event(db, phone="9876500001", name="Priya", product="Ather Konarc")
    r2 = _event(db, phone="9876500002", name="Arun", product="rizta")
    r3 = _event(db, phone="9876500003", name="Meena", product="Some new scooter")

    assert r1["matched_product"] == "Konarc" and r2["matched_product"] == "Rizta" and r3["matched_product"] is None
    sent_templates = [c.args[1] for c in send.call_args_list]
    assert sent_templates == ["konarc_details", "rizta_details", "thanks_for_interest"]
    assert [s["status"] for s in _sends(db)] == ["sent", "sent", "sent"]
    # body variables default to first name then product
    body = send.call_args_list[0].kwargs["components"][-1]
    assert [p["text"] for p in body["parameters"]] == ["Priya", "Konarc"]


def test_other_tenants_rules_and_products_are_never_used(db, send):
    their_t = _template(db, "theirs", tenant=OTHER)
    _rule(db, "interested", their_t, _item(db, "Konarc", tenant=OTHER), tenant=OTHER)
    r = _event(db, product="Konarc")
    assert r["matched_product"] is None and r["message_status"] == "skipped" and r["reason"] == "no_rule"
    send.assert_not_called()


def test_event_without_rule_is_logged_not_sent(db, send):
    _rule(db, "purchased", _template(db, "thanks"))
    r = _event(db, event_raw="interested", product="x")
    assert (r["message_status"], r["reason"]) == ("skipped", "no_rule")
    send.assert_not_called()
    assert db.rows("lead_notes")[0]["content"] == "Interested in x (via API)"


def test_unknown_event_and_bad_phone_are_ignored(db, send):
    assert _event(db, event_raw="refund")["status"] == "ignored"
    assert _event(db, phone="12")["status"] == "ignored"
    assert _sends(db) == []


def test_same_person_same_product_within_24h_is_sent_once(db, send):
    t = _template(db, "konarc_details")
    _rule(db, "interested", t, _item(db, "Konarc"))
    _rule(db, "interested", _template(db, "default"))
    _event(db, product="Konarc")
    second = _event(db, product="konarc")
    other_product = _event(db, product="Something else")
    assert (second["message_status"], second["reason"]) == ("skipped", "duplicate")
    assert other_product["message_status"] == "sent"
    assert send.call_count == 2


def test_duplicate_window_expires(db, send):
    _rule(db, "interested", _template(db, "t"))
    _event(db, product="A")
    _sends(db)[0]["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert _event(db, product="A")["message_status"] == "sent"


def test_delayed_message_waits_for_scheduler(db, send):
    _rule(db, "signed_up", _template(db, "welcome"), delay_minutes=5)
    r = _event(db, event_raw="signup")
    assert r["message_status"] == "queued"
    send.assert_not_called()

    with patch.object(svc, "get_supabase", return_value=db):
        assert asyncio.run(svc.process_due_sends()) == 0          # not due yet
        _sends(db)[0]["send_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        assert asyncio.run(svc.process_due_sends()) == 1
        assert asyncio.run(svc.process_due_sends()) == 0          # never sent twice
    assert _sends(db)[0]["status"] == "sent" and send.call_count == 1
    msg = db.rows("messages")[0]
    assert msg["reply_source"] == "automation" and msg["content"] == "[Auto-message: welcome]"


def test_opted_out_lead_is_skipped(db, send):
    _rule(db, "interested", _template(db, "t"))
    db.add("leads", tenant_id=T, phone="+919876543210", opted_out=True)
    r = _event(db)
    assert (r["message_status"], r["reason"]) == ("skipped", "opted_out")
    send.assert_not_called()


def test_rule_switched_off_while_queued_is_skipped(db, send):
    rule_id = _rule(db, "interested", _template(db, "t"), delay_minutes=10)
    _event(db)
    next(r for r in db.rows("auto_message_rules") if r["id"] == rule_id)["enabled"] = False
    _sends(db)[0]["send_at"] = _now_stamp()
    with patch.object(svc, "get_supabase", return_value=db):
        asyncio.run(svc.process_due_sends())
    assert (_sends(db)[0]["status"], _sends(db)[0]["reason"]) == ("skipped", "rule_removed_or_off")


def test_unapproved_template_and_meta_error_are_failures_with_reason(db, send):
    t = _template(db, "t")
    _rule(db, "interested", t)
    next(r for r in db.rows("message_templates") if r["id"] == t)["status"] = "PAUSED"
    r = _event(db)
    assert (r["message_status"], r["reason"]) == ("failed", "template_not_approved")

    next(r for r in db.rows("message_templates") if r["id"] == t)["status"] = "APPROVED"
    send.side_effect = HTTPException(status_code=400, detail="(#131026) Message undeliverable")
    r = _event(db, phone="9876500009")
    assert r["message_status"] == "failed" and "131026" in r["reason"]


# ---------------------------------------------------------------- components

def test_components_image_header_variables_fallbacks_and_dynamic_button(db, send):
    t = _template(db, "konarc_card", header_media_type="IMAGE", header_media_url="https://x/default.jpg",
                  body_text="Hi {{1}}, {{2}} starts at {{3}}. Order {{4}}.",
                  buttons=[{"type": "QUICK_REPLY", "text": "Call me"},
                           {"type": "URL", "text": "Book Test Ride", "url": "https://ather.example/{{1}}"}])
    item = _item(db, "Konarc", price_paise=9999900)
    db.add("catalog_media", tenant_id=T, catalog_item_id=item, storage_path="t/konarc-2.jpg", sort_order=2)
    db.add("catalog_media", tenant_id=T, catalog_item_id=item, storage_path="t/konarc-1.jpg", sort_order=1)
    _rule(db, "interested", t, item, variables=[
        {"source": "first_name", "fallback": "there"},
        {"source": "product"},
        {"source": "price", "fallback": "a great price"},
        {"source": "extra", "key": "order_id", "fallback": "soon"},
    ], button_param={"source": "text", "value": "konarc/test-ride"})

    _event(db, name="", product="Konarc")
    comps = send.call_args.kwargs["components"]
    assert comps[0] == {"type": "header", "parameters": [{"type": "image", "image": {"link": "https://cdn.example/t/konarc-1.jpg"}}]}
    assert [p["text"] for p in comps[1]["parameters"]] == ["there", "Konarc", "₹99,999", "soon"]
    assert comps[2] == {"type": "button", "sub_type": "url", "index": "1",
                        "parameters": [{"type": "text", "text": "konarc/test-ride"}]}


@pytest.mark.parametrize("paise,text", [(None, ""), (50000, "₹500"), (9999900, "₹99,999"), (12345678900, "₹12,34,56,789")])
def test_format_inr(paise, text):
    assert svc.format_inr(paise) == text


# ---------------------------------------------------------------- routes

@pytest.fixture
def client(db):
    routes._per_ip.reset()
    routes._per_tenant.reset()
    app = FastAPI()
    app.include_router(routes.public_router, prefix="/api/v1/auto-messages")
    app.include_router(routes.router, prefix="/api/v1/auto-messages")
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": T, "role": "owner", "permissions": []}
    db.add("app_settings", tenant_id=T, key=routes.TOKEN_KEY, value="tok-123")
    with patch.object(routes, "get_supabase", return_value=db), patch.object(svc, "get_supabase", return_value=db):
        yield TestClient(app)


def test_ingest_rejects_unknown_token(client):
    r = client.post("/api/v1/auto-messages/in/nope", json={"phone": "9876543210"})
    assert r.status_code == 401


def test_ingest_json_from_zapier_sends_and_is_cors_readable(client, db, send):
    _rule(db, "purchased", _template(db, "thank_you"))
    r = client.post("/api/v1/auto-messages/in/tok-123", json={"mobile": "9876543210", "event": "order", "amount": "450"})
    assert r.status_code == 200 and r.json()["message_status"] == "sent"
    assert r.headers["access-control-allow-origin"] == "*"
    assert _sends(db)[0]["source"] == "api" and _sends(db)[0]["extra"] == {"amount": "450"}


def test_website_form_post_is_tagged_website_and_honeypot_drops_bots(client, db, send):
    _rule(db, "interested", _template(db, "t"))
    bot = client.post("/api/v1/auto-messages/in/tok-123", data={"phone": "9876543210", "_hp": "spam", "_src": "form"})
    assert bot.status_code == 200 and _sends(db) == []
    ok = client.post("/api/v1/auto-messages/in/tok-123", data={"phone": "9876543210", "_hp": "", "_src": "form"})
    assert ok.status_code == 200 and _sends(db)[0]["source"] == "website"
    assert db.rows("leads")[0]["opt_in_source"] == "website_form"


def test_ingest_bad_input_and_rate_limit(client):
    assert client.post("/api/v1/auto-messages/in/tok-123", json={"phone": "1"}).status_code == 422
    assert client.post("/api/v1/auto-messages/in/tok-123", content="not json",
                       headers={"content-type": "application/json"}).status_code == 400
    form = [client.post("/api/v1/auto-messages/in/tok-123", data={"phone": "1", "_src": "form"}).status_code for _ in range(11)]
    assert form[-1] == 429


def test_app_server_sending_many_customers_from_one_ip_is_not_throttled(client, db, send):
    """An app/billing backend posts every customer from the same IP; only the
    website form is limited per IP."""
    _rule(db, "signed_up", _template(db, "welcome"))
    codes = [
        client.post("/api/v1/auto-messages/in/tok-123", json={"phone": f"98765{i:05d}", "event": "signup"}).status_code
        for i in range(30)
    ]
    assert codes == [200] * 30 and send.call_count == 30


def test_form_script_embeds_endpoint_and_this_tenants_products_only(client, db):
    _item(db, "Konarc")
    _item(db, "Old model", status="draft")
    _item(db, "Secret", tenant=OTHER)
    js = client.get("/api/v1/auto-messages/in/tok-123/form.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert '/api/v1/auto-messages/in/tok-123";' in js.text
    assert '["Konarc"]' in js.text and "Secret" not in js.text and "Old model" not in js.text
    assert "no longer valid" in client.get("/api/v1/auto-messages/in/bad/form.js").text


def test_rules_crud_validates_template_and_one_rule_per_product(client, db):
    approved, pending = _template(db, "ok"), _template(db, "pending", status="PENDING")
    item = _item(db, "Konarc")
    base = "/api/v1/auto-messages/rules"
    assert client.post(base, json={"event": "interested", "template_id": pending}).status_code == 400
    assert client.post(base, json={"event": "interested", "template_id": _template(db, "x", tenant=OTHER)}).status_code == 404
    assert client.post(base, json={"event": "nope", "template_id": approved}).status_code == 422
    created = client.post(base, json={"event": "interested", "template_id": approved, "catalog_item_id": item,
                                      "delay_minutes": 5, "variables": [{"source": "first_name", "fallback": "there"}]})
    assert created.status_code == 200
    assert client.post(base, json={"event": "interested", "template_id": approved, "catalog_item_id": item}).status_code == 409
    assert client.post(base, json={"event": "interested", "template_id": approved}).status_code == 200  # default rule
    rid = created.json()["id"]
    assert client.patch(f"{base}/{rid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"{base}/{rid}").status_code == 200
    assert len(client.get(base).json()["rules"]) == 1


def test_quick_add_from_shop_counter(client, db, send):
    t = _template(db, "thanks_for_buying")
    item = _item(db, "Konarc")
    _rule(db, "purchased", t, item)
    r = client.post("/api/v1/auto-messages/quick-add", json={"name": "Ravi", "phone": "98765 43210", "catalog_item_id": item})
    assert r.status_code == 200 and r.json()["message_status"] == "sent"
    assert _sends(db)[0]["source"] == "store" and db.rows("leads")[0]["opt_in_source"] == "offline_event"
    assert client.post("/api/v1/auto-messages/quick-add", json={"phone": "123456"}).status_code == 400


def test_aliases_and_send_log(client, db, send):
    item = _item(db, "Konarc")
    r = client.put(f"/api/v1/auto-messages/products/{item}/aliases", json={"aliases": [" konarc s ", "Konarc S", ""]})
    assert r.json()["aliases"] == ["konarc s"]
    _rule(db, "interested", _template(db, "konarc_details"), item)
    client.post("/api/v1/auto-messages/in/tok-123", json={"phone": "9876543210", "product": "Konarc S"})
    log = client.get("/api/v1/auto-messages/sends").json()["sends"]
    assert log[0]["product_name"] == "Konarc" and log[0]["template_name"] == "konarc_details"


def test_templates_endpoint_lists_only_approved_with_variable_info(client, db):
    _template(db, "pending", status="PENDING")
    _template(db, "card", body_text="Hi {{1}} {{2}} {{1}}",
              buttons=[{"type": "URL", "text": "Book", "url": "https://x/{{1}}"}, {"type": "QUICK_REPLY", "text": "Stop"}])
    out = client.get("/api/v1/auto-messages/templates").json()["templates"]
    assert [t["name"] for t in out] == ["card"]
    assert out[0]["variable_count"] == 2 and out[0]["has_dynamic_button"] is True and out[0]["buttons"] == ["Book", "Stop"]


# ---------------------------------------------------------------- review fixes

def test_links_from_customers_never_reach_the_template_and_whitespace_is_flattened(db, send):
    _rule(db, "interested", _template(db, "t", body_text="Hi {{1}}, about {{2}}: {{3}}"), variables=[
        {"source": "first_name", "fallback": "there"},
        {"source": "product", "fallback": "our products"},
        {"source": "extra", "key": "note", "fallback": "see you"},
    ])
    _event(db, name="win.com prize", product="free at https://evil.example", extra={"note": "line1\n\tline2   end"})
    params = [p["text"] for p in send.call_args.kwargs["components"][-1]["parameters"]]
    assert params == ["there", "our products", "line1 line2 end"]


def test_button_suffix_is_url_encoded(db, send):
    t = _template(db, "t", body_text="Hi", buttons=[{"type": "URL", "text": "Book", "url": "https://x.example/{{1}}"}])
    _rule(db, "interested", t, _item(db, "Konarc S"))
    _event(db, product="Konarc S")
    assert send.call_args.kwargs["components"][-1]["parameters"][0]["text"] == "Konarc%20S"


def test_send_interrupted_mid_flight_is_marked_failed_not_resent(db, send):
    _rule(db, "interested", _template(db, "t"), delay_minutes=5)
    _event(db)
    row = _sends(db)[0]
    row.update(status="sending", send_at=(datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat())
    with patch.object(svc, "get_supabase", return_value=db):
        assert asyncio.run(svc.process_due_sends()) == 0
    assert (row["status"], row["reason"]) == ("failed", "interrupted")
    send.assert_not_called()


def test_lead_schema_accepts_the_new_sources():
    from app.models.schemas import LeadBase
    for source in ("website", "api", "store"):
        assert LeadBase(source=source).source == source


def test_counter_staff_without_settings_access_can_use_the_counter(db, send):
    routes._per_ip.reset()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/auto-messages")
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": T, "role": "telecaller", "permissions": ["leads.manage"]}
    _item(db, "Konarc")
    _item(db, "Draft thing", status="draft")
    with patch.object(routes, "get_supabase", return_value=db), patch.object(svc, "get_supabase", return_value=db):
        c = TestClient(app)
        assert [p["name"] for p in c.get("/api/v1/auto-messages/quick-add/products").json()["products"]] == ["Konarc"]
        assert c.post("/api/v1/auto-messages/quick-add", json={"phone": "9876543210"}).status_code == 200
        assert len(c.get("/api/v1/auto-messages/quick-add/recent").json()["sends"]) == 1
        assert c.get("/api/v1/auto-messages/products").status_code == 403
        assert c.get("/api/v1/auto-messages/sends").status_code == 403


def test_rate_limit_key_ignores_client_supplied_forwarded_for():
    from starlette.requests import Request as StarletteRequest

    def req(headers):
        return StarletteRequest({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()], "client": ("10.0.0.1", 1)})
    assert routes._client_ip(req({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})) == "203.0.113.9"
    assert routes._client_ip(req({"cf-connecting-ip": "198.51.100.7", "x-forwarded-for": "1.2.3.4"})) == "198.51.100.7"
    assert routes._client_ip(req({})) == "10.0.0.1"
