"""Auto Messages v2: the Private Send guard, custom events, no quiet hours, summary,
paged send log, rule flags and the preview send. Reuses the fixtures of test_auto_messages."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routes import auto_messages as routes
from app.services import auto_messages as svc
from tests.test_auto_messages import (  # noqa: F401  (fixtures)
    OTHER, T, _event, _fake_lead_creation, _rule, _sends, _template, client, db, send,
)

BASE = "/api/v1/auto-messages"
IST = timezone(timedelta(hours=5, minutes=30))


def _custom(db, key="kundli_ready", label="Kundli ready", tenant=T):
    return db.add("auto_message_events", tenant_id=tenant, key=key, label=label, description=None)["id"]


def _private_send_key(db, tenant=T, status="active"):
    db.add("private_send_keys", tenant_id=tenant, key_prefix="aps_live_abcd", key_hash="h", status=status)


# ---------------------------------------------------------------- 1. Private Send guard

def test_ingest_is_refused_when_the_tenant_sends_from_its_own_server(client, db, send):
    _rule(db, "interested", _template(db, "t"))
    _private_send_key(db)
    r = client.post(f"{BASE}/in/tok-123", json={"phone": "9876543210"})
    assert r.status_code == 409
    assert r.json() == {"error": "This account sends from its own server", "code": "private_send_on"}
    assert r.headers["access-control-allow-origin"] == "*"
    assert _sends(db) == [] and db.rows("leads") == []
    send.assert_not_called()


def test_form_script_is_refused_when_the_tenant_sends_from_its_own_server(client, db):
    _private_send_key(db)
    r = client.get(f"{BASE}/in/tok-123/form.js")
    # A <script src> that gets JSON is a syntax error on the client's page: answer in JS.
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/javascript")
    assert "sends from its own server" in r.text and r.text.strip().startswith("/*") and r.text.strip().endswith("*/")
    assert r.headers["access-control-allow-origin"] == "*"


def test_a_revoked_or_other_tenants_key_does_not_block_ingest(client, db, send):
    _rule(db, "interested", _template(db, "t"))
    _private_send_key(db, status="revoked")
    _private_send_key(db, tenant=OTHER)
    assert client.post(f"{BASE}/in/tok-123", json={"phone": "9876543210"}).status_code == 200
    assert client.get(f"{BASE}/in/tok-123/form.js").status_code == 200


def test_setup_reports_private_send_on(client, db):
    assert client.get(f"{BASE}/setup").json()["private_send_on"] is False
    _private_send_key(db)
    body = client.get(f"{BASE}/setup").json()
    assert body["private_send_on"] is True and {"ingest_url", "form_script_url"} <= set(body)


def test_setup_without_a_token_still_reports_private_send_on(client, db):
    _private_send_key(db)
    with patch.object(routes, "get_setting", return_value=None):
        assert client.get(f"{BASE}/setup").json() == {"ingest_url": None, "form_script_url": None, "private_send_on": True}


# ---------------------------------------------------------------- 2. shop counter is gone

def test_quick_add_routes_are_removed(client):
    assert client.post(f"{BASE}/quick-add", json={"phone": "9876543210"}).status_code in (404, 405)
    assert client.get(f"{BASE}/quick-add/recent").status_code in (404, 405)


# ---------------------------------------------------------------- 3. custom events: validation

def test_builtin_and_aliases_still_resolve_without_a_database_lookup(db):
    assert svc.resolve_event(db, T, "Order Placed") == "purchased"
    assert svc.resolve_event(db, T, "") == "interested"
    assert svc.resolve_event(db, T, "refund") is None


def test_a_custom_key_resolves_only_for_its_own_tenant(db):
    _custom(db)
    assert svc.resolve_event(db, T, "kundli_ready") == "kundli_ready"
    assert svc.resolve_event(db, T, " Kundli_Ready ") == "kundli_ready"
    assert svc.resolve_event(db, OTHER, "kundli_ready") is None
    assert svc.resolve_event(db, T, "kundli") is None  # never guessed


def test_ingest_sends_the_custom_events_template(client, db, send):
    _custom(db)
    _rule(db, "kundli_ready", _template(db, "kundli_ready_msg", body_text="Hi {{1}}, your kundli is ready."))
    r = client.post(f"{BASE}/in/tok-123", json={"phone": "9876543210", "name": "Priya", "event": "kundli_ready"})
    assert r.status_code == 200 and r.json()["event"] == "kundli_ready" and r.json()["message_status"] == "sent"
    assert _sends(db)[0]["event"] == "kundli_ready"
    assert db.rows("lead_notes")[0]["content"] == "Kundli ready (via API)"


def test_ingest_of_an_event_the_tenant_does_not_have_is_rejected(client, db, send):
    _custom(db, tenant=OTHER)
    r = client.post(f"{BASE}/in/tok-123", json={"phone": "9876543210", "event": "kundli_ready"})
    assert r.status_code == 422 and r.json()["code"] == "ignored"
    assert _sends(db) == []


def test_rule_can_use_a_custom_key_but_not_an_unknown_one(client, db):
    approved = _template(db, "ok")
    _custom(db)
    rules = f"{BASE}/rules"
    assert client.post(rules, json={"event": "kundli_ready", "template_id": approved}).status_code == 200
    unknown = client.post(rules, json={"event": "refund", "template_id": approved})
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_event"
    assert client.post(rules, json={"event": "Bad Key!", "template_id": approved}).status_code == 422
    assert client.post(rules, json={"event": "kundli_ready", "template_id": approved}).status_code == 409


def test_another_tenants_custom_key_is_unknown_for_rules(client, db):
    _custom(db, tenant=OTHER)
    r = client.post(f"{BASE}/rules", json={"event": "kundli_ready", "template_id": _template(db, "ok")})
    assert r.status_code == 422 and r.json()["code"] == "unknown_event"


# ---------------------------------------------------------------- 3. custom events: routes

def test_list_events_returns_builtins_custom_and_the_limit(client, db):
    _custom(db)
    _custom(db, key="other_one", label="Other", tenant=OTHER)
    body = client.get(f"{BASE}/events").json()
    assert [e["key"] for e in body["builtin"]] == ["interested", "signed_up", "purchased"]
    assert set(body["builtin"][0]) == {"key", "label", "description"}
    assert [e["key"] for e in body["custom"]] == ["kundli_ready"]
    assert set(body["custom"][0]) == {"id", "key", "label", "description", "created_at"}
    assert body["limit"] == 20


@pytest.mark.parametrize("label,key", [
    ("Kundli ready", "kundli_ready"),
    ("  Kundli-Ready!! ", "kundli_ready"),
    ("Order   shipped - today", "order_shipped_today"),
    ("Free trial (7 days)", "free_trial_7_days"),
    ("A" * 80, "a" * 40),
])
def test_derive_event_key(label, key):
    assert svc.derive_event_key(label) == key


@pytest.mark.parametrize("label", ["", "   ", "!!!", "123 days", "_x", "a", "ऊ"])
def test_derive_event_key_rejects_what_cannot_be_a_key(label):
    assert svc.derive_event_key(label) is None


def test_create_event_derives_the_key_and_returns_the_row(client, db):
    r = client.post(f"{BASE}/events", json={"label": "Kundli ready", "description": "After the PDF is made"})
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "kundli_ready" and body["label"] == "Kundli ready"
    assert body["description"] == "After the PDF is made" and body["id"] and body["created_at"]
    assert db.rows("auto_message_events")[0]["tenant_id"] == T


def test_create_event_with_an_unusable_label_is_422_invalid_label(client):
    r = client.post(f"{BASE}/events", json={"label": "!!!"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_label"


@pytest.mark.parametrize("label", ["Interested", "Signed up", "purchased", "Order", "Sign-up"])
def test_create_event_clashing_with_a_builtin_or_its_alias_is_409(client, label):
    r = client.post(f"{BASE}/events", json={"label": label})
    assert r.status_code == 409 and r.json()["code"] == "event_exists"


def test_create_event_clashing_with_an_existing_custom_key_is_409(client, db):
    _custom(db)
    r = client.post(f"{BASE}/events", json={"label": "Kundli  Ready"})
    assert r.status_code == 409 and r.json()["code"] == "event_exists"
    assert client.post(f"{BASE}/events", json={"label": "Kundli ready"}).status_code == 409


def test_another_tenant_can_use_the_same_key(client, db):
    _custom(db, tenant=OTHER)
    assert client.post(f"{BASE}/events", json={"label": "Kundli ready"}).status_code == 200


def test_event_limit_is_20_per_tenant(client, db):
    for i in range(20):
        _custom(db, key=f"event_{i:02d}", label=f"Event {i}")
    _custom(db, key="theirs", label="Theirs", tenant=OTHER)
    r = client.post(f"{BASE}/events", json={"label": "One more"})
    assert r.status_code == 409 and r.json()["code"] == "event_limit"


def test_patch_event_changes_label_and_description_never_the_key(client, db):
    _custom(db)
    r = client.patch(f"{BASE}/events/kundli_ready", json={"label": "Kundli is ready", "description": "PDF done", "key": "x"})
    assert r.status_code == 200
    assert (r.json()["key"], r.json()["label"], r.json()["description"]) == ("kundli_ready", "Kundli is ready", "PDF done")
    cleared = client.patch(f"{BASE}/events/kundli_ready", json={"description": None})
    assert cleared.json()["description"] is None and cleared.json()["label"] == "Kundli is ready"


def test_patch_event_errors(client, db):
    _custom(db, tenant=OTHER)
    assert client.patch(f"{BASE}/events/kundli_ready", json={"label": "x"}).status_code == 404
    assert client.patch(f"{BASE}/events/interested", json={"label": "x"}).status_code == 400
    _custom(db)
    assert client.patch(f"{BASE}/events/kundli_ready", json={}).status_code == 400
    assert client.patch(f"{BASE}/events/kundli_ready", json={"label": ""}).status_code == 422


def test_delete_event_removes_its_rule_and_keeps_old_sends(client, db, send):
    _custom(db)
    _custom(db, key="keep_me", label="Keep me")
    _rule(db, "kundli_ready", _template(db, "t"))
    _rule(db, "keep_me", _template(db, "t2"))
    _event(db, event_raw="kundli_ready")
    r = client.delete(f"{BASE}/events/kundli_ready")
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert [e["key"] for e in db.rows("auto_message_events")] == ["keep_me"]
    assert [x["event"] for x in db.rows("auto_message_rules")] == ["keep_me"]
    assert _sends(db)[0]["event"] == "kundli_ready"


def test_delete_event_errors(client, db):
    assert client.delete(f"{BASE}/events/interested").status_code == 400
    assert client.delete(f"{BASE}/events/nope").status_code == 404
    _custom(db, tenant=OTHER)
    assert client.delete(f"{BASE}/events/kundli_ready").status_code == 404
    assert len(db.rows("auto_message_events")) == 1


def test_event_writes_need_auto_messages_manage(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies.tenant import get_tenant_and_role
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": T, "role": "telecaller", "permissions": ["auto_messages.view"]}
    with patch.object(routes, "get_supabase", return_value=db), patch.object(svc, "get_supabase", return_value=db):
        c = TestClient(app)
        assert c.get(f"{BASE}/events").status_code == 200
        assert c.post(f"{BASE}/events", json={"label": "Kundli ready"}).status_code == 403
        assert c.patch(f"{BASE}/events/kundli_ready", json={"label": "x"}).status_code == 403
        assert c.delete(f"{BASE}/events/kundli_ready").status_code == 403


# ---------------------------------------------------------------- 4. no quiet hours, no waiting

def _ist(hour, minute=0, day=7):
    return datetime(2026, 10, day, hour, minute, tzinfo=IST).astimezone(timezone.utc)


def _at(moment):
    return patch.object(svc, "_utcnow", return_value=moment)


def test_quiet_hours_are_gone_from_the_engine():
    for name in ("apply_quiet_hours", "QUIET_STATE", "QUIET_HOURS_BUNDLE", "QUIET_START", "QUIET_END",
                 "QUIET_CATEGORIES", "_is_duplicate", "DUPLICATE_WINDOW"):
        assert not hasattr(svc, name), name


@pytest.mark.parametrize("category", ["MARKETING", "UTILITY", "AUTHENTICATION"])
@pytest.mark.parametrize("hour", [3, 11, 22])
def test_every_category_is_sent_right_away_at_any_hour(db, send, category, hour):
    _rule(db, "interested", _template(db, "offer", category=category))
    with _at(_ist(hour, 40)):
        r = _event(db)
    assert (r["message_status"], r["reason"]) == ("sent", None)
    send.assert_called_once()
    assert datetime.fromisoformat(_sends(db)[0]["send_at"]) == _ist(hour, 40)


def test_a_stale_queued_marketing_row_is_sent_at_night_by_the_scheduler(db, send):
    rule = _rule(db, "interested", _template(db, "offer", category="MARKETING"))
    db.add("auto_message_sends", tenant_id=T, rule_id=rule, phone="+919876543210", event="interested",
           source="api", status="queued", send_at=_ist(14, 5).isoformat(), extra={})
    with patch.object(svc, "get_supabase", return_value=db), _at(_ist(22, 10)):
        assert asyncio.run(svc.process_due_sends()) == 1
    row = _sends(db)[0]
    assert (row["status"], row["reason"]) == ("sent", None)


# ---------------------------------------------------------------- 4b. partner rows in the log

def _partner_row(db, status="sent", event=None, tenant=T, **kw):
    return db.add("auto_message_sends", tenant_id=tenant, event=event, status=status, phone="+919876543210",
                  source="partner", lead_id=None, **kw)


def test_sends_route_lists_partner_rows_with_a_null_event(client, db):
    t = _template(db, "kundli_msg")
    _partner_row(db, template_id=t, created_at="2026-10-01T00:00:01+00:00")
    _partner_row(db, event="kundli_ready", template_id=t, created_at="2026-10-01T00:00:02+00:00")
    body = client.get(f"{BASE}/sends").json()
    assert body["has_more"] is False
    assert [(r["source"], r["event"]) for r in body["sends"]] == [("partner", "kundli_ready"), ("partner", None)]
    assert {r["template_name"] for r in body["sends"]} == {"kundli_msg"}
    assert client.get(f"{BASE}/sends?event=kundli_ready").json()["sends"][0]["event"] == "kundli_ready"
    assert len(client.get(f"{BASE}/sends?status=sent").json()["sends"]) == 2


def test_summary_counts_partner_rows(client, db):
    _partner_row(db, "sent")
    _partner_row(db, "failed", reason="meta rejected")
    assert client.get(f"{BASE}/summary").json() == {"sent": 1, "failed": 1, "skipped": 0}


def test_rules_has_sent_ignores_a_partner_row_with_a_null_event(client, db):
    _rule(db, "interested", _template(db, "ok"))
    _partner_row(db, "sent")  # event NULL
    assert client.get(f"{BASE}/rules").json()["rules"][0]["has_sent"] is False
    assert svc.sent_event_keys(db, T) == set()


# ---------------------------------------------------------------- 5. rules list flags

def test_rules_carry_has_sent_and_template_approved(client, db):
    ok = _template(db, "ok")
    lost = _template(db, "lost", status="PAUSED")
    _custom(db)
    _rule(db, "interested", ok)
    _rule(db, "purchased", lost)
    _rule(db, "kundli_ready", ok)
    db.add("auto_message_sends", tenant_id=T, event="interested", status="sent", phone="1", source="api")
    db.add("auto_message_sends", tenant_id=T, event="purchased", status="failed", phone="1", source="api")
    db.add("auto_message_sends", tenant_id=OTHER, event="kundli_ready", status="sent", phone="1", source="api")
    rules = {r["event"]: r for r in client.get(f"{BASE}/rules").json()["rules"]}
    assert (rules["interested"]["has_sent"], rules["interested"]["template_approved"]) == (True, True)
    assert (rules["purchased"]["has_sent"], rules["purchased"]["template_approved"]) == (False, False)
    assert (rules["kundli_ready"]["has_sent"], rules["kundli_ready"]["template_approved"]) == (False, True)


def test_rules_flags_use_one_template_query_and_one_sends_lookup(client, db):
    t = _template(db, "ok")
    for event in ("interested", "signed_up", "purchased"):
        _rule(db, event, t)
    calls = []
    real_table = db.table
    db.table = lambda name: (calls.append(name), real_table(name))[1]
    client.get(f"{BASE}/rules")
    assert calls.count("message_templates") == 1
    assert calls.count("auto_message_sends") == 0  # the sent lookup is a single rpc


def test_rules_list_without_rules_makes_no_extra_lookups(client, db):
    assert client.get(f"{BASE}/rules").json() == {"rules": []}


# ---------------------------------------------------------------- 5. monthly summary

def _send_row(db, status, created_at, event="interested", tenant=T):
    return db.add("auto_message_sends", tenant_id=tenant, event=event, status=status, phone="1",
                  source="api", created_at=created_at.astimezone(timezone.utc).isoformat())


def test_summary_counts_this_calendar_month_in_ist(client, db):
    now = datetime(2026, 10, 15, 12, 0, tzinfo=IST)
    _send_row(db, "sent", datetime(2026, 10, 1, 0, 5, tzinfo=IST))
    _send_row(db, "sent", datetime(2026, 10, 14, 9, 0, tzinfo=IST))
    _send_row(db, "failed", datetime(2026, 10, 14, 9, 0, tzinfo=IST))
    _send_row(db, "skipped", datetime(2026, 10, 2, 9, 0, tzinfo=IST), event="kundli_ready")
    _send_row(db, "skipped", datetime(2026, 10, 3, 9, 0, tzinfo=IST))
    _send_row(db, "queued", datetime(2026, 10, 3, 9, 0, tzinfo=IST))      # not counted
    _send_row(db, "sent", datetime(2026, 9, 30, 23, 59, tzinfo=IST))      # last month in IST
    _send_row(db, "sent", datetime(2026, 11, 1, 0, 0, tzinfo=IST))        # next month
    _send_row(db, "sent", datetime(2026, 10, 5, 9, 0, tzinfo=IST), tenant=OTHER)
    with patch.object(routes, "_utcnow", return_value=now.astimezone(timezone.utc)):
        assert client.get(f"{BASE}/summary").json() == {"sent": 2, "failed": 1, "skipped": 2}


def test_summary_month_edge_uses_ist_not_utc(client, db):
    # 31 Oct 19:00 UTC is 1 Nov 00:30 IST: it belongs to November.
    _send_row(db, "sent", datetime(2026, 10, 31, 19, 0, tzinfo=timezone.utc))
    with patch.object(routes, "_utcnow", return_value=datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)):
        assert client.get(f"{BASE}/summary").json()["sent"] == 1
    with patch.object(routes, "_utcnow", return_value=datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)):
        assert client.get(f"{BASE}/summary").json()["sent"] == 0


def test_summary_is_zero_when_nothing_was_sent(client):
    assert client.get(f"{BASE}/summary").json() == {"sent": 0, "failed": 0, "skipped": 0}


# ---------------------------------------------------------------- 5. paged send log

def _seed_sends(db, n, event="interested", status="sent"):
    for i in range(n):
        db.add("auto_message_sends", tenant_id=T, event=event, status=status, phone=f"98{i:08d}", source="api",
               created_at=f"2026-10-01T00:00:{i:02d}+00:00")


def test_sends_default_page_is_10_newest_first_with_has_more(client, db):
    _seed_sends(db, 12)
    body = client.get(f"{BASE}/sends").json()
    assert len(body["sends"]) == 10 and body["has_more"] is True
    assert body["sends"][0]["phone"] == "9800000011"


def test_sends_offset_and_limit_page_through_the_log(client, db):
    _seed_sends(db, 12)
    page2 = client.get(f"{BASE}/sends?limit=10&offset=10").json()
    assert [s["phone"] for s in page2["sends"]] == ["9800000001", "9800000000"] and page2["has_more"] is False
    exact = client.get(f"{BASE}/sends?limit=12").json()
    assert len(exact["sends"]) == 12 and exact["has_more"] is False


def test_sends_limit_is_capped_at_50_and_floored_at_1(client, db):
    _seed_sends(db, 60)
    big = client.get(f"{BASE}/sends?limit=500").json()
    assert len(big["sends"]) == 50 and big["has_more"] is True
    assert len(client.get(f"{BASE}/sends?limit=0").json()["sends"]) == 1
    assert len(client.get(f"{BASE}/sends?offset=-5").json()["sends"]) == 10


def test_sends_filter_by_event_and_status_and_keep_other_tenants_out(client, db):
    _seed_sends(db, 3, event="interested")
    _seed_sends(db, 2, event="kundli_ready", status="failed")
    db.add("auto_message_sends", tenant_id=OTHER, event="kundli_ready", status="failed", phone="1", source="api")
    both = client.get(f"{BASE}/sends?event=kundli_ready&status=failed").json()["sends"]
    assert len(both) == 2 and {s["event"] for s in both} == {"kundli_ready"}
    assert len(client.get(f"{BASE}/sends?event=interested").json()["sends"]) == 3
    assert len(client.get(f"{BASE}/sends?status=failed").json()["sends"]) == 2


# ---------------------------------------------------------------- 5. preview send

@pytest.fixture(autouse=True)
def _reset_preview_limit():
    routes._preview_limiter.reset()


def _preview(client, rule_id, phone="98765 43210"):
    return client.post(f"{BASE}/rules/{rule_id}/preview", json={"phone": phone})


def test_preview_sends_the_template_with_sample_values_and_writes_nothing(client, db, send):
    t = _template(db, "kundli_msg", body_text="Hi {{1}}, report {{2}} for {{3}} is ready: {{4}}",
                  buttons=[{"type": "URL", "text": "Open", "url": "https://x.example/{{1}}"}])
    rid = _rule(db, "interested", t, variables=[
        {"source": "first_name"}, {"source": "extra", "key": "order_id"},
        {"source": "text", "value": "Priya's chart"}, {"source": "extra", "key": "report_url"}],
        button_param={"source": "extra", "key": "report_url"})
    r = _preview(client, rid)
    assert r.status_code == 200 and r.json() == {"status": "sent", "reason": None}
    assert send.call_args.args[:3] == ("+919876543210", "kundli_msg", "en")
    body, button = send.call_args.kwargs["components"]
    assert [p["text"] for p in body["parameters"]] == ["Priya", "order_id", "Priya's chart", "report_url"]
    assert button["parameters"][0]["text"] == "report_url"
    assert db.rows("leads") == [] and _sends(db) == [] and db.rows("messages") == [] and db.rows("lead_notes") == []


def test_preview_with_a_bad_phone_is_422_and_sends_nothing(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    r = _preview(client, rid, phone="12345")
    assert r.status_code == 422 and r.json()["code"] == "invalid_phone"
    send.assert_not_called()


def test_preview_of_a_missing_or_other_tenants_rule_is_404(client, db, send):
    theirs = _rule(db, "interested", _template(db, "t", tenant=OTHER), tenant=OTHER)
    assert _preview(client, theirs).status_code == 404
    assert _preview(client, "nope").status_code == 404
    send.assert_not_called()


def test_preview_with_an_unapproved_template_fails_in_plain_words(client, db, send):
    t = _template(db, "t")
    rid = _rule(db, "interested", t)
    next(x for x in db.rows("message_templates") if x["id"] == t)["status"] = "PAUSED"
    body = _preview(client, rid).json()
    assert body["status"] == "failed" and "approved" in body["reason"].lower()
    send.assert_not_called()


def test_preview_meta_failure_comes_back_as_failed_with_a_reason(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    send.side_effect = HTTPException(status_code=400, detail='{"error":{"code":131026,"message":"Message undeliverable"}}')
    body = _preview(client, rid).json()
    assert body["status"] == "failed" and "WhatsApp" in body["reason"]
    assert _sends(db) == []


def test_preview_unexpected_error_is_failed_not_a_500(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    send.side_effect = RuntimeError("boom")
    assert _preview(client, rid).json()["status"] == "failed"


def test_preview_is_limited_to_5_a_minute_per_tenant(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    codes = [_preview(client, rid).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert send.call_count == 5
    assert _preview(client, rid).json()["code"] == "rate_limited"


def test_preview_needs_settings_manage(db, send):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies.tenant import get_tenant_and_role
    rid = _rule(db, "interested", _template(db, "t"))
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": T, "role": "telecaller", "permissions": ["auto_messages.view"]}
    with patch.object(routes, "get_supabase", return_value=db), patch.object(svc, "get_supabase", return_value=db):
        assert _preview(TestClient(app), rid).status_code == 403
    send.assert_not_called()


# ---------------------------------------------------------------- 6. preview audit trail + daily cap

PREVIEW_DAILY_CAP = 20


def _audit_rows(db, action="auto_messages.preview_sent", tenant=T):
    return [r for r in db.rows("app_audit_logs") if r["action"] == action and r["tenant_id"] == tenant]


def _seed_preview_audits(db, n, created_at, tenant=T, action="auto_messages.preview_sent"):
    for _ in range(n):
        db.add("app_audit_logs", tenant_id=tenant, action=action, target_type="auto_message_rule",
               metadata={}, created_at=created_at)


def _ist_midnight_utc():
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    return now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def test_preview_writes_an_audit_event_with_only_the_last_4_digits(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    assert _preview(client, rid).json()["status"] == "sent"
    [event] = _audit_rows(db)
    assert event["target_type"] == "auto_message_rule" and event["target_id"] == rid
    assert event["metadata"] == {"rule_id": rid, "phone_last4": "3210", "status": "sent"}
    assert "9876543210" not in str(db.rows("app_audit_logs"))


def test_preview_audit_records_a_failed_send_too(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    send.side_effect = RuntimeError("boom")
    assert _preview(client, rid).json()["status"] == "failed"
    assert _audit_rows(db)[0]["metadata"]["status"] == "failed"


def test_preview_blocked_before_sending_writes_no_audit_event(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    assert _preview(client, rid, phone="12345").status_code == 422
    assert _preview(client, "nope").status_code == 404
    assert _audit_rows(db) == []


def test_preview_is_capped_at_20_a_day_and_says_so_in_plain_words(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    _seed_preview_audits(db, PREVIEW_DAILY_CAP, datetime.now(timezone.utc).isoformat())
    r = _preview(client, rid)
    assert r.status_code == 429 and r.json()["code"] == "preview_daily_limit"
    assert r.json()["detail"] == "You've sent 20 previews today. Try again tomorrow."
    send.assert_not_called()
    assert len(_audit_rows(db)) == PREVIEW_DAILY_CAP  # a blocked attempt adds nothing


def test_preview_under_the_cap_still_sends(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    _seed_preview_audits(db, PREVIEW_DAILY_CAP - 1, datetime.now(timezone.utc).isoformat())
    assert _preview(client, rid).status_code == 200
    send.assert_called_once()


def test_preview_cap_counts_only_this_tenant_this_action_since_ist_midnight(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    now = datetime.now(timezone.utc).isoformat()
    before_midnight = (_ist_midnight_utc() - timedelta(minutes=1)).isoformat()
    _seed_preview_audits(db, PREVIEW_DAILY_CAP, before_midnight)               # yesterday (IST)
    _seed_preview_audits(db, PREVIEW_DAILY_CAP, now, tenant=OTHER)             # someone else
    _seed_preview_audits(db, PREVIEW_DAILY_CAP, now, action="tenant.other")    # another action
    assert _preview(client, rid).status_code == 200


def test_preview_cap_applies_after_the_one_minute_limiter_resets(client, db, send):
    rid = _rule(db, "interested", _template(db, "t"))
    _seed_preview_audits(db, PREVIEW_DAILY_CAP, datetime.now(timezone.utc).isoformat())
    routes._preview_limiter.reset()
    assert _preview(client, rid).json()["code"] == "preview_daily_limit"


# ---------------------------------------------------------------- 7. concurrent duplicate event

def test_create_event_losing_a_unique_race_is_409_event_exists_not_500(client, db):
    from postgrest.exceptions import APIError
    real_table = db.table

    def table(name):
        query = real_table(name)
        if name == "auto_message_events":
            def insert(_payload):
                def fail():
                    raise APIError({"message": "duplicate key value violates unique constraint", "code": "23505"})
                return type("Q", (), {"execute": staticmethod(fail)})()
            query.insert = insert
        return query

    with patch.object(db, "table", side_effect=table):
        r = client.post(f"{BASE}/events", json={"label": "Kundli ready"})
    assert r.status_code == 409 and r.json()["code"] == "event_exists"


def test_create_event_other_insert_errors_are_not_swallowed(client, db):
    from postgrest.exceptions import APIError
    real_table = db.table

    def table(name):
        query = real_table(name)
        if name == "auto_message_events":
            def insert(_payload):
                def fail():
                    raise APIError({"message": "connection reset", "code": "08006"})
                return type("Q", (), {"execute": staticmethod(fail)})()
            query.insert = insert
        return query

    with patch.object(db, "table", side_effect=table), pytest.raises(APIError):
        client.post(f"{BASE}/events", json={"label": "Kundli ready"})
