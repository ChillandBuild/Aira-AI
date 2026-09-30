"""Unit tests for the returning-lead eval (R3): the new check types in checks.py, the
continue-question classifier, the scenario templating and gate in returning.py, and the write
guard. No model calls, no database."""
import asyncio
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from evals.conversations import checks, judge, returning, write_guard

FUTURE = (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _turn(*, lead="hi", text="ok", tools=(), events=(), deal=None, asks=None):
    turn = {
        "lead": lead, "replies": [{"text": text, "kind": "text", "options": []}], "events": list(events),
        "debug": {"tool_calls": list(tools), "deal": deal},
    }
    if asks is not None:
        turn["asks_continue"] = asks
    return turn


def _cfg(*turns, **extra):
    return {"expect": {"turns": list(turns), **extra}}


def _link(amount=9900, expires=FUTURE, url="https://rzp.io/l/eval1"):
    return {"type": "payment_link", "url": url, "missing_required": [], "amount_paise": amount, "expires_at": expires}


DEAL = {"package_key": "one_question", "status": "awaiting_payment", "current_charge_paise": 9900}


# ---- returning_close
def test_close_deal_on_a_non_decline_is_a_wrong_close():
    result = checks.returning_close([_turn(tools=['close_deal {}'])], _cfg({"close": False}))
    assert result.status == checks.FAIL and "WRONG_CLOSE" in result.detail


def test_close_deal_with_nothing_expected_defaults_to_a_wrong_close():
    assert checks.returning_close([_turn(tools=['close_deal {}'])], _cfg()).status == checks.FAIL


def test_explicit_decline_must_call_close_deal_and_close_the_deal():
    closed = _turn(tools=['close_deal {}'], events=[{"type": "deal_closed"}])
    assert checks.returning_close([closed], _cfg({"close": True})).status == checks.PASS
    missed = checks.returning_close([_turn()], _cfg({"close": True}))
    assert missed.status == checks.FAIL and "MISSED_CLOSE" in missed.detail
    unclosed = checks.returning_close([_turn(tools=['close_deal {}'])], _cfg({"close": True}))
    assert unclosed.status == checks.FAIL


def test_no_close_and_none_expected_passes():
    assert checks.returning_close([_turn()], _cfg({"close": False})).status == checks.PASS


# ---- returning_link
def test_live_link_at_todays_price_passes():
    turn = _turn(events=[_link()], deal=DEAL)
    assert checks.returning_link([turn], _cfg({"link": True})).status == checks.PASS


def test_expired_link_is_a_dead_link():
    turn = _turn(events=[_link(expires=PAST)], deal=DEAL)
    result = checks.returning_link([turn], _cfg({"link": True}))
    assert result.status == checks.FAIL and "dead link" in result.detail


def test_old_price_link_fails():
    turn = _turn(events=[_link(amount=4900)], deal=DEAL)
    result = checks.returning_link([turn], _cfg({"link": True}))
    assert result.status == checks.FAIL and "old-price" in result.detail


def test_razorpay_url_not_made_this_turn_is_a_dead_link():
    turn = _turn(text="Pay here https://rzp.io/l/dead1234", deal=DEAL)
    assert "dead or copied" in checks.returning_link([turn], _cfg()).detail


def test_link_expected_but_missing_and_link_not_wanted_but_sent():
    assert checks.returning_link([_turn(deal=DEAL)], _cfg({"link": True})).status == checks.FAIL
    sent = _turn(events=[_link()], deal=DEAL)
    assert checks.returning_link([sent], _cfg({"link": False})).status == checks.FAIL


# ---- returning_question
def test_question_expected_and_asked_passes_and_wrong_way_fails():
    assert checks.returning_question([_turn(asks=True)], _cfg({"ask": True})).status == checks.PASS
    assert checks.returning_question([_turn(asks=False)], _cfg({"ask": True})).status == checks.FAIL
    assert checks.returning_question([_turn(asks=True)], _cfg({"ask": False})).status == checks.FAIL


def test_question_undecided_is_skipped_never_passed():
    assert checks.returning_question([_turn()], _cfg({"ask": True})).status == checks.SKIP


def test_question_not_stated_is_not_checked():
    assert checks.returning_question([_turn(asks=True)], _cfg({"close": False})).status == checks.PASS


# ---- returning_new_booking
def test_new_booking_needs_the_flag_and_the_old_deal_closed_first():
    made = _turn(tools=['select_offering {"key": "x", "new_booking": true}'], events=[{"type": "deal_closed"}])
    assert checks.returning_new_booking([made], _cfg({"new_booking": True})).status == checks.PASS
    no_close = _turn(tools=['select_offering {"key": "x", "new_booking": true}'])
    assert checks.returning_new_booking([no_close], _cfg({"new_booking": True})).status == checks.FAIL
    assert checks.returning_new_booking([_turn()], _cfg({"new_booking": True})).status == checks.FAIL


def test_new_booking_used_when_not_expected_fails_unless_scenario_does_not_care():
    made = _turn(tools=['select_offering {"key": "x", "new_booking": true}'])
    assert checks.returning_new_booking([made], _cfg({"close": False})).status == checks.FAIL
    assert checks.returning_new_booking([made], _cfg({"new_booking": None})).status == checks.PASS


# ---- returning_confirm_details
def test_confirm_details_must_show_previous_details_and_send_no_link():
    cfg = _cfg({"confirm_details": True}, previous_values=["Karthik"])
    assert checks.returning_confirm_details([_turn(text="Same as before, Karthik?")], cfg).status == checks.PASS
    assert checks.returning_confirm_details([_turn(text="Which offering?")], cfg).status == checks.FAIL
    linked = _turn(text="Karthik, pay here", events=[_link()])
    assert checks.returning_confirm_details([linked], cfg).status == checks.FAIL


def test_details_saved_silently_fail_the_confirm_and_no_save_checks():
    saved = _turn(text="Karthik?", tools=['save_details {"details": {}}'])
    cfg = _cfg({"confirm_details": True}, previous_values=["Karthik"])
    assert checks.returning_confirm_details([saved], cfg).status == checks.FAIL
    assert checks.returning_confirm_details([saved], _cfg({"no_save": True})).status == checks.FAIL
    assert checks.returning_confirm_details([_turn()], _cfg({"no_save": True})).status == checks.PASS


# ---- returning_package
def test_package_must_match_the_open_deal_at_the_end_of_the_turn():
    assert checks.returning_package([_turn(deal=DEAL)], _cfg({"package": "one_question"})).status == checks.PASS
    assert checks.returning_package([_turn(deal=DEAL)], _cfg({"package": "detailed"})).status == checks.FAIL
    assert checks.returning_package([_turn(deal=None)], _cfg({"package": "detailed"})).status == checks.FAIL


def test_new_checks_are_registered():
    for name in checks.RETURNING_CHECKS:
        assert name in checks.HARD_CHECKS


# ---- the continue-question classifier
def _run(coro):
    return asyncio.run(coro)


def test_classifier_reads_the_boolean_and_fails_safe():
    async def yes(*a, **k):
        return {"asks": True}

    async def junk(*a, **k):
        return {"asks": "maybe"}

    async def boom(*a, **k):
        raise RuntimeError("provider down")

    assert _run(judge.asks_continue_question("hi", "Continue?", "t", llm_json=yes)) is True
    assert _run(judge.asks_continue_question("hi", "Continue?", "t", llm_json=junk)) is None
    assert _run(judge.asks_continue_question("hi", "Continue?", "t", llm_json=boom)) is None


# ---- templating and the gate
CONFIG = {
    "packages": [{"key": "one_question", "name": "One Question", "amount_paise": 100},
                 {"key": "detailed", "name": "Detailed", "amount_paise": 200}],
    "roles": {"cheap": "one_question", "dear": "detailed"},
    "detail_keys": {"name": "full_name", "dob": "date_of_birth"},
}


def test_expand_replaces_tokens_and_drops_what_the_tenant_lacks():
    scenario = {
        "state": {"selected": "{pkg.cheap}", "collected": {"{d.name}": "Karthik", "{d.gender}": "male"},
                  "stale_amount_paise": "{price.cheap.old}"},
        "lead_turns": ["I want the {name.dear}", "{d.gender} unknown"],
    }
    out = returning.expand(scenario, CONFIG)
    assert out["state"]["selected"] == "one_question"
    assert out["state"]["collected"] == {"full_name": "Karthik"}
    assert out["state"]["stale_amount_paise"] == 100 + returning.STALE_EXTRA_PAISE
    assert out["lead_turns"] == ["I want the Detailed"]


def test_shipped_scenarios_expand_for_every_tenant_and_meet_the_size_and_language_bar():
    data = json.loads((Path(returning.__file__).parent / "scenarios_returning.json").read_text())
    assert len(data["scenarios"]) >= 50
    assert sum(s["source"] == "real" for s in data["scenarios"]) >= len(data["scenarios"]) * 0.4
    for name, config in data["configs"].items():
        assert config["packages"] and config["required_details"], name
        for scenario in data["scenarios"]:
            expanded = returning.expand(scenario, config)
            assert expanded["state"].get("selected") in (None, *[p["key"] for p in config["packages"]]), (name, scenario["id"])
            assert expanded["lead_turns"], (name, scenario["id"])


def _row(sid, turns):
    return {"id": sid, "transcript": turns, "checks": [], "config": "x"}


def test_gate_counts_wrong_closes_dead_links_and_right_actions():
    scenarios = {
        "a": {"expect": {"turns": [{"close": False}]}}, "b": {"expect": {"turns": [{"link": True}]}},
        "c": {"expect": {"turns": [{"close": False}]}},
    }
    rows = [
        _row("a", [_turn(tools=["close_deal {}"])]),                       # wrong close
        _row("b", [_turn(events=[_link(expires=PAST)], deal=DEAL)]),     # dead link
        _row("c", [_turn()]),                                            # fine
    ]
    result = returning.gate(rows, scenarios, CONFIG)
    assert (result["wrong_closes"], result["bad_links"], result["right"]) == (1, 1, 1)
    assert result["passed"] is False


def test_gate_passes_only_with_zero_bad_and_ninety_percent_right():
    scenarios = {f"s{i}": {"expect": {"turns": [{"close": False}]}} for i in range(10)}
    rows = [_row(sid, [_turn()]) for sid in scenarios]
    assert returning.gate(rows, scenarios, CONFIG)["passed"] is True
    rows[0] = _row("s0", [_turn(tools=["close_deal {}"])])
    assert returning.gate(rows, scenarios, CONFIG)["passed"] is False


# ---- the write guard
def test_write_guard_refuses_writes_and_lets_reads_and_search_rpcs_through():
    def request(method, path):
        return httpx.Request(method, f"https://x.supabase.co{path}")

    assert write_guard.is_read(request("GET", "/rest/v1/leads"))
    assert write_guard.is_read(request("POST", "/rest/v1/rpc/match_knowledge_chunks"))
    assert not write_guard.is_read(request("POST", "/rest/v1/rpc/increment_token_usage"))
    assert not write_guard.is_read(request("POST", "/rest/v1/messages"))
    assert not write_guard.is_read(request("PATCH", "/rest/v1/leads"))
    assert not write_guard.is_read(request("DELETE", "/rest/v1/leads"))


def test_write_guard_install_blocks_a_write_and_records_it():
    from app.db import supabase as supabase_module

    write_guard.blocked.clear()
    transport = supabase_module._RetryTransport(httpx.MockTransport(lambda r: httpx.Response(200, json=["real"])))
    with ExitStack() as stack:
        write_guard.install(stack)
        read = transport.handle_request(httpx.Request("GET", "https://x.supabase.co/rest/v1/leads"))
        write = transport.handle_request(httpx.Request("POST", "https://x.supabase.co/rest/v1/messages"))
    assert read.json() == ["real"] and write.json() == []
    assert write_guard.blocked == ["POST /rest/v1/messages"]
    write_guard.blocked.clear()
