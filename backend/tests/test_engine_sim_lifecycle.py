"""The eval simulator (evals/conversations/engine_sim.py) mirrors the R3 lifecycle, so returning-lead
and decline scenarios can run offline against the production prompt and tools: the away time
shows in DEAL STATE, close_deal closes the simulated deal, and both are visible in the transcript."""
import asyncio
import json
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.services import ai_reply, deal_actions
from evals.conversations import engine_sim
from evals.conversations.engine_sim import World

CONFIG = {
    "packages": [
        {"key": "one_question", "name": "One Question", "amount_paise": 4900, "description": "x"},
        {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900, "description": "y"},
    ],
    "required_details": [{"key": "name", "label": "Full name", "type": "text"}],
}
STATE = {"selected": "one_question", "collected": {"name": "Vivek"}, "link": {"expires_in_hours": 20}}


@pytest.fixture
def sim():
    with ExitStack() as stack:
        engine_sim.install(stack)
        engine_sim.install_settings(stack)
        # The base prompt reads the tenant's settings from the database: not in a unit test.
        stack.enter_context(patch.object(ai_reply, "_build_base_prompt", return_value="BASE"))
        yield


def _world(state: dict) -> World:
    world = World("tenant-1", CONFIG)
    world.settings = {"reply_language_mode": "mirror", "app_download_link": ""}
    engine_sim.CURRENT.set(world)
    world.seed(state)
    return world


def _prompt(world: World, away: timedelta | None) -> str:
    last_seen = world.note_lead_message(away)
    return ai_reply.build_reply_system_prompt(
        engine_sim.StubDB(), engine_sim.LEAD_ID, "tenant-1", {"name": "", "segment": "C", "tenant_id": "tenant-1"},
        "hi", "whatsapp", last_seen_at=last_seen,
    )[0]


def _call(name, **args):
    return [{"function": {"name": name, "arguments": json.dumps(args)}}]


def _apply(world: World, calls):
    ctx = deal_actions.DealContext(config=world.intake_config, db=engine_sim.StubDB(), lead_id=engine_sim.LEAD_ID,
                                   tenant_id="tenant-1", phone=engine_sim.PHONE)
    return asyncio.run(deal_actions.apply_tool_calls(calls, ctx))


def test_away_time_reaches_deal_state_and_the_return_instruction(sim):
    world = _world({**STATE, "away_days": 4})
    prompt = _prompt(world, None)
    assert "Last message from them: 4 days ago" in prompt
    assert "THE CUSTOMER IS BACK" in prompt
    assert "IST" in prompt  # the live link's expiry


def test_a_per_turn_away_overrides_and_the_message_restarts_the_clock(sim):
    world = _world(STATE)
    assert "THE CUSTOMER IS BACK" not in _prompt(world, None)
    assert "THE CUSTOMER IS BACK" in _prompt(world, timedelta(hours=30))
    assert "THE CUSTOMER IS BACK" not in _prompt(world, None)  # they just wrote


def test_an_expired_seeded_link_is_reported_in_deal_state(sim):
    world = _world({**STATE, "link": "expired"})
    assert "new one will be made" in _prompt(world, None)


def test_close_deal_closes_the_simulated_deal_and_cancels_its_live_link(sim):
    world = _world(STATE)
    out = _apply(world, _call("close_deal", reason="venam"))
    assert not out.refusals
    assert world.active_session() is None
    assert [e["type"] for e in world.events] == ["deal_closed", "plink_cancelled"]


def test_new_booking_closes_the_old_deal_first(sim):
    world = _world(STATE)
    out = _apply(world, _call("select_offering", key="detailed", new_booking=True))
    assert not out.refusals
    assert [s["status"] for s in world.sessions.values()][0] == "cancelled"
    assert world.active_session()["package_key"] == "detailed"
    assert world.active_session()["collected_data"] == {}


def test_a_previous_booking_is_seeded_and_offered_back(sim):
    world = _world({"previous": {"selected": "one_question", "collected": {"name": "Vivek"}}})
    assert "PREVIOUS BOOKING (their earlier One Question" in _prompt(world, None)
