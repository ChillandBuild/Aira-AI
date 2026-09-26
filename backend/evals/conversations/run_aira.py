"""Run Aira (the production reply engine) through scripted conversations and grade them.

    cd backend && .venv/bin/python -m evals.conversations.run_aira --key-tenant <tenant_uuid> \
        [--files scenarios.json,scenarios_edge.json] [--only id1,id2] [--repeat 1] [--no-judge] [--out results.json]

Every lead message goes through the same steps as generate_reply (see engine_sim.run_turn), with
real LLM calls on the key tenant's keys and a simulated world for sessions, orders and links.
Each conversation is graded twice: the fixed checks (checks.py, must hold 100%) and the LLM
judge (judge.py: sounds human, answered first, memory, honesty, handled the situation).
Nothing is written to the database and no WhatsApp message is sent.

Legacy baseline (the old route_intake flow): evals/conversations/run_eval.py --engine legacy.
"""
import argparse
import asyncio
import json
import sys
from contextlib import ExitStack
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

from evals.conversations import engine_sim, judge  # noqa: E402
from evals.conversations.checks import ALWAYS_CHECKS, FAIL, PASS, SKIP, run_check  # noqa: E402

CONCURRENCY = 3
NETWORK_RETRIES = 1  # a provider timeout is not a finding; a second one is reported
DEFAULT_FILES = "scenarios.json,scenarios_edge.json,scenarios_life.json"


def load(files: str) -> tuple[list[dict], dict]:
    """Scenarios from the given files; configs from every scenario file, so an edge file can
    reuse the base businesses."""
    scenarios: list[dict] = []
    configs: dict = {}
    wanted = {name.strip() for name in files.split(",")}
    for path in sorted(HERE.glob("scenarios*.json")):
        data = json.loads(path.read_text())
        configs.update(data.get("configs") or {})
        if path.name in wanted:
            scenarios.extend(data.get("scenarios") or [])
    return scenarios, configs


def _check_config(config: dict) -> dict:
    """What checks.py needs: packages, catalog prices, and hosts the business may link to."""
    return {
        "packages": config.get("packages") or [],
        "catalog": config.get("catalog") or [],
        "allowed_hosts": config.get("allowed_hosts") or [],
    }


async def _one(scenario: dict, config: dict, tenant: str, use_judge: bool, gate: asyncio.Semaphore) -> dict:
    async with gate:
        transcript = None
        for attempt in range(NETWORK_RETRIES + 1):
            try:
                transcript = await engine_sim.run_scenario(scenario, config, tenant)
                break
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == NETWORK_RETRIES:
                    return {"id": scenario["id"], "crash": repr(e), "transcript": [], "checks": [], "judge": None}
            except Exception as e:  # a crash is a finding, not a reason to stop the run
                return {"id": scenario["id"], "crash": repr(e), "transcript": [], "checks": [], "judge": None}
        names = list(dict.fromkeys([*scenario.get("expect", {}).get("hard", []), *ALWAYS_CHECKS]))
        hard = [run_check(n, transcript, _check_config(config)) for n in names]
        verdict = await judge.judge_conversation(scenario, transcript, config, tenant) if use_judge else None
        return {
            "id": scenario["id"], "transcript": transcript, "judge": verdict,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in hard],
        }


def report(rows: list[dict]) -> None:
    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    judged = {"pass": 0, "weak": 0, "fail": 0}
    seconds = [t["seconds"] for r in rows for t in r["transcript"]]
    for row in sorted(rows, key=lambda r: r["id"]):
        if row.get("crash"):
            print(f"- {row['id']}: CRASH {row['crash']}")
            continue
        for c in row["checks"]:
            counts[c["status"]] += 1
        fails = [c for c in row["checks"] if c["status"] == FAIL]
        v = row.get("judge")
        tag = f"judge={v['status'].upper()}({v['min_score']})" if v else "judge=off"
        if v:
            judged[v["status"]] += 1
        print(f"- {row['id']}: {tag} fixed={'FAIL' if fails else 'ok'}")
        for c in fails:
            print(f"    FIXED {c['name']}: {c['detail']}")
        if v and v["status"] != "pass":
            for issue in v["issues"][:3]:
                print(f"    JUDGE {issue}")
    decided = counts[PASS] + counts[FAIL]
    rate = f"{100 * counts[PASS] / decided:.0f}%" if decided else "n/a"
    print(f"\nFixed checks: {counts[PASS]} pass, {counts[FAIL]} fail, {counts[SKIP]} skipped ({rate})")
    print(f"Judge: {judged['pass']} pass, {judged['weak']} weak, {judged['fail']} fail of {sum(judged.values())}")
    if seconds:
        print(f"Time per turn: avg {sum(seconds) / len(seconds):.1f}s, max {max(seconds)}s over {len(seconds)} turns")
    crashes = [r["id"] for r in rows if r.get("crash")]
    if crashes:
        print(f"Crashes: {crashes}")


async def main_async(args) -> None:
    if args.reply_model:
        engine_sim.EXTRA_SETTINGS["ai_reply_model"] = args.reply_model
    scenarios, configs = load(args.files)
    wanted = set(args.only.split(",")) if args.only else None
    picked = [s for s in scenarios if not wanted or s["id"] in wanted]
    gate = asyncio.Semaphore(CONCURRENCY)
    with ExitStack() as stack:
        engine_sim.install(stack)
        engine_sim.install_settings(stack)
        jobs = []
        for run in range(args.repeat):
            for s in picked:
                scenario = s if args.repeat == 1 else {**s, "id": f"{s['id']}#{run + 1}"}
                jobs.append(_one(scenario, configs[s["config"]], args.key_tenant, not args.no_judge, gate))
        rows = await asyncio.gather(*jobs)
    report(rows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"Written to {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-tenant", required=True)
    parser.add_argument("--files", default=DEFAULT_FILES)
    parser.add_argument("--only")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--reply-model", help="try another reply model, e.g. google/gemini-3.5-flash")
    parser.add_argument("--out")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
