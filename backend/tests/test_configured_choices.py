import asyncio
import json

import pytest

from app.services import choices, deal_actions, deal_turn, intake


PACKAGES = [
    {"key": "one", "name": "One Question", "amount_paise": 100, "button_label": "1 Rs"},
    {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs"},
    {"key": "marriage", "name": "Marriage Compatibility", "amount_paise": 9900, "button_label": "Marriage 99Rs"},
]
FIELDS = [
    {"key": "name", "label": "Name", "type": "text"},
    {"key": "gender", "label": "Gender", "type": "choice", "options": ["Male", "Female"]},
    {"key": "slot", "label": "Preferred time", "type": "choice", "options": ["Morning", "Evening"]},
]


def ctx():
    return deal_actions.DealContext(
        config={"enabled": True, "packages": PACKAGES, "fields": FIELDS},
        db=object(), lead_id="lead", tenant_id="tenant", phone="", buttons_enabled=True,
    )


def call(**args):
    return {"function": {"name": "offer_choices", "arguments": json.dumps(args)}}


def run_turn(monkeypatch, draft="", calls=(), session=None):
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)

    async def model(messages, **kwargs):
        return draft, list(calls)

    async def text_model(messages, **kwargs):
        return "Please choose from the configured options."

    return asyncio.run(deal_turn.converse_once(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "options sollunga"}],
        [], ctx(), tenant_id="tenant", llm_with_tools=model, llm=text_model,
    ))


@pytest.mark.parametrize("source", ["tool", "marker"])
def test_legacy_package_choices_use_saved_labels_and_ids(monkeypatch, source):
    labels = ["One Question (1 Rs)", "Detailed Question (99 Rs)", "Marriage Compatibility (99 Rs)"]
    body = "Enga kitta jaadhaga aaraichi irukku. Ungaluku edhula interest irukku?"
    draft = body + "\nCHOICES: " + " | ".join(labels) if source == "marker" else ""
    calls = [call(message=body, options=labels)] if source == "tool" else []
    text, _, outcome = run_turn(monkeypatch, draft, calls)
    assert outcome.menu["kind"] == "list"  # three options are a list, only two are reply buttons
    assert outcome.menu["sections"][0]["rows"] == [
        {"id": p["key"], "title": p["button_label"]} for p in PACKAGES
    ]
    assert "One Question" in text and "Detailed Question" in text and "Marriage Compatibility" in text


def test_structured_offerings_need_no_ai_labels(monkeypatch):
    text, _, outcome = run_turn(monkeypatch, calls=[
        call(message="Edhu venum?", offering_keys=["one", "detailed", "marriage"])
    ])
    assert outcome.menu["options"] == ["1 Rs", "99Rs", "Marriage 99Rs"]
    assert "₹1" in text and "₹99" in text


def test_tanglish_detail_question_is_bound_even_out_of_order(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Neenga aan-aa pen-aa?", field_key="gender")], session=session)
    assert outcome.menu["options"] == ["Male", "Female"]
    assert choices.parse_detail_tap(outcome.menu["buttons"][0]["id"]) == ("session", "gender", "Male")


def test_generic_detail_choices_bind_to_configured_field(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Neenga aan-aa pen-aa?", options=["Male", "Female"])], session=session)
    assert choices.parse_detail_tap(outcome.menu["buttons"][1]["id"]) == ("session", "gender", "Female")


def test_explicit_field_can_offer_a_correction_to_an_answered_detail(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {"gender": "Male"}}
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Gender correct panna select pannunga?", field_key="gender")], session=session)
    assert choices.parse_detail_tap(outcome.menu["buttons"][1]["id"]) == ("session", "gender", "Female")


def test_unknown_structured_reference_cannot_become_generic_buttons(monkeypatch):
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Choose?", field_key="unknown", options=["Yes", "No"])])
    assert outcome.menu is None
    assert any("offer_choices" in r for r in outcome.refusals)


def test_unrelated_conversational_options_remain_generic(monkeypatch):
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Delivery or pickup?", options=["Delivery", "Pickup"])])
    assert outcome.menu["buttons"] == [{"id": "choice:1", "title": "Delivery"}, {"id": "choice:2", "title": "Pickup"}]


@pytest.mark.parametrize("collected", [{}, {"gender": "Female", "name": "Prem", "slot": "Morning"}])
def test_detail_tap_saves_and_corrects_canonical_value_without_extraction(monkeypatch, collected):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": collected.copy(), "skipped_fields": []}
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)
    monkeypatch.setattr(intake, "_update_session", lambda sid, patch, db: session.update(patch))
    monkeypatch.setattr(intake, "adopt_lead_name", lambda *a: None)

    async def extractor(*args):
        raise AssertionError("tappable configured values must not depend on the model")

    tap = choices.build_detail_menu(FIELDS[1], "session")["buttons"][0]["id"]
    saved = asyncio.run(deal_turn.capture_details(ctx(), "Male", interactive_id=tap, extractor=extractor))
    assert saved == {"gender": "Male"}
    assert session["collected_data"]["gender"] == "Male"


@pytest.mark.parametrize("fault", ["session", "config", "paid", "malformed"])
def test_stale_or_invalid_detail_tap_never_saves_or_extracts(monkeypatch, fault):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    context = ctx()
    menu = choices.build_detail_menu(FIELDS[1], "old" if fault == "session" else "session")
    tap = menu["buttons"][0]["id"]
    if fault == "config":
        context.config["fields"] = [f for f in FIELDS if f["key"] != "gender"]
    if fault == "paid":
        session["status"] = "paid"
    if fault == "malformed":
        tap = "choice:detail:invalid"
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)

    async def extractor(*args):
        raise AssertionError("a rejected old tap must not be reinterpreted as a different detail")

    assert asyncio.run(deal_turn.capture_details(context, "Male", interactive_id=tap, extractor=extractor)) == {}
    assert session["collected_data"] == {}


def test_booking_change_during_tap_capture_cannot_save_into_new_booking(monkeypatch):
    before = {"id": "old", "package_key": "one", "status": "collecting", "collected_data": {}}
    after = {"id": "new", "package_key": "one", "status": "collecting", "collected_data": {}}
    sessions = iter([before, after])
    monkeypatch.setattr(deal_actions, "_session", lambda _: next(sessions))
    writes = []
    monkeypatch.setattr(intake, "_update_session", lambda sid, patch, db: writes.append((sid, patch)))
    monkeypatch.setattr(intake, "adopt_lead_name", lambda *a: None)
    tap = choices.build_detail_menu(FIELDS[1], "old")["buttons"][0]["id"]
    assert asyncio.run(deal_turn.capture_details(ctx(), "Male", interactive_id=tap)) == {}
    assert writes == []


def test_four_configured_offerings_keep_real_keys_in_a_list(monkeypatch):
    context = ctx()
    context.config["packages"] = PACKAGES + [{"key": "extra", "name": "Extra", "amount_paise": 20000}]
    menu, error = deal_turn._configured_menu(context, {"offering_keys": [p["key"] for p in context.config["packages"]]}, [])
    assert not error and menu["kind"] == "list"
    assert [r["id"] for r in menu["sections"][0]["rows"]] == ["one", "detailed", "marriage", "extra"]


def test_general_service_answer_gets_no_paid_package_menu(monkeypatch):
    _, _, outcome = run_turn(monkeypatch, "We offer horoscope analysis, predictions and marriage compatibility. Anything else I can help with?")
    assert outcome.menu is None


def test_package_menu_under_a_detail_question_is_refused(monkeypatch):
    _, _, outcome = run_turn(monkeypatch, calls=[call(message="Could you share your name?", offering_keys=["one", "detailed"])])
    assert outcome.menu is None
    assert any("message" in r for r in outcome.refusals)


def test_text_channel_renders_configured_options(monkeypatch):
    context = ctx()
    object.__setattr__(context, "buttons_enabled", False)
    attached = deal_turn._Attached()
    text = deal_turn._attach_choices("Which one?", context, attached, [], "", choice_args={"offering_keys": ["one", "detailed"]})
    assert attached.menu is None and "1 Rs" in text and "99Rs" in text


def test_retry_that_changes_the_question_drops_old_detail_buttons(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)
    responses = iter([
        ("Gender? It costs ₹1000.", [call(message="Gender? It costs ₹1000.", field_key="gender")]),
        ("What is your name?", []),
    ])

    async def model(messages, **kwargs):
        return next(responses)

    text, _, outcome = asyncio.run(deal_turn.converse_once(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "book"}],
        [], ctx(), tenant_id="tenant", llm_with_tools=model, llm=model,
    ))
    assert text == "What is your name?" and outcome.menu is None


def test_detail_taps_are_not_reinterpreted_from_history_on_later_turns():
    rows = [
        {"direction": "inbound", "content": "Male", "interactive_id": "choice:detail:old"},
        {"direction": "inbound", "content": "Prem", "interactive_id": None},
        {"direction": "outbound", "content": "Name?"},
        {"direction": "inbound", "content": "1 Rs", "interactive_id": "one"},
    ]
    history = deal_turn.without_detail_taps(rows)
    assert [r["content"] for r in history] == ["Prem", "Name?", "1 Rs"]


def test_rejected_tap_cannot_be_resaved_by_a_model_tool(monkeypatch):
    context = ctx()
    object.__setattr__(context, "rejected_detail_tap", True)
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)
    tool = {"function": {"name": "save_details", "arguments": json.dumps({"fields": {"gender": "Male"}})}}
    outcome = asyncio.run(deal_actions.apply_tool_calls([tool], context))
    assert outcome.refusals and session["collected_data"] == {}


def test_choice_tool_message_is_the_message_above_its_buttons(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    text, _, outcome = run_turn(monkeypatch, draft="What is your birth date?", calls=[
        call(message="Neenga aan-aa pen-aa?", field_key="gender")
    ], session=session)
    assert text == "Neenga aan-aa pen-aa?" and outcome.menu["options"] == ["Male", "Female"]


def test_generic_options_from_a_refused_round_do_not_follow_a_new_question(monkeypatch):
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)
    responses = iter([
        ("", [call(message="Gender? It costs ₹1000.", options=["Male", "Female"])]),
        ("What is your name?", []),
    ])

    async def model(messages, **kwargs):
        return next(responses)

    text, _, outcome = asyncio.run(deal_turn.converse_once(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "book"}],
        [], ctx(), tenant_id="tenant", llm_with_tools=model, llm=model,
    ))
    assert text == "What is your name?" and outcome.menu is None


def test_saved_options_with_whitespace_accept_their_own_button(monkeypatch):
    context = ctx()
    field = {"key": "gender", "label": "Gender", "options": [" Male ", " Female "]}
    context.config["fields"] = [field]
    session = {"id": "session", "package_key": "one", "status": "collecting", "collected_data": {}}
    tap = choices.build_detail_menu(field, "session")["buttons"][0]["id"]
    assert deal_turn._detail_tap_fields(context, tap, session) == {"gender": " Male "}


@pytest.mark.parametrize("structured", [True, False])
def test_oversized_configured_choice_ids_use_full_text_not_generic_buttons(monkeypatch, structured):
    context = ctx()
    field = {"key": "appointment_type", "label": "Appointment type", "options": ["அ" * 50, "Female"]}
    context.config["fields"] = [field]
    session = {"id": "00000000-0000-0000-0000-000000000000", "package_key": "one", "status": "collecting", "collected_data": {}}
    monkeypatch.setattr(deal_actions, "_session", lambda _: session)
    args = {"field_key": field["key"]} if structured else {}
    offered = [] if structured else field["options"]
    attached = deal_turn._Attached()
    text = deal_turn._attach_choices("Choose appointment type?", context, attached, offered, "", choice_args=args)
    assert attached.menu is None
    assert field["options"][0] in text and "Female" in text
