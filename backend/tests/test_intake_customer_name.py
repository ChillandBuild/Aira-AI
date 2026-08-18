"""Naming the customer without knowing the tenant's field schema in advance.

Every tenant configures its own intake fields, so the key holding a person's name
is whatever they typed into the console -- `full_name` for an astrologer,
`patient_name` for a clinic, `member_name` for a gym. The code looked for the
literal key "name", found nothing, and greeted paying customers as "Customer".

Live evidence 2026-08-15: a lead who typed "Prem Kumar D" during collection got
"Customer, Payment success aayiduchu" the moment their payment cleared, and the
staff notification read "Lead 'Customer' paid for a consultation".
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intake as ik


def _fields(*specs):
    return [{"key": k, "label": l, "type": "text"} for k, l in specs]


# --- identifying the name -------------------------------------------------


def test_the_literal_name_key_is_used_when_present():
    fields = _fields(("name", "Name"), ("age", "Age"))
    assert ik.resolve_customer_name({"name": "Cheran", "age": "30"}, fields) == "Cheran"


def test_an_astrologers_full_name_field_is_recognised():
    fields = _fields(("full_name", "Full Name"), ("date_of_birth", "Date of birth"))
    collected = {"full_name": "Prem Kumar D", "date_of_birth": "19 november 2003"}
    assert ik.resolve_customer_name(collected, fields) == "Prem Kumar D"


def test_a_clinics_patient_name_field_is_recognised():
    fields = _fields(("patient_name", "Patient Name"), ("symptoms", "Symptoms"))
    assert ik.resolve_customer_name({"patient_name": "Lakshmi"}, fields) == "Lakshmi"


def test_an_opaque_key_is_matched_on_its_label_instead():
    """Tenants sometimes key fields f1/f2/f3 and put the meaning in the label."""
    fields = _fields(("f1", "Your Name"), ("f2", "Preferred slot"))
    assert ik.resolve_customer_name({"f1": "Ravi", "f2": "6am"}, fields) == "Ravi"


def test_fields_that_merely_contain_a_person_are_not_mistaken_for_the_name():
    fields = _fields(("place_of_birth", "Place of Birth"), ("goal", "Goal"))
    assert ik.resolve_customer_name({"place_of_birth": "erode", "goal": "fitness"}, fields) is None


def test_the_first_matching_field_in_config_order_wins():
    fields = _fields(("full_name", "Full Name"), ("nominee_name", "Nominee Name"))
    collected = {"full_name": "Cheran", "nominee_name": "Meena"}
    assert ik.resolve_customer_name(collected, fields) == "Cheran"


def test_a_blank_value_does_not_count_as_a_name():
    fields = _fields(("full_name", "Full Name"))
    assert ik.resolve_customer_name({"full_name": "   "}, fields) is None


def test_the_value_is_returned_exactly_as_the_customer_typed_it():
    fields = _fields(("full_name", "Full Name"))
    assert ik.resolve_customer_name({"full_name": " prem KUMAR d "}, fields) == "prem KUMAR d"


# --- falling back ---------------------------------------------------------


def test_the_leads_own_name_is_used_when_no_field_holds_one():
    """A gym asks only for a goal and a slot -- but WhatsApp already told us who
    this is."""
    fields = _fields(("goal", "Goal"), ("preferred_slot", "Preferred slot"))
    name = ik.resolve_customer_name({"goal": "fitness"}, fields, lead_name="Ravi")
    assert name == "Ravi"


def test_a_collected_name_beats_the_leads_stored_name():
    fields = _fields(("full_name", "Full Name"))
    name = ik.resolve_customer_name({"full_name": "Prem Kumar D"}, fields, lead_name="Prem")
    assert name == "Prem Kumar D"


def test_nothing_identifiable_yields_no_name_rather_than_a_placeholder():
    """The point of the whole fix. No keyword list covers every language a tenant
    might label a field in -- here the key is opaque and the label is Tamil script,
    so nothing matches. Greeting this customer as 'Customer' is worse than not
    greeting them at all."""
    fields = _fields(("f1", "பெயர்"), ("f2", "வயது"))
    assert ik.resolve_customer_name({"f1": "சரண்"}, fields, lead_name=None) is None


def test_a_romanised_tamil_name_field_is_recognised():
    fields = _fields(("peyar", "Peyar"), ("vayadhu", "Vayadhu"))
    assert ik.resolve_customer_name({"peyar": "Cheran"}, fields) == "Cheran"


def test_an_absent_schema_falls_back_to_scanning_the_collected_keys():
    assert ik.resolve_customer_name({"customer_name": "Meena"}, None) == "Meena"


def test_empty_everything_is_handled():
    assert ik.resolve_customer_name({}, []) is None
    assert ik.resolve_customer_name(None, None) is None


# --- what the customer and the staff actually see -------------------------


@pytest.mark.asyncio
async def test_the_receipt_greets_a_customer_whose_name_is_known():
    from app.services import intake_copy

    with patch.object(intake_copy, "resolve_language_mode", return_value="tanglish"), \
         patch.object(intake_copy, "compose_line", new=AsyncMock(return_value="Unga consultation book aayiduchu.")), \
         patch("app.db.supabase.get_supabase", return_value=MagicMock()):
        text = await intake_copy.compose_payment_receipt(
            lead_id="l-1", tenant_id="t-1", customer_name="Prem Kumar D", service_noun="consultation",
        )
    assert text == "Prem Kumar D, Unga consultation book aayiduchu."


@pytest.mark.asyncio
async def test_the_receipt_drops_the_greeting_rather_than_inventing_one():
    from app.services import intake_copy

    with patch.object(intake_copy, "resolve_language_mode", return_value="tanglish"), \
         patch.object(intake_copy, "compose_line", new=AsyncMock(return_value="Unga consultation book aayiduchu.")), \
         patch("app.db.supabase.get_supabase", return_value=MagicMock()):
        text = await intake_copy.compose_payment_receipt(
            lead_id="l-1", tenant_id="t-1", customer_name=None, service_noun="consultation",
        )
    assert text == "Unga consultation book aayiduchu."
    assert "Customer" not in text


def _paid_session_db(collected, lead_name=None):
    db = MagicMock()
    existing = MagicMock()
    existing.data = {
        "id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1",
        "tenant_id": "t-1", "collected_data": collected,
        "field_schema": _fields(("full_name", "Full Name"), ("date_of_birth", "Date of birth")),
        "package_amount_paise": 500,
    }
    lead = MagicMock()
    lead.data = {"phone": "+919345679286", "name": lead_name}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
        existing, lead,
    ]
    return db


def test_confirming_payment_reports_the_name_from_the_tenants_own_schema():
    db = _paid_session_db({"full_name": "Prem Kumar D"})
    with patch.object(ik, "notify_pool"):
        result = ik.confirm_intake_payment("sess-1", "pay_1", amount_paid_paise=500, db=db)
    assert result["customer_name"] == "Prem Kumar D"


def test_confirming_payment_reports_no_name_when_none_can_be_identified():
    db = _paid_session_db({"date_of_birth": "06.06.2000"})
    with patch.object(ik, "notify_pool"):
        result = ik.confirm_intake_payment("sess-1", "pay_1", amount_paid_paise=500, db=db)
    assert result["customer_name"] is None


def test_the_staff_notification_says_a_lead_rather_than_lead_customer():
    db = _paid_session_db({"date_of_birth": "06.06.2000"})
    with patch.object(ik, "notify_pool") as notify:
        ik.confirm_intake_payment("sess-1", "pay_1", amount_paid_paise=500, db=db)
    body = notify.call_args[0][3]
    assert "Customer" not in body
    assert "A lead paid" in body


def test_the_staff_notification_names_the_lead_when_it_can():
    db = _paid_session_db({"full_name": "Prem Kumar D"})
    with patch.object(ik, "notify_pool") as notify:
        ik.confirm_intake_payment("sess-1", "pay_1", amount_paid_paise=500, db=db)
    assert "Prem Kumar D" in notify.call_args[0][3]


# --- writing the name back onto the lead ----------------------------------


def test_a_newly_collected_name_is_written_onto_a_lead_that_has_none():
    """The dashboard showed this lead as unnamed while they were mid-conversation
    telling us exactly who they are."""
    db = MagicMock()
    ik.adopt_lead_name(db, "lead-1", "t-1", "Prem Kumar D")
    update = db.table.return_value.update
    update.assert_called_once_with({"name": "Prem Kumar D"})
    # Guarded in the query, not by a prior read: never overwrite a name a human set.
    update.return_value.eq.return_value.eq.return_value.is_.assert_called_once_with("name", "null")


def test_no_write_is_attempted_without_a_name():
    db = MagicMock()
    ik.adopt_lead_name(db, "lead-1", "t-1", None)
    db.table.assert_not_called()


def test_a_failed_name_write_is_swallowed():
    db = MagicMock()
    db.table.side_effect = RuntimeError("postgrest down")
    ik.adopt_lead_name(db, "lead-1", "t-1", "Prem")  # must not raise
