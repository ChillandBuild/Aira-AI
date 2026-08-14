"""Brain-led intake: the main AI drives the paid intake flow through tools,
instead of route_intake composing and sending every line itself.

Gated to an explicit per-tenant phone allowlist so it can be live-tested on one
number without any real lead reaching it.
"""
import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intake_brain as ib


_CONFIG = {
    "enabled": True,
    "trigger_description": "astrology question",
    "offer_message": "Verum ₹29 dhaan. Proceed pannalaama?",
    "fields": [
        {"key": "full_name", "label": "Full Name", "type": "text"},
        {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    ],
    "packages": [
        {"key": "basic", "name": "Basic", "amount_paise": 500, "description": "short reading"},
        {"key": "deep", "name": "Deep Dive", "amount_paise": 2900, "description": "full chart"},
    ],
    "service_noun": "consultation",
    "amount_paise": 0,
}


def _session(status="collecting", **extra):
    return {
        "id": "s-1",
        "status": status,
        "lead_id": "l-1",
        "tenant_id": "t-1",
        "collected_data": {},
        **extra,
    }


def _chain(result):
    """A Supabase query builder stub: every chained filter returns itself, and
    execute() yields `result` whatever the chain looked like."""
    m = MagicMock()
    m.execute.return_value = result
    for attr in ("select", "eq", "neq", "in_", "gte", "or_", "limit", "order", "maybe_single"):
        getattr(m, attr).return_value = m
    return m


def _db(lead_row):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        result = MagicMock()
        result.data = [lead_row] if name == "leads" else []
        t.select.return_value = _chain(result)
        t.update.return_value = _chain(result)
        t.insert.return_value = _chain(MagicMock(data=[{"id": "m-1"}]))
        return t

    db.table.side_effect = table
    return db


@contextlib.contextmanager
def _brain_led_env(session, chat_with_tools, gate_on=True):
    """generate_reply with everything around the reply itself stubbed out, so the
    assertions are about tool wiring and what actually gets sent."""
    from app.services import ai_reply, intake

    lead_row = {
        "ai_enabled": True, "score": 5, "segment": "C", "phone": "+919345679286",
        "converted_at": None, "tenant_id": "t-1", "assigned_to": None, "name": "Cheran",
        "blocked_at": None, "needs_human_attention": False, "tamil_locked": False,
    }
    build_prompt = MagicMock(return_value=("SYSTEM PROMPT", "tanglish"))
    send = AsyncMock(return_value="wamid.1")

    with patch.object(ai_reply, "get_supabase", return_value=_db(lead_row)), \
         patch.object(ai_reply, "get_setting", return_value="true"), \
         patch.object(ai_reply, "check_quota", return_value=True), \
         patch.object(ai_reply, "get_inbox_config", return_value={"triggers": []}), \
         patch.object(ai_reply, "_recent_thread", return_value=[]), \
         patch.object(ai_reply, "_resolve_campaign", return_value=(None, None)), \
         patch.object(ai_reply, "get_knowledge_context", new=AsyncMock(return_value="")), \
         patch.object(ai_reply, "_build_catalog_context",
                      new=AsyncMock(return_value=("CATALOG", [dict(ai_reply._CATALOG_RECOMMEND_TOOL)], {}, 3))), \
         patch.object(ai_reply, "build_reply_system_prompt", build_prompt), \
         patch.object(ai_reply, "_llm_chat_with_tools", new=chat_with_tools), \
         patch.object(ai_reply, "_llm_chat", new=AsyncMock(return_value="Sure!")), \
         patch.object(ai_reply, "send_whatsapp", new=send), \
         patch.object(ai_reply, "meter"), \
         patch.object(ai_reply, "sync_follow_up_jobs"), \
         patch.object(ai_reply, "record_stage_event"), \
         patch("app.services.scoring_engine.compute_score",
               new=AsyncMock(side_effect=RuntimeError("scoring is not what this test is about"))), \
         patch.object(ib, "is_brain_led", return_value=gate_on), \
         patch.object(intake, "get_intake_config", return_value=_CONFIG), \
         patch.object(intake, "_get_active_session", return_value=session):
        yield {"build_prompt": build_prompt, "send": send}


# --- the gate -------------------------------------------------------------


def test_gate_is_off_when_no_allowlist_is_configured():
    with patch.object(ib, "get_setting", return_value=""):
        assert ib.is_brain_led("t-1", "+919345679286") is False


def test_gate_is_off_for_a_phone_that_is_not_on_the_list():
    with patch.object(ib, "get_setting", return_value='["+919999999999"]'):
        assert ib.is_brain_led("t-1", "+919345679286") is False


def test_gate_is_on_for_a_listed_phone():
    with patch.object(ib, "get_setting", return_value='["+919345679286"]'):
        assert ib.is_brain_led("t-1", "+919345679286") is True


def test_gate_matches_regardless_of_phone_formatting():
    """The allowlist is typed by a human in the operator console; '+91 93456 79286'
    and '9345679286' must resolve to the same number as the stored lead phone."""
    with patch.object(ib, "get_setting", return_value='["+91 93456 79286"]'):
        assert ib.is_brain_led("t-1", "+919345679286") is True
    with patch.object(ib, "get_setting", return_value='["9345679286"]'):
        assert ib.is_brain_led("t-1", "+919345679286") is True


def test_gate_fails_closed_on_a_malformed_allowlist():
    with patch.object(ib, "get_setting", return_value="not json at all"):
        assert ib.is_brain_led("t-1", "+919345679286") is False


def test_gate_fails_closed_when_the_setting_lookup_raises():
    with patch.object(ib, "get_setting", side_effect=RuntimeError("boom")):
        assert ib.is_brain_led("t-1", "+919345679286") is False


def test_gate_is_off_for_an_empty_phone():
    with patch.object(ib, "get_setting", return_value='["+919345679286"]'):
        assert ib.is_brain_led("t-1", "") is False


# --- tool definitions -----------------------------------------------------


def _tool_names(tools):
    return [t["function"]["name"] for t in tools]


def test_details_and_cancel_tools_are_always_available():
    tools = ib.intake_tools(_CONFIG, _session())
    assert "save_intake_details" in _tool_names(tools)
    assert "cancel_intake" in _tool_names(tools)


def test_package_tool_is_offered_while_no_package_is_chosen():
    tools = ib.intake_tools(_CONFIG, _session(status="offer_pending"))
    assert "choose_package" in _tool_names(tools)


def test_package_tool_is_withdrawn_once_a_package_is_snapshotted():
    session = _session(package_key="basic", package_amount_paise=500)
    assert "choose_package" not in _tool_names(ib.intake_tools(_CONFIG, session))


def test_payment_tool_is_withheld_until_a_package_and_every_field_are_present():
    """The brain must not be able to bill a lead whose details are half-collected --
    the tool simply isn't on the menu until the data is there."""
    no_package = _session(collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    assert "send_payment_link" not in _tool_names(ib.intake_tools(_CONFIG, no_package))

    half_collected = _session(package_key="basic", package_amount_paise=500,
                              collected_data={"full_name": "Cheran"})
    assert "send_payment_link" not in _tool_names(ib.intake_tools(_CONFIG, half_collected))

    ready = _session(package_key="basic", package_amount_paise=500,
                     collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    assert "send_payment_link" in _tool_names(ib.intake_tools(_CONFIG, ready))


def test_payment_tool_takes_no_amount_argument():
    """The price is whatever the session snapshotted, never whatever the model says."""
    ready = _session(package_key="basic", package_amount_paise=500,
                     collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    tool = next(t for t in ib.intake_tools(_CONFIG, ready) if t["function"]["name"] == "send_payment_link")
    assert tool["function"]["parameters"]["properties"] == {}


def test_details_tool_advertises_the_exact_configured_field_keys():
    tool = next(t for t in ib.intake_tools(_CONFIG, _session()) if t["function"]["name"] == "save_intake_details")
    properties = tool["function"]["parameters"]["properties"]
    assert set(properties) == {"full_name", "date_of_birth"}


# --- prompt block ---------------------------------------------------------


def test_prompt_block_names_what_is_still_needed_and_what_is_already_held():
    block = ib.intake_prompt_block(_CONFIG, _session(collected_data={"full_name": "Cheran"}))
    assert "Full Name: Cheran" in block
    assert "Date of birth" in block


def test_prompt_block_renders_package_prices_in_python():
    block = ib.intake_prompt_block(_CONFIG, _session(status="offer_pending"))
    assert "₹5" in block
    assert "₹29" in block


def test_prompt_block_forbids_inventing_prices_or_links():
    block = ib.intake_prompt_block(_CONFIG, _session())
    lowered = block.lower()
    assert "never" in lowered
    assert "payment link" in lowered


# --- tool execution -------------------------------------------------------


def _call(name, args=None):
    return {"function": {"name": name, "arguments": json.dumps(args or {})}}


@pytest.mark.asyncio
async def test_saving_details_merges_onto_what_was_already_collected():
    db = MagicMock()
    session = _session(collected_data={"full_name": "Cheran"})
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("save_intake_details", {"date_of_birth": "06.06.2000"})],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    patch_arg = update.call_args[0][1]
    assert patch_arg["collected_data"] == {"full_name": "Cheran", "date_of_birth": "06.06.2000"}


@pytest.mark.asyncio
async def test_saving_details_ignores_keys_the_tenant_never_configured():
    db = MagicMock()
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("save_intake_details", {"full_name": "Cheran", "credit_card": "4111"})],
            session=_session(), config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    assert update.call_args[0][1]["collected_data"] == {"full_name": "Cheran"}


@pytest.mark.asyncio
async def test_choosing_a_package_snapshots_its_name_and_price_onto_the_session():
    db = MagicMock()
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("choose_package", {"package_key": "deep"})],
            session=_session(status="offer_pending"), config=_CONFIG, tenant_id="t-1",
            lead_id="l-1", phone="+91", db=db,
        )
    patch_arg = update.call_args[0][1]
    assert patch_arg["package_key"] == "deep"
    assert patch_arg["package_amount_paise"] == 2900
    assert patch_arg["status"] == "collecting"


@pytest.mark.asyncio
async def test_choosing_an_unconfigured_package_changes_nothing():
    db = MagicMock()
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("choose_package", {"package_key": "platinum"})],
            session=_session(status="offer_pending"), config=_CONFIG, tenant_id="t-1",
            lead_id="l-1", phone="+91", db=db,
        )
    update.assert_not_called()


@pytest.mark.asyncio
async def test_payment_link_is_created_at_the_snapshotted_amount_and_returned_verbatim():
    db = MagicMock()
    session = _session(
        package_key="basic", package_amount_paise=500,
        collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"},
    )
    create = AsyncMock(return_value={"payment_link_url": "https://rzp.io/rzp/ABC"})
    with patch.object(ib, "_update_session") as update, \
         patch.object(ib, "create_payment_link", new=create):
        appended = await ib.execute_intake_tools(
            [_call("send_payment_link")],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+919345679286", db=db,
        )
    assert create.call_args.kwargs["amount_paise"] == 500
    assert appended == "https://rzp.io/rzp/ABC"
    assert update.call_args[0][1]["status"] == "awaiting_payment"


@pytest.mark.asyncio
async def test_payment_link_is_refused_when_details_are_still_missing():
    """Belt and braces: the tool is already off the menu in this state, but a model
    that hallucinates the call must still not produce a charge."""
    db = MagicMock()
    session = _session(package_key="basic", package_amount_paise=500,
                       collected_data={"full_name": "Cheran"})
    create = AsyncMock()
    with patch.object(ib, "_update_session") as update, \
         patch.object(ib, "create_payment_link", new=create):
        appended = await ib.execute_intake_tools(
            [_call("send_payment_link")],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    create.assert_not_awaited()
    update.assert_not_called()
    assert appended == ""


@pytest.mark.asyncio
async def test_payment_link_is_refused_when_no_package_was_ever_chosen():
    db = MagicMock()
    session = _session(collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    create = AsyncMock()
    with patch.object(ib, "create_payment_link", new=create):
        appended = await ib.execute_intake_tools(
            [_call("send_payment_link")],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    create.assert_not_awaited()
    assert appended == ""


@pytest.mark.asyncio
async def test_a_failed_payment_link_leaves_the_session_unpaid_and_appends_nothing():
    db = MagicMock()
    session = _session(package_key="basic", package_amount_paise=500,
                       collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    with patch.object(ib, "_update_session") as update, \
         patch.object(ib, "create_payment_link", new=AsyncMock(side_effect=RuntimeError("razorpay down"))):
        appended = await ib.execute_intake_tools(
            [_call("send_payment_link")],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    assert appended == ""
    update.assert_not_called()


@pytest.mark.asyncio
async def test_cancelling_marks_the_session_cancelled():
    db = MagicMock()
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("cancel_intake")],
            session=_session(), config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    assert update.call_args[0][1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_saving_the_last_missing_field_moves_the_session_to_confirmation():
    db = MagicMock()
    session = _session(package_key="basic", package_amount_paise=500,
                       collected_data={"full_name": "Cheran"})
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("save_intake_details", {"date_of_birth": "06.06.2000"})],
            session=session, config=_CONFIG, tenant_id="t-1", lead_id="l-1",
            phone="+91", db=db,
        )
    assert update.call_args[0][1]["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_an_unparseable_tool_call_is_skipped_without_raising():
    db = MagicMock()
    bad = {"function": {"name": "save_intake_details", "arguments": "{not json"}}
    with patch.object(ib, "_update_session") as update:
        appended = await ib.execute_intake_tools(
            [bad], session=_session(), config=_CONFIG, tenant_id="t-1",
            lead_id="l-1", phone="+91", db=db,
        )
    assert appended == ""
    update.assert_not_called()


@pytest.mark.asyncio
async def test_an_unknown_tool_name_is_ignored():
    db = MagicMock()
    with patch.object(ib, "_update_session") as update:
        await ib.execute_intake_tools(
            [_call("delete_everything")], session=_session(), config=_CONFIG,
            tenant_id="t-1", lead_id="l-1", phone="+91", db=db,
        )
    update.assert_not_called()


# --- route_intake standing aside ------------------------------------------


@pytest.mark.asyncio
async def test_route_intake_yields_the_turn_once_a_brain_led_session_exists():
    """The whole flip: route_intake composes and sends nothing, and reports the
    turn as unconsumed so the webhook runs generate_reply instead."""
    from app.services import intake as ik

    db = MagicMock()
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=_session()), \
         patch.object(ik, "is_brain_led", return_value=True), \
         patch.object(ik, "_send_and_log", new=AsyncMock()) as send, \
         patch.object(ik, "compose_line", new=AsyncMock()) as compose:
        consumed = await ik.route_intake(
            lead_id="l-1", tenant_id="t-1", phone="+919345679286", body="Cheran", db=db,
        )
    assert consumed is False
    send.assert_not_awaited()
    compose.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_intake_still_makes_the_opening_offer_for_a_brain_led_lead():
    """Only the conversation flips. The trigger classifier and the tenant's own
    offer copy are identical in both modes, so they stay where they are."""
    from app.services import intake as ik

    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "s-new"}]
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=None), \
         patch.object(ik, "is_brain_led", return_value=True), \
         patch.object(ik, "detect_intake_intent", new=AsyncMock(return_value=True)), \
         patch.object(ik, "_update_session"), \
         patch.object(ik, "_send_and_log", new=AsyncMock()) as send:
        consumed = await ik.route_intake(
            lead_id="l-1", tenant_id="t-1", phone="+919345679286", body="jaadhagam paakanum", db=db,
        )
    assert consumed is True
    assert send.await_args[0][1] == _CONFIG["offer_message"]


@pytest.mark.asyncio
async def test_generate_reply_is_reached_with_intake_tools_and_no_catalog_tools():
    """End of the flip: the turn lands in the real reply engine, which offers the
    intake tools and suppresses catalog recommendations for the duration."""
    from app.services import ai_reply

    session = _session(package_key="basic", package_amount_paise=500,
                       collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    chat = AsyncMock(return_value=("Sari, indha link la pay pannunga:", []))
    with _brain_led_env(session, chat) as env:
        await ai_reply.generate_reply(lead_id="l-1", message="seri", phone="+919345679286")

    tools = chat.await_args.kwargs["tools"]
    names = [t["function"]["name"] for t in tools]
    assert "save_intake_details" in names
    assert "send_payment_link" in names
    assert "recommend_catalog_item" not in names
    assert env["build_prompt"].call_args.kwargs["include_intake_context"] is False


@pytest.mark.asyncio
async def test_the_payment_url_reaches_the_customer_verbatim():
    from app.services import ai_reply

    session = _session(package_key="basic", package_amount_paise=500,
                       collected_data={"full_name": "Cheran", "date_of_birth": "06.06.2000"})
    chat = AsyncMock(return_value=("Sari, indha link la pay pannunga:", [_call("send_payment_link")]))
    with _brain_led_env(session, chat) as env, \
         patch.object(ib, "create_payment_link",
                      new=AsyncMock(return_value={"payment_link_url": "https://rzp.io/rzp/XYZ"})), \
         patch.object(ib, "_update_session"):
        await ai_reply.generate_reply(lead_id="l-1", message="seri", phone="+919345679286")

    sent = env["send"].await_args[0][1]
    assert sent == "Sari, indha link la pay pannunga:\nhttps://rzp.io/rzp/XYZ"


@pytest.mark.asyncio
async def test_a_composer_led_lead_gets_no_intake_tools_from_the_reply_engine():
    from app.services import ai_reply

    chat = AsyncMock(return_value=("Sure!", []))
    with _brain_led_env(_session(), chat, gate_on=False) as env:
        await ai_reply.generate_reply(lead_id="l-1", message="hi", phone="+919999999999")

    names = [t["function"]["name"] for t in chat.await_args.kwargs["tools"]]
    assert names == ["recommend_catalog_item"]
    assert env["build_prompt"].call_args.kwargs["include_intake_context"] is True


@pytest.mark.asyncio
async def test_an_already_paid_session_is_left_to_the_existing_paid_context():
    from app.services import ai_reply

    chat = AsyncMock(return_value=("Sure!", []))
    with _brain_led_env(_session(status="paid"), chat) as env:
        await ai_reply.generate_reply(lead_id="l-1", message="when will they call?", phone="+919345679286")

    names = [t["function"]["name"] for t in chat.await_args.kwargs["tools"]]
    assert names == ["recommend_catalog_item"]
    assert env["build_prompt"].call_args.kwargs["include_intake_context"] is True


@pytest.mark.asyncio
async def test_a_composer_led_lead_is_untouched_by_the_flip():
    from app.services import intake as ik

    db = MagicMock()
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=_session()), \
         patch.object(ik, "is_brain_led", return_value=False), \
         patch.object(ik, "_update_session"), \
         patch.object(ik, "extract_fields", new=AsyncMock(return_value={"full_name": "Cheran"})), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "collector_identity", return_value=""), \
         patch.object(ik, "compose_line", new=AsyncMock(return_value="Unga DOB enna?")), \
         patch.object(ik, "_send_and_log", new=AsyncMock()) as send:
        consumed = await ik.route_intake(
            lead_id="l-1", tenant_id="t-1", phone="+919999999999", body="Cheran", db=db,
        )
    assert consumed is True
    send.assert_awaited_once()
