"""IndiaMART / JustDial enquiries end to end, with realistic sample payloads
(no current client uses these marketplaces, so these are the proof):
parsing both shapes, JustDial's three transports, bad tokens and bodies,
repeat enquiries, welcome template, DNC."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import marketplace_intake
from app.services import marketplace_leads
from app.services.marketplace_leads import enquiry_note, parse_enquiry

INDIAMART_PUSH = {
    "CODE": 200,
    "STATUS": "SUCCESS",
    "RESPONSE": {
        "UNIQUE_QUERY_ID": "2998847362",
        "QUERY_TYPE": "W",
        "SENDER_NAME": "Suresh Kumar",
        "SENDER_MOBILE": "+91-9876543210",
        "SENDER_EMAIL": "suresh@example.com",
        "SENDER_COMPANY": "SK Traders",
        "SENDER_CITY": "Chennai",
        "SENDER_STATE": "Tamil Nadu",
        "SENDER_PINCODE": "600002",
        "QUERY_PRODUCT_NAME": "LED Bulb 9W",
        "QUERY_MESSAGE": "Need 500 pieces, delivery in Chennai",
    },
}

JUSTDIAL_PUSH = {
    "leadid": "JD123", "prefix": "Mr", "name": "Ravi", "mobile": "9876500000", "email": "",
    "category": "Mobile Accessories", "city": "Madurai", "area": "Anna Nagar", "dncmobile": "0",
}


def test_indiamart_nested_response_is_read():
    e = parse_enquiry("indiamart", INDIAMART_PUSH)
    assert e["phone"] == "+91-9876543210"
    assert e["name"] == "Suresh Kumar"
    assert e["product"] == "LED Bulb 9W"
    assert e["city"] == "Chennai" and e["query_id"] == "2998847362"


def test_indiamart_flat_payload_still_works():
    assert parse_enquiry("indiamart", INDIAMART_PUSH["RESPONSE"])["phone"] == "+91-9876543210"


def test_numeric_phone_is_coerced_not_a_crash():
    assert parse_enquiry("justdial", {"mobile": 9876500000})["phone"] == "9876500000"


def test_justdial_fields_and_dnc_flag():
    e = parse_enquiry("justdial", {**JUSTDIAL_PUSH, "dncmobile": "1"})
    assert e["name"] == "Mr Ravi" and e["product"] == "Mobile Accessories" and e["do_not_call"] is True


def test_note_carries_what_the_buyer_typed():
    note = enquiry_note("indiamart", parse_enquiry("indiamart", INDIAMART_PUSH))
    assert note.startswith("IndiaMART enquiry: LED Bulb 9W")
    assert "Need 500 pieces" in note and "(Chennai, Tamil Nadu)" in note and "SK Traders" in note


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(marketplace_intake.public_router, prefix="/api/v1/marketplace")
    handle = AsyncMock(return_value={"status": "ok", "lead_id": "lead-1", "is_new": True})
    with patch.object(marketplace_intake, "get_supabase", return_value=MagicMock()), \
         patch.object(marketplace_intake, "_resolve_tenant_by_token", side_effect=lambda db, p, t: "t1" if t == "good" else None), \
         patch.object(marketplace_intake, "handle_enquiry", handle):
        yield TestClient(app), handle


def test_indiamart_push_reaches_handler_with_parsed_enquiry(client):
    c, handle = client
    r = c.post("/api/v1/marketplace/indiamart/good", json=INDIAMART_PUSH)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    tenant, provider, enquiry = handle.await_args.args
    assert (tenant, provider, enquiry["phone"]) == ("t1", "indiamart", "+91-9876543210")


@pytest.mark.parametrize("transport", ["json", "form", "get"])
def test_justdial_accepts_json_form_and_query_and_acks_received(client, transport):
    c, handle = client
    url = "/api/v1/marketplace/justdial/good"
    if transport == "json":
        r = c.post(url, json=JUSTDIAL_PUSH)
    elif transport == "form":
        r = c.post(url, data=JUSTDIAL_PUSH)
    else:
        r = c.get(url, params=JUSTDIAL_PUSH)
    assert r.status_code == 200 and r.text == "RECEIVED"
    assert handle.await_args.args[2]["phone"] == "9876500000"


def test_bad_token_is_401_and_never_parsed(client):
    c, handle = client
    assert c.post("/api/v1/marketplace/indiamart/wrong", json=INDIAMART_PUSH).status_code == 401
    handle.assert_not_awaited()


def test_non_object_json_is_400(client):
    c, _ = client
    assert c.post("/api/v1/marketplace/indiamart/good", json=[1, 2]).status_code == 400


# ---------------------------------------------------------------- handle_enquiry

def _db(existing_lead=None):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
    chain.execute.return_value = SimpleNamespace(data=[existing_lead] if existing_lead else [])
    return db


@pytest.mark.asyncio
async def test_new_enquiry_creates_lead_notes_it_assigns_and_welcomes():
    enquiry = parse_enquiry("indiamart", INDIAMART_PUSH)
    welcome = AsyncMock(return_value=True)
    with patch("app.services.inbound_lead.create_inbound_lead", return_value="lead-1") as create, \
         patch.object(marketplace_leads, "_existing_lead", side_effect=[None, {"id": "lead-1", "segment": "C"}]), \
         patch.object(marketplace_leads, "_merge_enquiry") as merge, \
         patch.object(marketplace_leads, "_add_note") as note, \
         patch.object(marketplace_leads, "_assign_now") as assign, \
         patch.object(marketplace_leads, "send_welcome_template", welcome):
        out = await marketplace_leads.handle_enquiry("t1", "indiamart", enquiry, db=MagicMock())
    assert out == {"status": "ok", "lead_id": "lead-1", "is_new": True}
    assert create.call_args.kwargs["opt_in_source"] == "indiamart"  # broadcast gate needs it
    merge.assert_called_once()
    assert "LED Bulb 9W" in note.call_args.args[3]
    assign.assert_called_once_with("lead-1", "t1", "C")
    welcome.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeat_enquiry_is_noted_but_not_re_messaged_or_re_queued():
    enquiry = parse_enquiry("indiamart", INDIAMART_PUSH)
    welcome = AsyncMock()
    known = {"id": "lead-1", "segment": "B", "deleted_at": None}
    with patch("app.services.inbound_lead.create_inbound_lead", return_value="lead-1"), \
         patch.object(marketplace_leads, "_existing_lead", return_value=known), \
         patch.object(marketplace_leads, "_merge_enquiry"), \
         patch.object(marketplace_leads, "_add_note") as note, \
         patch.object(marketplace_leads, "_assign_now") as assign, \
         patch.object(marketplace_leads, "send_welcome_template", welcome):
        out = await marketplace_leads.handle_enquiry("t1", "indiamart", enquiry, db=MagicMock())
    assert out["is_new"] is False
    note.assert_called_once()
    assign.assert_not_called()
    welcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_dnc_buyer_is_not_queued_for_calls():
    enquiry = parse_enquiry("justdial", {**JUSTDIAL_PUSH, "dncmobile": "1"})
    with patch("app.services.inbound_lead.create_inbound_lead", return_value="lead-1"), \
         patch.object(marketplace_leads, "_existing_lead", side_effect=[None, {"id": "lead-1", "segment": "C"}]), \
         patch.object(marketplace_leads, "_merge_enquiry") as merge, \
         patch.object(marketplace_leads, "_add_note"), \
         patch.object(marketplace_leads, "_assign_now") as assign, \
         patch.object(marketplace_leads, "send_welcome_template", AsyncMock()):
        await marketplace_leads.handle_enquiry("t1", "justdial", enquiry, db=MagicMock())
    assign.assert_not_called()
    assert merge.call_args.args[4]["do_not_call"] is True


@pytest.mark.asyncio
async def test_missing_phone_is_ignored_not_an_error():
    out = await marketplace_leads.handle_enquiry("t1", "indiamart", {"phone": ""}, db=MagicMock())
    assert out["status"] == "ignored"


@pytest.mark.asyncio
async def test_welcome_template_fills_name_and_product_into_its_variables():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = (
        SimpleNamespace(data=[{"name": "enquiry_hi", "language": "en", "status": "APPROVED", "header_media_type": None,
                               "body_text": "Hi {{1}}, thanks for asking about {{2}}!"}])
    )
    send = AsyncMock()
    with patch("app.config_dynamic.get_setting", return_value="tpl-1"), \
         patch("app.services.meta_cloud.send_template_message", send):
        ok = await marketplace_leads.send_welcome_template(db, "t1", "+919876543210",
                                                           {"name": "Suresh Kumar", "product": "LED Bulb 9W"})
    assert ok is True
    params = send.await_args.kwargs["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Suresh", "LED Bulb 9W"]


@pytest.mark.asyncio
async def test_welcome_send_failure_never_raises():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = (
        SimpleNamespace(data=[{"name": "t", "language": "en", "status": "APPROVED", "header_media_type": None, "body_text": "Hi"}])
    )
    with patch("app.config_dynamic.get_setting", return_value="tpl-1"), \
         patch("app.services.meta_cloud.send_template_message", AsyncMock(side_effect=RuntimeError("meta down"))):
        assert await marketplace_leads.send_welcome_template(db, "t1", "+91", {}) is False
