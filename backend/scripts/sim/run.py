"""Drive every persona through the real reply pipeline and write a report.

    python -m scripts.sim.run --tenant <uuid>
    python -m scripts.sim.run --tenant <uuid> --personas time_dependent,fact_stress
    python -m scripts.sim.run --cleanup <run_id>

Run from backend/. Leads it creates are named "[SIM] <persona>" and carry the run
id in `notes`, so --cleanup can find and remove every row a run produced.

Test leads use ITU country code +999, reserved for trials and never routable, so
a follow-up job that outlives cleanup still cannot reach a real handset.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sim import blocks, judge, personas, rules  # noqa: E402
from scripts.sim.harness import run_turn  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sim")

SIM_NAME_PREFIX = "[SIM]"
_TEST_PHONE_CC = "+999"
_LEAD_TABLES = ("messages", "lead_stage_events", "follow_up_jobs", "lead_conversation_state")


def _sim_phone(run_id: str, index: int) -> str:
    # run_id is hex, so strip it to digits and pad -- a phone column with letters
    # in it trips validation further down the pipeline.
    digits = "".join(c for c in run_id if c.isdigit()).ljust(7, "0")[:7]
    return f"{_TEST_PHONE_CC}{digits}{index:02d}"


def _create_lead(db, tenant_id: str, persona: personas.Persona, run_id: str, index: int) -> str:
    row = (
        db.table("leads")
        .insert(
            {
                "tenant_id": tenant_id,
                "name": f"{SIM_NAME_PREFIX} {persona.label}",
                "phone": _sim_phone(run_id, index),
                # `source` is constrained to the real acquisition channels, so the
                # simulator borrows "manual" rather than adding a value to a live
                # tenant's schema. The name prefix and notes are the real markers.
                "source": "manual",
                "notes": f"sim_run_id={run_id}",
                "segment": "C",
                "ai_enabled": True,
            }
        )
        .execute()
    )
    return row.data[0]["id"]


async def run_persona(
    db,
    tenant_id: str,
    persona: personas.Persona,
    run_id: str,
    index: int,
    *,
    live_notifications: bool,
    master_override: str | None = None,
) -> dict:
    lead_id = _create_lead(db, tenant_id, persona, run_id, index)
    print(f"\n[{persona.key}] lead {lead_id}")

    conversation: list[tuple[str, str]] = []
    turns: list[dict] = []
    message = persona.opening

    for turn_no in range(1, persona.turns + 1):
        turn = await run_turn(
            lead_id,
            tenant_id,
            message,
            live_notifications=live_notifications,
            master_override=master_override,
            db=db,
        )
        conversation.append(("Customer", message))
        conversation.append(("Assistant", turn.reply_text))

        language_mode = ""
        if "LANGUAGE STYLE" in turn.system_prompt:
            # The mode name is not in the prompt text; re-derive it the same way
            # the pipeline did so the script check grades against the real target.
            try:
                from app.services.ai_reply import _resolve_reply_language_mode

                language_mode = _resolve_reply_language_mode(tenant_id)
            except Exception:
                language_mode = ""

        hard = rules.check(turn.reply_text, turn.system_prompt, language_mode=language_mode)
        verdict = await judge.judge_turn(
            system_prompt=turn.system_prompt,
            conversation=conversation,
            reply=turn.reply_text,
            watch_for=persona.watch,
            tenant_id=tenant_id,
        )

        flag = "!" if (hard or verdict.is_failure) else " "
        print(f"  {flag} turn {turn_no}: {message[:48]!r}")
        print(f"      -> {turn.reply_text[:90]!r}")
        for finding in hard:
            print(f"      [{finding.severity}] {finding.code}: {finding.detail[:100]}")
        if verdict.is_failure:
            print(f"      [judge/{verdict.severity}] {verdict.summary[:110]}")

        turns.append(
            {
                "turn": turn_no,
                "customer": message,
                "reply": turn.reply_text,
                "prompt_chars": len(turn.system_prompt),
                "prompt_blocks": [
                    {"label": b.label, "chars": b.chars}
                    for b in blocks.split_blocks(turn.system_prompt)
                ],
                "history_chars": turn.history_chars,
                "tools_offered": turn.tools_offered,
                "sends": turn.sends,
                "suppressed": sorted(set(turn.suppressed)),
                "latency_ms": turn.latency_ms,
                "pipeline_error": turn.error,
                "findings": [
                    {"severity": f.severity, "code": f.code, "detail": f.detail} for f in hard
                ],
                "judge": {
                    "grounded": verdict.grounded,
                    "unsupported_claims": list(verdict.unsupported_claims),
                    "stayed_in_scope": verdict.stayed_in_scope,
                    "tone_ok": verdict.tone_ok,
                    "answered_the_question": verdict.answered_the_question,
                    "watch_triggered": verdict.watch_triggered,
                    "watch_note": verdict.watch_note,
                    "severity": verdict.severity,
                    "summary": verdict.summary,
                    "error": verdict.error,
                },
            }
        )

        if turn_no == persona.turns:
            break
        message = await judge.next_customer_message(
            persona_system_prompt=persona.system_prompt,
            conversation=conversation,
            tenant_id=tenant_id,
        )
        if not message:
            break

    return {
        "persona": persona.key,
        "label": persona.label,
        "watch": persona.watch,
        "lead_id": lead_id,
        "turns": turns,
    }


_FK_TABLE_RE = re.compile(r'constraint "([a-z_]+?)_lead_id_fkey" on table "([a-z_]+)"')


def _delete_lead(db, lead_id: str, *, max_rounds: int = 12) -> bool:
    """Delete one lead, clearing whatever still references it.

    Roughly 20 tables carry a lead_id foreign key and the set grows with every
    feature, so rather than hardcode the list, this deletes the known ones, then
    reads the referencing table straight out of Postgres's own FK error and
    clears that too. A run that escalates a lead creates chat_handovers rows,
    which is how this was found.
    """
    for table in _LEAD_TABLES:
        try:
            db.table(table).delete().eq("lead_id", lead_id).execute()
        except Exception as exc:
            logger.debug("cleanup: %s for lead %s: %s", table, lead_id, exc)

    for _ in range(max_rounds):
        try:
            db.table("leads").delete().eq("id", lead_id).execute()
            return True
        except Exception as exc:
            match = _FK_TABLE_RE.search(str(exc))
            if not match:
                logger.warning("cleanup: cannot delete lead %s: %s", lead_id, exc)
                return False
            blocking = match.group(2)
            try:
                db.table(blocking).delete().eq("lead_id", lead_id).execute()
            except Exception as inner:
                logger.warning("cleanup: clearing %s for lead %s: %s", blocking, lead_id, inner)
                return False
    logger.warning("cleanup: gave up on lead %s after %d rounds", lead_id, max_rounds)
    return False


def cleanup(db, run_id: str) -> dict:
    """Delete every row a run produced. Safe to re-run; never raises."""
    leads = (
        db.table("leads").select("id").ilike("notes", f"%sim_run_id={run_id}%").execute()
    ).data or []
    removed = {"leads": 0, "stuck": []}
    for row in leads:
        if _delete_lead(db, row["id"]):
            removed["leads"] += 1
        else:
            removed["stuck"].append(row["id"])
    return removed


def write_report(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = result["run_id"]
    (out_dir / f"{run_id}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    lines = [
        f"# Aira reply simulation — {run_id}",
        "",
        f"- tenant: `{result['tenant_id']}`",
        f"- started: {result['started_at']}",
        f"- personas: {len(result['personas'])}",
        "",
        "## Findings",
        "",
    ]
    total_findings = 0
    for persona_result in result["personas"]:
        rows = []
        for turn in persona_result["turns"]:
            for finding in turn["findings"]:
                rows.append(f"  - turn {turn['turn']} **{finding['severity']}** "
                            f"`{finding['code']}` — {finding['detail']}")
            verdict = turn["judge"]
            if verdict["severity"] in ("high", "critical") or not verdict["grounded"]:
                rows.append(f"  - turn {turn['turn']} **judge/{verdict['severity']}** — "
                            f"{verdict['summary']}")
                for claim in verdict["unsupported_claims"]:
                    rows.append(f"    - unsupported: {claim}")
        total_findings += len(rows)
        status = f"{len(rows)} finding(s)" if rows else "clean"
        lines.append(f"### {persona_result['label']} — {status}")
        lines.append(f"_watch: {persona_result['watch']}_")
        lines.append("")
        lines.extend(rows or ["  - nothing flagged"])
        lines.append("")

    lines += ["## Prompt size", "", "| persona | turn | prompt chars | history chars | latency ms |",
              "|---|---:|---:|---:|---:|"]
    for persona_result in result["personas"]:
        for turn in persona_result["turns"]:
            lines.append(
                f"| {persona_result['persona']} | {turn['turn']} | {turn['prompt_chars']:,} "
                f"| {turn['history_chars']:,} | {turn['latency_ms']:,} |"
            )

    lines += ["", "## Transcripts", ""]
    for persona_result in result["personas"]:
        lines.append(f"### {persona_result['label']}")
        lines.append("")
        for turn in persona_result["turns"]:
            lines.append(f"**Customer:** {turn['customer']}")
            lines.append("")
            lines.append(f"**Aira:** {turn['reply']}")
            lines.append("")
        lines.append("")

    lines.insert(6, f"**{total_findings} finding(s) across {len(result['personas'])} personas.**")
    path = out_dir / f"{run_id}.md"
    path.write_text("\n".join(lines))
    return path


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run persona conversations against the reply pipeline.")
    parser.add_argument("--tenant", help="tenant_id to simulate against")
    parser.add_argument("--personas", help="comma-separated persona keys (default: all)")
    parser.add_argument("--turns", type=int, help="override each persona's turn budget")
    parser.add_argument("--live-notifications", action="store_true",
                        help="let escalations really page staff (default: suppressed)")
    parser.add_argument("--keep-leads", action="store_true",
                        help="do not delete the simulated leads afterwards")
    parser.add_argument("--cleanup", metavar="RUN_ID", help="delete a previous run's rows and exit")
    parser.add_argument("--out", default="sim-out", help="report directory (default: sim-out)")
    parser.add_argument(
        "--master-from-file",
        metavar="PATH",
        help="run with a candidate master prompt read from this file, to compare it "
             "against the live one on one identical tenant. Reads only; nothing is "
             "written back to platform_defaults.",
    )
    parser.add_argument("--label", help="short name for this variant, shown in the report")
    args = parser.parse_args()

    from app.db.supabase import get_supabase

    db = get_supabase()

    if args.cleanup:
        removed = cleanup(db, args.cleanup)
        print(f"removed {removed['leads']} simulated lead(s) for run {args.cleanup}")
        if removed["stuck"]:
            print(f"COULD NOT DELETE: {removed['stuck']}")
        return 0

    if not args.tenant:
        parser.error("--tenant is required unless --cleanup is used")

    selected = personas.PERSONAS
    if args.personas:
        selected = tuple(personas.by_key(k.strip()) for k in args.personas.split(",") if k.strip())
    if args.turns:
        selected = tuple(
            personas.Persona(**{**p.__dict__, "turns": args.turns}) for p in selected
        )

    master_override = None
    if args.master_from_file:
        path = Path(args.master_from_file)
        if not path.is_file():
            parser.error(f"no such master prompt file: {path}")
        master_override = path.read_text(encoding="utf-8").strip()
        if not master_override:
            parser.error(f"master prompt file is empty: {path}")
        print(f"master prompt override: {len(master_override):,} chars from {path}")

    run_id = uuid.uuid4().hex[:12]
    result = {
        "run_id": run_id,
        "tenant_id": args.tenant,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live_notifications": args.live_notifications,
        "label": args.label or "live-master",
        "master_chars": len(master_override) if master_override else None,
        "master_from_file": args.master_from_file,
        "personas": [],
    }
    print(f"run {run_id} — {len(selected)} persona(s), tenant {args.tenant}")
    if args.live_notifications:
        print("WARNING: staff notifications are LIVE for this run.")

    try:
        for index, persona in enumerate(selected):
            try:
                result["personas"].append(
                    await run_persona(
                        db, args.tenant, persona, run_id, index,
                        live_notifications=args.live_notifications,
                        master_override=master_override,
                    )
                )
            except Exception as exc:
                logger.exception("persona %s failed", persona.key)
                result["personas"].append(
                    {"persona": persona.key, "label": persona.label, "watch": persona.watch,
                     "lead_id": None, "turns": [], "error": f"{type(exc).__name__}: {exc}"}
                )
    finally:
        path = write_report(result, Path(args.out))
        print(f"\nreport: {path}")
        if not args.keep_leads:
            removed = cleanup(db, run_id)
            print(f"cleaned up {removed['leads']} simulated lead(s)")
            if removed["stuck"]:
                print(f"COULD NOT DELETE: {removed['stuck']} — rerun --cleanup {run_id}")
        else:
            print(f"leads kept — remove later with: --cleanup {run_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
