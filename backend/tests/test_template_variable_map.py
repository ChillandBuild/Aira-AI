import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import template_fields, whatsapp_notify
from app.services.template_fields import AlertFields, build_body_components, is_valid_field

LEAD = {
    "id": "lead-1", "name": "Asha", "phone": "+919999999999",
    "created_at": "2026-10-06T20:00:00+00:00",  # 7 Oct 01:30 IST
    "assigned_to": "caller-1", "call_status": "callback",
    "collected_data": {"course": "MBA", "cities": ["Chennai", "Madurai"]},
}


def _db(rows_by_table: dict[str, list[dict]]):
    """Fake Supabase client: any query chain on a table returns that table's rows."""
    db = MagicMock()
    calls: list[str] = []

    def table(name):
        calls.append(name)
        chain = MagicMock()
        for m in ("select", "eq", "order", "limit", "update"):
            getattr(chain, m).return_value = chain
        chain.execute.return_value = MagicMock(data=rows_by_table.get(name, []))
        return chain

    db.table.side_effect = table
    db.calls = calls
    return db


def _texts(comps):
    return [p["text"] for p in comps[0]["parameters"]]


# --- no map: exactly the old fixed order ------------------------------------

def test_escalation_without_map_keeps_fixed_order_and_queries_nothing():
    db = _db({})
    fields = AlertFields(db, "t1", LEAD, {"escalation_reason": "wants a human", "lead_source": "Organic lead"})
    template = {"body_text": "{{1}} {{2}} {{3}}", "variable_map": None}
    comps = whatsapp_notify._build_escalation_components(template, LEAD, "wants a human", fields=fields)
    assert _texts(comps) == ["Asha", "+919999999999", "wants a human"]
    assert db.calls == []


def test_hot_alert_without_map_keeps_fixed_order():
    template = {"body_text": "{{1}} {{2}} {{3}} {{4}}"}
    comps = whatsapp_notify._build_components(template, LEAD, "A", AlertFields(_db({}), "t1", LEAD))
    assert _texts(comps) == ["Asha", "+919999999999", "Hot", "https://www.anrilaitech.com/dashboard/conversations?lead_id=lead-1"]


# --- with a map --------------------------------------------------------------

def test_single_variable_template_can_take_the_phone():
    template = {"body_text": "Call {{1}} now", "variable_map": {"1": "lead_phone"}}
    fields = AlertFields(_db({}), "t1", LEAD, {"escalation_reason": "x", "lead_source": "Organic lead"})
    comps = whatsapp_notify._build_escalation_components(template, LEAD, "x", fields=fields)
    assert _texts(comps) == ["+919999999999"]


def test_field_the_alert_cannot_supply_falls_back_to_the_slot_default():
    # Escalation reason only exists on escalation alerts; on a hot-lead alert
    # {{3}} keeps its fixed value (the Hot/Warm label).
    template = {"body_text": "{{1}} {{2}} {{3}}", "variable_map": {"3": "escalation_reason"}}
    fields = AlertFields(_db({}), "t1", LEAD, {"lead_temperature": "Hot"})
    comps = whatsapp_notify._build_components(template, LEAD, "A", fields)
    assert _texts(comps) == ["Asha", "+919999999999", "Hot"]


def test_unknown_field_in_stored_map_falls_back_to_default():
    template = {"body_text": "{{1}}", "variable_map": {"1": "lead_score"}}
    comps = build_body_components(template, ["Asha"], AlertFields(_db({}), "t1", LEAD))
    assert _texts(comps) == ["Asha"]


def test_slot_beyond_defaults_with_unavailable_field_gets_a_dash():
    template = {"body_text": "{{1}} {{2}}", "variable_map": {"2": "escalation_reason"}}
    comps = build_body_components(template, ["Asha"], AlertFields(_db({}), "t1", LEAD))
    assert _texts(comps) == ["Asha", "-"]


def test_collected_detail_scalar_list_and_missing():
    template = {"body_text": "{{1}} {{2}} {{3}}", "variable_map": {
        "1": "collected:course", "2": "collected:cities", "3": "collected:budget"}}
    comps = build_body_components(template, [], AlertFields(_db({}), "t1", LEAD))
    assert _texts(comps) == ["MBA", "Chennai, Madurai", "-"]


def test_lead_details_from_other_tables():
    db = _db({
        "callers": [{"name": "Ravi"}],
        "tenants": [{"name": "Rao Academy"}],
        "messages": [{"content": "Is the\nfee  refundable?", "channel": "instagram", "media_type": None}],
    })
    template = {"body_text": "{{1}} {{2}} {{3}} {{4}} {{5}}", "variable_map": {
        "1": "assigned_agent", "2": "business_name", "3": "last_message", "4": "channel", "5": "call_status"}}
    comps = build_body_components(template, [], AlertFields(db, "t1", LEAD))
    assert _texts(comps) == ["Ravi", "Rao Academy", "Is the fee refundable?", "Instagram", "Call later"]
    assert db.calls.count("messages") == 1  # last message and channel share one lookup


def test_unassigned_lead_and_no_calls_yet():
    lead = {**LEAD, "assigned_to": None, "call_status": None}
    template = {"body_text": "{{1}} {{2}}", "variable_map": {"1": "assigned_agent", "2": "call_status"}}
    comps = build_body_components(template, [], AlertFields(_db({}), "t1", lead))
    assert _texts(comps) == ["Unassigned", "Not called yet"]


def test_dates_are_shown_in_ist():
    template = {"body_text": "{{1}} {{2}}", "variable_map": {"1": "enquiry_date", "2": "alert_time"}}
    fixed = datetime(2026, 10, 7, 10, 5, tzinfo=timezone.utc)  # 3:35 PM IST
    with patch.object(template_fields, "datetime", wraps=datetime) as dt:
        dt.now.return_value = fixed
        comps = build_body_components(template, [], AlertFields(_db({}), "t1", LEAD))
    assert _texts(comps) == ["7 Oct 2026", "7 Oct 2026, 3:35 PM"]


def test_lazy_lead_source_only_runs_when_used():
    source = MagicMock(return_value="Ad: Diwali")
    fields = AlertFields(_db({}), "t1", LEAD, {"lead_source": source})
    build_body_components({"body_text": "{{1}}", "variable_map": {"1": "lead_name"}}, [], fields)
    source.assert_not_called()
    comps = build_body_components({"body_text": "{{1}}", "variable_map": {"1": "lead_source"}}, [], fields)
    assert _texts(comps) == ["Ad: Diwali"]


@pytest.mark.parametrize("field,ok", [
    ("lead_phone", True), ("channel", True), ("collected:course", True), ("collected:Preferred city", True),
    ("lead_score", False), ("collected:", False), ("collected:<script>", False), ("", False), (None, False),
])
def test_is_valid_field(field, ok):
    assert is_valid_field(field) is ok


# --- save endpoint -----------------------------------------------------------

def _save(body_text: str, var_map: dict):
    from app.routes import templates as routes
    db = _db({"message_templates": [{"id": "tmpl-1", "body_text": body_text}]})
    with patch.object(routes, "get_supabase", return_value=db):
        return asyncio.run(routes.update_template_variable_map(
            "tmpl-1", routes.VariableMapPayload(variable_map=var_map), tenant_id="t1", _ctx={}))


def test_save_cleans_and_returns_map():
    assert _save("Hi {{1}} {{2}}", {"01": " lead_phone ", "2": "collected:course"}) == {
        "id": "tmpl-1", "variable_map": {"1": "lead_phone", "2": "collected:course"}}


def test_save_rejects_slot_the_template_does_not_have():
    with pytest.raises(HTTPException) as e:
        _save("Hi {{1}}", {"2": "lead_phone"})
    assert e.value.status_code == 400 and "{{2}}" in e.value.detail


def test_save_rejects_unknown_field():
    with pytest.raises(HTTPException) as e:
        _save("Hi {{1}}", {"1": "lead_score"})
    assert e.value.status_code == 400
