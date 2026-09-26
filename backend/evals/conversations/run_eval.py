"""Conversation eval: run scenarios.json against an engine and grade the transcript.

    cd backend && .venv/bin/python -m evals.conversations.run_eval --key-tenant <tenant_uuid> \
        [--engine legacy|new] [--only id1,id2] [--out results.json]

Design: docs/plans/ai-native-conversation.md. --engine legacy = the old route_intake state
machine (the baseline); --engine new = the AI-native engine (deal_turn.converse_once with the
production prompt builder, tools and guardrails).

What is REAL: intake.route_intake (the production state machine), every LLM call it makes
(trigger check, package match, field extraction, wording) using the key tenant's keys, and,
when route_intake hands a turn back, the production system-prompt builder plus a real model call.
What is SIMULATED: the DB (in-memory session store), WhatsApp sends (captured), the payment
link (fake URL), chat handovers (recorded).

Known limits of the legacy baseline (it under-counts the legacy engine, be fair when reading it):
  - When route_intake hands a turn back, only generate_reply's trigger C (asked for a human) is
    simulated. Triggers A/B/D/F and the catalog tools are NOT, so handover_on_unknown_twice
    under-counts the legacy engine.
  - Product scenarios are skipped: that path is generate_reply with tools, not route_intake.
Nothing is written to the database and no WhatsApp message is sent.
"""
import argparse
import asyncio
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

import app.services.ai_reply as ai_reply  # noqa: E402
import app.services.deal_actions as deal_actions  # noqa: E402
import app.services.deal_turn as deal_turn  # noqa: E402
import app.services.intake as intake  # noqa: E402
from app.services.knowledge_service import get_knowledge_context  # noqa: E402
from evals.conversations.checks import FAIL, PASS, SKIP, run_check  # noqa: E402

PHONE = "+910000000000"
LEAD_ID = "eval-lead"
LANGUAGE_MODE = "tanglish"
FALLTHROUGH_MAX_TOKENS = 600
PAID_STATUS, COLLECTING_STATUS, CONFIRM_STATUS = "paid", "collecting", "awaiting_confirmation"


class _StubQuery:
    """Every DB read comes back empty; writes are dropped."""

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=[])


class _StubDB:
    def table(self, _name):
        return _StubQuery()


class Sim:
    """In-memory stand-in for the DB and the outside world during one scenario."""

    def __init__(self, tenant_id: str, required: list[dict]):
        self.tenant_id = tenant_id
        self.required_keys = [f["key"] for f in required]
        self.sessions: dict[str, dict] = {}
        self.replies: list[dict] = []
        self.events: list[dict] = []
        self.link_count = 0
        self.debug: dict = {}

    def active_session(self) -> dict | None:
        rows = [s for s in self.sessions.values() if s["status"] in intake._ACTIVE_STATUSES]
        return rows[-1] if rows else None

    def missing_required(self, session: dict) -> list[str]:
        have = {k for k, v in (session.get("collected_data") or {}).items() if v}
        skipped = set(session.get("skipped_fields") or [])
        return [k for k in self.required_keys if k not in have and k not in skipped]


def _new_session(sim: Sim, status: str, extra: dict | None = None) -> dict:
    sid = f"sess-{len(sim.sessions) + 1}"
    row = {
        "id": sid, "lead_id": LEAD_ID, "tenant_id": sim.tenant_id, "status": status,
        "collected_data": {}, "skipped_fields": [], "ask_attempts": {}, "package_path": [],
        "package_draft_path": [], "selected_addons": None, "field_schema": [],
    } | (extra or {})
    sim.sessions[sid] = row
    return row


def _seed_session(sim: Sim, config: dict, state: dict) -> None:
    """Start a scenario mid-flow. Details are seeded with placeholder values."""
    package = next((p for p in config.get("packages", []) if p["key"] == state.get("selected")), None)
    if not package:
        return
    saved = {k: "seeded" for k in state.get("details_saved", [])}
    session = {
        "collected_data": saved, "package_key": package["key"], "package_name": package["name"],
        "package_amount_paise": package["amount_paise"], "total_amount_paise": package["amount_paise"],
        "field_schema": config.get("required_details", []),
    }
    if state.get("paid"):
        status = PAID_STATUS
    else:
        pending = [k for k in sim.required_keys if k not in saved]
        status = COLLECTING_STATUS if pending else CONFIRM_STATUS
    _new_session(sim, status, session)


def _install_patches(stack: ExitStack, sim: Sim, intake_config: dict) -> None:
    async def send(phone, text, tenant_id, lead_id, db):
        sim.replies.append({"text": text, "kind": "text", "options": []})

    async def send_buttons(phone, body, buttons, tenant_id, lead_id, db):
        sim.replies.append({"text": body, "kind": "buttons", "options": [b["title"] for b in buttons]})

    async def send_list(phone, body, button_text, sections, tenant_id, lead_id, db):
        titles = [r["title"] for s in sections for r in s.get("rows") or []]
        sim.replies.append({"text": body, "kind": "list", "options": titles})

    async def payment_link(**kwargs):
        sim.link_count += 1
        url = f"https://rzp.io/l/eval{sim.link_count}"
        session = sim.sessions.get((kwargs.get("notes") or {}).get("booking_id"), {})
        sim.events.append({"type": "payment_link", "url": url, "missing_required": sim.missing_required(session)})
        return {"payment_link_url": url}

    def create(lead_id, tenant_id, db):
        return _new_session(sim, "offer_pending")

    def update(session_id, patch_, db):
        sim.sessions[session_id].update(patch_)

    def handover(lead_id, reason, tenant_id, assigned_to, db):
        sim.events.append({"type": "handover", "reason": reason})

    async def gather(db, lead_id, tenant_id, message):
        return [], ""

    targets = {
        (intake, "get_intake_config"): lambda tenant_id, db=None: intake_config,
        (intake, "_get_active_session"): lambda lead_id, tenant_id, db: sim.active_session(),
        (intake, "_create_session"): create,
        (intake, "_update_session"): update,
        (intake, "get_in_progress_session"): lambda lead_id, tenant_id, db=None: (
            (s := sim.active_session()) and s["status"] in intake._IN_PROGRESS_STATUSES and s or None
        ),
        (intake, "get_paid_unresolved_session"): lambda lead_id, tenant_id, db=None: (
            (s := sim.active_session()) and s["status"] == PAID_STATUS and s or None
        ),
        (intake, "_send_and_log"): send,
        (intake, "_send_buttons_and_log"): send_buttons,
        (intake, "_send_list_and_log"): send_list,
        (intake, "create_payment_link"): payment_link,
        (intake, "resolve_language_mode"): lambda lead_id, tenant_id, db: LANGUAGE_MODE,
        (intake, "gather_context"): gather,
        (intake, "collector_identity"): lambda db, lead_id, tenant_id, message: "",
        (ai_reply, "_trigger_chat_escalation"): handover,
    }
    for (module, name), replacement in targets.items():
        stack.enter_context(patch.object(module, name, replacement))


def _build_intake_config(config: dict, live: dict) -> dict:
    return {
        "enabled": True,
        "trigger_description": live["trigger_description"],
        "offer_message": live["offer_message"],
        "fields": config.get("required_details", []),
        "packages": config.get("packages", []),
        "service_noun": config.get("service_noun", "consultation"),
        "amount_paise": 0,
    }


async def _fallthrough_reply(sim: Sim, history: list[dict], message: str, key_tenant: str) -> str:
    """route_intake handed the turn back: build the reply the way generate_reply would."""
    knowledge = await get_knowledge_context(key_tenant, query=message) or ""
    lead = {"name": "", "segment": "C", "tenant_id": key_tenant, "needs_human_attention": False}
    system_prompt, _mode, _flag = ai_reply.build_reply_system_prompt(
        _StubDB(), LEAD_ID, key_tenant, lead, message, "whatsapp",
        context_text=knowledge, include_intake_context=True,
    )
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": message}]
    return (await ai_reply._llm_chat(messages, max_tokens=FALLTHROUGH_MAX_TOKENS, tenant_id=key_tenant)).strip()


def _logged_text(reply: dict) -> str:
    """How production stores an outbound message: menus are logged with their options."""
    if reply["kind"] in ("buttons", "list"):
        return deal_turn.menu_log_text(reply["text"], reply)
    return reply["text"]


def _turn_input(turn) -> tuple[str, str | None]:
    return (turn["text"], turn["tap"]) if isinstance(turn, dict) else (turn, None)


async def _legacy_turn(sim: Sim, history: list[dict], body: str, tap: str | None, key_tenant: str) -> bool:
    consumed = await intake.route_intake(LEAD_ID, key_tenant, PHONE, body, db=_StubDB(), interactive_id=tap)
    if not consumed:
        text = await _fallthrough_reply(sim, history, body, key_tenant)
        sim.replies.append({"text": text, "kind": "text", "options": []})
        if ai_reply._HUMAN_REQUEST_RE.search(body) and not sim.events:
            # generate_reply's trigger C ("asked for a human") always fires.
            sim.events.append({"type": "handover", "reason": "User requested a human agent"})
    return consumed


async def _new_turn(sim: Sim, history: list[dict], body: str, tap: str | None, key_tenant: str, config: dict) -> bool:
    """The AI-native engine, wired the way generate_reply wires it."""
    db = _StubDB()
    ctx = deal_actions.DealContext(config=config, db=db, lead_id=LEAD_ID, tenant_id=key_tenant, phone=PHONE)
    guard_fired = deal_turn.pre_turn_guards(ctx, body)
    await deal_turn.capture_details(ctx, body)
    knowledge = await get_knowledge_context(key_tenant, query=body) or ""
    lead = {"name": "", "segment": "C", "tenant_id": key_tenant, "needs_human_attention": False}
    system_prompt, _mode, _flag = ai_reply.build_reply_system_prompt(
        db, LEAD_ID, key_tenant, lead, body, "whatsapp", context_text=knowledge, tapped_option_key=tap,
    )
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": body}]
    text, calls, outcome = await deal_turn.converse_once(
        messages, [], ctx, tenant_id=key_tenant, handover_opened=guard_fired,
        handover_line=ai_reply._handover_line(key_tenant),
    )
    sim.debug = {
        "tool_calls": [(c.get("function") or {}).get("name") + " " + str((c.get("function") or {}).get("arguments")) for c in calls],
        "refusals": list(outcome.refusals),
    }
    if ai_reply._HUMAN_REQUEST_RE.search(body) and not any(e["type"] == "handover" for e in sim.events):
        # generate_reply's trigger C ("asked for a human") always fires, on every path.
        sim.events.append({"type": "handover", "reason": "User requested a human agent"})
    menu = outcome.menu
    sim.replies.append({
        "text": text, "kind": menu["kind"] if menu else "text", "options": menu["options"] if menu else [],
    })
    return False


async def run_scenario(scenario: dict, config: dict, live_cfg: dict, key_tenant: str, engine: str = "legacy") -> list[dict]:
    sim = Sim(key_tenant, config.get("required_details", []))
    _seed_session(sim, config, scenario.get("state") or {})
    intake_config = _build_intake_config(config, live_cfg)
    transcript: list[dict] = []
    history: list[dict] = []
    with ExitStack() as stack:
        _install_patches(stack, sim, intake_config)
        for turn in scenario["lead_turns"]:
            body, tap = _turn_input(turn)
            sim.replies, sim.events, sim.debug = [], [], {}
            started = time.monotonic()
            if engine == "new":
                consumed = await _new_turn(sim, history, body, tap, key_tenant, intake_config)
            else:
                consumed = await _legacy_turn(sim, history, body, tap, key_tenant)
            history.append({"role": "user", "content": body})
            history.extend({"role": "assistant", "content": _logged_text(r)} for r in sim.replies)
            transcript.append({
                "lead": body, "replies": sim.replies, "events": sim.events,
                "seconds": round(time.monotonic() - started, 1), "consumed": consumed, "debug": sim.debug,
            })
    return transcript


def grade(scenario: dict, transcript: list[dict], config: dict) -> list[dict]:
    results = [run_check(name, transcript, config) for name in scenario["expect"]["hard"]]
    return [{"name": r.name, "status": r.status, "detail": r.detail} for r in results]


def _print_report(rows: list[dict]) -> None:
    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    for row in rows:
        marks = " ".join(f"{c['name']}={c['status'].upper()}" for c in row["checks"])
        print(f"- {row['id']}: {marks}")
        for c in row["checks"]:
            counts[c["status"]] += 1
            if c["status"] == FAIL:
                print(f"    FAIL {c['name']}: {c['detail']}")
    decided = counts[PASS] + counts[FAIL]
    rate = f"{100 * counts[PASS] / decided:.0f}%" if decided else "n/a"
    print(f"\nHard checks: {counts[PASS]} pass, {counts[FAIL]} fail, {counts[SKIP]} skipped -> pass rate {rate}")
    print("LLM judge: not run (phase P1 covers the hard checks only)")


async def main_async(args) -> None:
    data = json.loads((HERE / "scenarios.json").read_text())
    live_cfg = intake.get_intake_config(args.key_tenant)
    wanted = set(args.only.split(",")) if args.only else None
    rows: list[dict] = []
    for scenario in data["scenarios"]:
        if wanted and scenario["id"] not in wanted:
            continue
        config = data["configs"][scenario["config"]]
        if config.get("kind") == "product":
            print(f"- {scenario['id']}: skipped (product path is not route_intake)")
            continue
        transcript = await run_scenario(scenario, config, live_cfg, args.key_tenant, args.engine)
        rows.append({"id": scenario["id"], "transcript": transcript, "checks": grade(scenario, transcript, config)})
    _print_report(rows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"Transcripts written to {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-tenant", required=True)
    parser.add_argument("--engine", choices=["legacy", "new"], default="legacy")
    parser.add_argument("--only", help="comma-separated scenario ids")
    parser.add_argument("--out")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
