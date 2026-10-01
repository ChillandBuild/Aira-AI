"""AstroTamil clients: the bot must collect a date, time and gender AstroTamil can use BEFORE the
payment link goes out. Live miss 2026-09-30: "19112003" and "theriyathu" were saved as typed, the
link was sent, the customer paid, and the push to AstroTamil was then refused with only a log line.

Clients without the AstroTamil connection must behave exactly as before; the last class proves it."""
import asyncio
from unittest.mock import patch

import pytest
from test_deal_actions import LEAD, TENANT, call, world  # noqa: F401  (world is a fixture)

from app.services import astro_bridge, deal_actions

PHONE = "+916369781582"  # a number AstroTamil accepts; the shared test phone is not a valid one


def run(calls, config):
    ctx = deal_actions.DealContext(config=config, db=object(), lead_id=LEAD, tenant_id=TENANT, phone=PHONE)
    return asyncio.run(deal_actions.apply_tool_calls(calls, ctx))

# The live Astro Tamil intake form on 2026-10-01.
ASTRO_CONFIG = {
    "enabled": True,
    "service_noun": "question",
    "fields": [
        {"key": "name", "label": "Name", "type": "text"},
        {"key": "gender", "label": "Gender", "type": "choice", "options": ["Male", "Female"]},
        {"key": "date_of_birth", "label": "Date of birth", "type": "text"},
        {"key": "place_of_birth", "label": "Place of Birth", "type": "text"},
        {"key": "time_of_birth", "label": "Time of Birth", "type": "text"},
        {"key": "question", "label": "Question", "type": "text"},
    ],
    "packages": [{"key": "one_question", "name": "One Question", "amount_paise": 100, "button_label": "1 Rs"}],
}
_CONNECTED = {"astro_bridge_url": "https://astro.example.com", "astro_bridge_api_key": "k"}


@pytest.fixture
def connected():
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: _CONNECTED.get(k, fallback)):
        yield


def _session(world):
    return next(iter(world.sessions.values()))


def _start(world, **details):
    run([call("select_offering", key="one_question")], ASTRO_CONFIG)
    if details:
        run([call("save_details", fields=details)], ASTRO_CONFIG)


def _save(**fields):
    return run([call("save_details", fields=fields)], ASTRO_CONFIG)


@pytest.mark.usefixtures("connected")
class TestAnswerGuard:
    def test_compact_date_is_read_and_stored_as_a_real_date(self, world):
        _start(world)
        out = _save(date_of_birth="19112003")
        assert not out.refusals
        assert _session(world)["collected_data"]["date_of_birth"] == "2003-11-19"

    @pytest.mark.parametrize("typed,stored", [
        ("19-11-2003", "2003-11-19"), ("19.11.2003", "2003-11-19"), ("19 Nov 2003", "2003-11-19"),
        ("2003-11-19", "2003-11-19"),
    ])
    def test_every_common_date_shape_is_stored_the_same_way(self, world, typed, stored):
        _start(world)
        _save(date_of_birth=typed)
        assert _session(world)["collected_data"]["date_of_birth"] == stored

    @pytest.mark.parametrize("typed", ["31-02-2003", "sometime in 2003", "1911203", "19112099", "naalaikku"])
    def test_an_unusable_date_is_not_saved_and_the_model_is_told_how_to_ask(self, world, typed):
        _start(world)
        out = _save(date_of_birth=typed)
        assert "date_of_birth" not in _session(world)["collected_data"]
        assert out.refusals and "date_of_birth" in out.refusals[0]

    def test_unreadable_date_refusal_gives_the_format_to_ask_for(self, world):
        _start(world)
        assert "19-11-2003" in _save(date_of_birth="sometime in 2003").refusals[0]

    @pytest.mark.parametrize("typed,stored", [
        ("10:30 am", "10:30 AM"), ("6 pm", "06:00 PM"), ("evening 6", "06:00 PM"),
        ("17:45", "05:45 PM"), ("10.30pm", "10:30 PM"), ("மாலை 6", "06:00 PM"),
    ])
    def test_time_is_stored_in_one_unambiguous_form(self, world, typed, stored):
        _start(world)
        assert not _save(time_of_birth=typed).refusals
        assert _session(world)["collected_data"]["time_of_birth"] == stored

    @pytest.mark.parametrize("typed", ["10:30", "5.30", "1030"])
    def test_time_without_am_pm_is_not_saved_and_am_pm_is_asked(self, world, typed):
        _start(world)
        out = _save(time_of_birth=typed)
        assert "time_of_birth" not in _session(world)["collected_data"]
        assert "AM or PM" in out.refusals[0]

    @pytest.mark.parametrize("typed", ["theriyathu", "தெரியாது", "don't know", "pata nahi"])
    def test_unknown_time_is_not_saved_as_typed_and_one_approximate_time_is_asked_for(self, world, typed):
        _start(world)
        out = _save(time_of_birth=typed)
        assert "time_of_birth" not in _session(world)["collected_data"]
        refusal = out.refusals[0]
        assert "approximate" in refusal and "skip_detail" in refusal

    def test_a_real_time_inside_an_i_dont_know_sentence_is_saved(self, world):
        _start(world)
        assert not _save(time_of_birth="theriyathu, around 6 am").refusals
        assert _session(world)["collected_data"]["time_of_birth"] == "06:00 AM"

    def test_unreadable_time_gets_an_example(self, world):
        _start(world)
        assert "10:30 am" in _save(time_of_birth="abc").refusals[0]

    def test_gender_must_be_one_of_the_form_options(self, world):
        _start(world)
        assert _save(gender="theriyathu").refusals
        assert "gender" not in _session(world)["collected_data"]
        assert not _save(gender="female").refusals
        assert _session(world)["collected_data"]["gender"] == "Female"

    def test_the_good_answers_in_a_mixed_message_are_still_saved(self, world):
        _start(world)
        out = _save(name="Keerthi", date_of_birth="19112003", time_of_birth="theriyathu")
        data = _session(world)["collected_data"]
        assert data == {"name": "Keerthi", "date_of_birth": "2003-11-19"}
        assert out.refusals


@pytest.mark.usefixtures("connected")
class TestSkipGuard:
    @pytest.mark.parametrize("key", ["date_of_birth", "gender", "question"])
    def test_a_detail_astrotamil_cannot_work_without_cannot_be_skipped(self, world, key):
        _start(world)
        out = run([call("skip_detail", key=key)], ASTRO_CONFIG)
        assert out.refusals and _session(world)["skipped_fields"] == []

    @pytest.mark.parametrize("key", ["time_of_birth", "place_of_birth", "name"])
    def test_birth_time_place_and_name_can_be_skipped(self, world, key):
        _start(world)
        out = run([call("skip_detail", key=key)], ASTRO_CONFIG)
        assert not out.refusals and _session(world)["skipped_fields"] == [key]


@pytest.mark.usefixtures("connected")
class TestPaymentGuard:
    GOOD = {"name": "Keerthi", "gender": "Male", "date_of_birth": "2003-11-19",
            "place_of_birth": "Neyveli", "time_of_birth": "10:30 AM", "question": "job eppo?"}

    def _link(self, world, collected, skipped=()):
        _start(world)
        session = _session(world)
        session["collected_data"] = collected
        session["skipped_fields"] = list(skipped)
        return run([call("create_payment_link")], ASTRO_CONFIG)

    def test_a_good_set_of_answers_gets_the_link(self, world):
        out = self._link(world, dict(self.GOOD))
        assert out.payment_link and not out.refusals

    def test_unreadable_date_saved_before_the_guard_existed_blocks_the_link(self, world):
        out = self._link(world, {**self.GOOD, "date_of_birth": "sometime in the 90s"})
        assert not out.payment_link and not world.links
        assert "birth date" in out.refusals[0]

    def test_junk_gender_blocks_the_link(self, world):
        out = self._link(world, {**self.GOOD, "gender": "theriyathu"})
        assert not world.links and "gender" in out.refusals[0]

    def test_unknown_birth_time_does_not_block_the_link(self, world):
        collected = {k: v for k, v in self.GOOD.items() if k != "time_of_birth"}
        out = self._link(world, collected, skipped=["time_of_birth"])
        assert out.payment_link and not out.refusals

    def test_the_link_check_is_the_check_the_push_uses(self, world):
        collected = {**self.GOOD, "time_of_birth": "abc"}
        out = self._link(world, collected)
        assert not world.links
        assert astro_bridge.unusable_for_push(collected, [], PHONE) == ["birth time"]
        assert "birth time" in out.refusals[0]


class TestClientsWithoutTheConnectionAreUntouched:
    """conftest saves no AstroTamil settings, so TENANT is an ordinary client."""

    def test_answers_are_saved_exactly_as_typed(self, world):
        _start(world)
        out = _save(date_of_birth="19112003", time_of_birth="theriyathu", gender="Male")
        assert not out.refusals
        assert _session(world)["collected_data"] == {
            "date_of_birth": "19112003", "time_of_birth": "theriyathu", "gender": "Male"}

    def test_any_detail_can_be_skipped(self, world):
        _start(world)
        assert not run([call("skip_detail", key="date_of_birth")], ASTRO_CONFIG).refusals

    def test_the_link_is_not_held_back(self, world):
        _start(world)
        _session(world)["collected_data"] = {
            "name": "K", "gender": "x", "date_of_birth": "??", "place_of_birth": "p",
            "time_of_birth": "??", "question": "q"}
        assert run([call("create_payment_link")], ASTRO_CONFIG).payment_link
