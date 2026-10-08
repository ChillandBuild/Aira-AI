"""Per-account partner send mode: each account's app calls send-template ONE way, "template"
(a template_code, the AstroTamil call) or "event". No setting means "template", so an account
that never touched the Developer page behaves exactly as before. A call in the other shape is
refused with 400 wrong_mode, and nothing is sent or logged. Setting key partner_send_mode in
app_settings (no migration); GET/PUT /api/v1/intake/partner/send-mode."""
import hashlib
import hmac
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_and_role
from app.routes import intake as routes
from app.routes.intake import public_router
from app.services import partner_send_mode as mode_svc
from tests.fake_supabase import FakeSupabase

TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
OTHER = "11111111-2d34-4b67-8d69-f83f52e4fb6c"
SECRET = "bridge-secret"
URL = "/api/v1/intake/partner/send-template"
LEGACY_URL = "/api/v1/expert-handoff/partner/send-template"
MODE_URL = "/api/v1/intake/partner/send-mode"

TEMPLATE_MODE_REFUSES_EVENT = (
    "This account sends by template ID. To send events, switch to Event on the Developer page."
)
EVENT_MODE_REFUSES_TEMPLATE = (
    "This account sends by event. To send template IDs, switch to Template ID on the Developer page."
)

public_app = FastAPI()
public_app.include_router(public_router, prefix="/api/v1/intake")
legacy_app = FastAPI()
legacy_app.include_router(public_router, prefix="/api/v1/expert-handoff")


@pytest.fixture
def db():
    d = FakeSupabase()
    d.add("phone_numbers", tenant_id=TENANT, role="primary", meta_phone_number_id="pnid-primary")
    template = d.add(
        "message_templates", tenant_id=TENANT, name="order_shipped", language="en", status="APPROVED",
        body_text="Hi {{1}}, order {{2}} has shipped.", short_code="407940",
        header_text=None, buttons=[],
    )
    d.add("auto_message_rules", tenant_id=TENANT, event="purchased", template_id=template["id"],
          enabled=True, delay_minutes=0, variables=[], button_param=None)
    return d


def _set_mode(db, mode, tenant=TENANT):
    db.add("app_settings", tenant_id=tenant, key=mode_svc.KEY, value=mode, is_secret=False)


def _code_body(**over):
    body = {"tenant_id": TENANT, "template_code": "407940", "phone": "919876543210",
            "variables": ["Rajan", "#5412"], "reference": "question:5412"}
    body.update(over)
    return body


def _event_body(**over):
    body = {"tenant_id": TENANT, "phone": "919876543210", "event": "purchased", "name": "Priya Raman",
            "extra": {"order_id": "A-77"}, "reference": "order:77"}
    body.update(over)
    return body


def _post(body, db, url=URL, the_app=public_app):
    raw = json.dumps(body).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"x-anril-signature": f"sha256={sig}", "content-type": "application/json"}
    send = AsyncMock(return_value={"messages": [{"id": "wamid.M1"}]})
    with patch("app.routes.intake.astro_bridge.get_bridge_secret", return_value=SECRET), \
         patch("app.db.supabase.get_supabase", return_value=db), \
         patch("app.services.meta_cloud.send_template_message", send):
        res = TestClient(the_app).post(url, content=raw, headers=headers)
    return res, send


def _nothing_happened(db, send):
    send.assert_not_awaited()
    assert db.rows("auto_message_sends") == []


# ------------------------------------------------------------------ template mode (the default)

def test_no_setting_means_template_mode_and_the_response_is_unchanged(db):
    res, send = _post(_code_body(), db)
    assert res.status_code == 200
    assert res.json() == {"ok": True, "message_id": "wamid.M1",
                          "template": {"code": "407940", "name": "order_shipped", "language": "en"}}
    send.assert_awaited_once()


def test_no_setting_and_neither_field_keeps_the_old_message_byte_for_byte(db):
    body = _code_body()
    del body["template_code"]
    res, send = _post(body, db)
    assert res.status_code == 400
    assert res.json() == {"ok": False, "code": "invalid_request",
                          "error": "template_code is required and variables must be a list"}
    _nothing_happened(db, send)


def test_template_mode_refuses_an_event_call_and_sends_and_logs_nothing(db):
    res, send = _post(_event_body(), db)
    assert res.status_code == 400
    assert res.json() == {"ok": False, "code": "wrong_mode", "error": TEMPLATE_MODE_REFUSES_EVENT}
    _nothing_happened(db, send)


def test_an_explicit_template_setting_behaves_like_no_setting(db):
    _set_mode(db, "template")
    assert _post(_code_body(), db)[0].status_code == 200
    logged = len(db.rows("auto_message_sends"))
    res, send = _post(_event_body(), db)
    assert res.json()["code"] == "wrong_mode"
    send.assert_not_awaited()
    assert len(db.rows("auto_message_sends")) == logged


def test_template_mode_refuses_a_call_carrying_both_fields(db):
    res, send = _post(_event_body(template_code="407940", variables=["a", "b"]), db)
    assert res.status_code == 400 and res.json()["code"] == "wrong_mode"
    assert db.rows("auto_message_sends") == []
    send.assert_not_awaited()


def test_template_mode_ignores_an_empty_event_field(db):
    res, _ = _post(_code_body(event=""), db)
    assert res.status_code == 200 and res.json()["template"]["code"] == "407940"


# ------------------------------------------------------------------ event mode

def test_event_mode_sends_the_events_template(db):
    _set_mode(db, "event")
    res, send = _post(_event_body(), db)
    assert res.status_code == 200
    assert res.json()["event"] == "purchased" and res.json()["message_id"] == "wamid.M1"
    send.assert_awaited_once()
    [row] = db.rows("auto_message_sends")
    assert (row["source"], row["event"], row["status"]) == ("partner", "purchased", "sent")


def test_event_mode_refuses_a_template_code_call_and_sends_nothing(db):
    _set_mode(db, "event")
    res, send = _post(_code_body(), db)
    assert res.status_code == 400
    assert res.json() == {"ok": False, "code": "wrong_mode", "error": EVENT_MODE_REFUSES_TEMPLATE}
    _nothing_happened(db, send)


def test_event_mode_refuses_a_call_carrying_both_fields(db):
    _set_mode(db, "event")
    res, send = _post(_event_body(template_code="407940", variables=["a", "b"]), db)
    assert res.status_code == 400 and res.json()["code"] == "wrong_mode"
    assert res.json()["error"] == EVENT_MODE_REFUSES_TEMPLATE
    _nothing_happened(db, send)


@pytest.mark.parametrize("missing", [None, ""])
def test_event_mode_without_an_event_is_400_invalid_request(db, missing):
    _set_mode(db, "event")
    body = _event_body()
    if missing is None:
        del body["event"]
    else:
        body["event"] = missing
    res, send = _post(body, db)
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_request" and res.json()["ok"] is False
    _nothing_happened(db, send)


def test_event_mode_keeps_its_own_errors(db):
    _set_mode(db, "event")
    unknown, _ = _post(_event_body(event="not_an_event"), db)
    assert (unknown.status_code, unknown.json()["code"]) == (400, "unknown_event")
    db.table("auto_message_rules").delete().execute()
    no_rule, _ = _post(_event_body(), db)
    assert (no_rule.status_code, no_rule.json()["code"]) == (409, "no_rule")


# ------------------------------------------------------------------ the mode is read safely

def test_a_failed_settings_read_falls_back_to_template_and_warns(db, caplog):
    _set_mode(db, "event")  # would be event mode if the read worked
    real_table = db.table

    def table(name):
        if name == "app_settings":
            raise RuntimeError("connection reset")
        return real_table(name)

    with patch.object(db, "table", side_effect=table), caplog.at_level(logging.WARNING):
        res, send = _post(_code_body(), db)
    assert res.status_code == 200 and res.json()["template"]["code"] == "407940"
    send.assert_awaited_once()
    assert any("partner_send_mode" in r.getMessage() for r in caplog.records)


def test_a_stored_value_that_is_not_a_mode_counts_as_template(db):
    _set_mode(db, "carrier-pigeon")
    assert _post(_code_body(), db)[0].status_code == 200


def test_another_tenants_setting_does_not_change_this_tenants_mode(db):
    _set_mode(db, "event", tenant=OTHER)
    assert _post(_code_body(), db)[0].status_code == 200
    assert mode_svc.get_partner_send_mode(db, TENANT) == "template"
    assert mode_svc.get_partner_send_mode(db, OTHER) == "event"


def test_the_legacy_prefix_obeys_the_mode_too(db):
    res, send = _post(_event_body(), db, url=LEGACY_URL, the_app=legacy_app)
    assert res.status_code == 400 and res.json()["code"] == "wrong_mode"
    assert res.json()["error"] == TEMPLATE_MODE_REFUSES_EVENT
    send.assert_not_awaited()
    _set_mode(db, "event")
    res, send = _post(_code_body(), db, url=LEGACY_URL, the_app=legacy_app)
    assert res.status_code == 400 and res.json()["error"] == EVENT_MODE_REFUSES_TEMPLATE
    assert _post(_event_body(), db, url=LEGACY_URL, the_app=legacy_app)[0].status_code == 200


# ------------------------------------------------------------------ GET / PUT the setting

def _client(db, permissions, tenant=TENANT):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/intake")
    app.dependency_overrides[get_tenant_and_role] = lambda: {
        "tenant_id": tenant, "role": "admin", "user_id": "u-1", "permissions": permissions,
    }
    return TestClient(app)


def _api(db, client, method, **kw):
    with patch.object(routes, "get_supabase", return_value=db):
        return getattr(client, method)(MODE_URL, **kw)


def test_get_defaults_to_template(db):
    res = _api(db, _client(db, ["settings.view"]), "get")
    assert res.status_code == 200 and res.json() == {"mode": "template"}


def test_get_returns_the_saved_mode(db):
    _set_mode(db, "event")
    assert _api(db, _client(db, ["settings.view"]), "get").json() == {"mode": "event"}


def test_admin_can_switch_to_event_and_the_next_call_follows(db):
    admin = _client(db, ["settings.manage"])
    res = _api(db, admin, "put", json={"mode": "event"})
    assert res.status_code == 200 and res.json() == {"mode": "event"}
    assert _api(db, admin, "get").json() == {"mode": "event"}
    assert _post(_code_body(), db)[0].json()["code"] == "wrong_mode"
    assert _post(_event_body(), db)[0].status_code == 200
    back = _api(db, admin, "put", json={"mode": "template"})
    assert back.json() == {"mode": "template"}
    assert _post(_code_body(), db)[0].status_code == 200
    saved = [r for r in db.rows("app_settings") if r["key"] == mode_svc.KEY]
    assert len(saved) == 1  # upsert, not a second row


def test_put_writes_an_audit_row_for_the_callers_tenant(db):
    _api(db, _client(db, ["settings.manage"]), "put", json={"mode": "event"})
    [row] = db.rows("app_audit_logs")
    assert row["tenant_id"] == TENANT and row["action"] == "tenant.partner_send_mode_updated"
    assert row["actor_user_id"] == "u-1" and row["metadata"] == {"mode": "event", "previous": "template"}


@pytest.mark.parametrize("bad", [{"mode": "both"}, {"mode": ""}, {"mode": None}, {}, {"mode": "event", "tenant_id": OTHER}])
def test_put_rejects_a_bad_body_and_saves_nothing(db, bad):
    res = _api(db, _client(db, ["settings.manage"]), "put", json=bad)
    assert res.status_code == 422
    assert db.rows("app_settings") == []


def test_a_view_only_user_can_read_but_not_write(db):
    viewer = _client(db, ["settings.view"])
    assert _api(db, viewer, "get").status_code == 200
    res = _api(db, viewer, "put", json={"mode": "event"})
    assert res.status_code == 403
    assert db.rows("app_settings") == []


def test_a_user_without_settings_permissions_gets_403_both_ways(db):
    nobody = _client(db, ["auto_messages.view"])
    assert _api(db, nobody, "get").status_code == 403
    assert _api(db, nobody, "put", json={"mode": "event"}).status_code == 403


def test_put_only_writes_the_callers_own_tenant(db):
    _api(db, _client(db, ["settings.manage"], tenant=OTHER), "put", json={"mode": "event"})
    assert mode_svc.get_partner_send_mode(db, OTHER) == "event"
    assert mode_svc.get_partner_send_mode(db, TENANT) == "template"


def test_a_failed_save_is_a_500_that_says_nothing_changed(db):
    real_table = db.table

    def table(name):
        if name == "app_settings":
            raise RuntimeError("db down")
        return real_table(name)

    with patch.object(db, "table", side_effect=table):
        res = _api(db, _client(db, ["settings.manage"]), "put", json={"mode": "event"})
    assert res.status_code == 500
    assert res.json()["code"] == "setting_not_saved"
    assert "Nothing was changed" in res.json()["error"]
