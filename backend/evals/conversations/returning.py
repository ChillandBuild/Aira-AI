"""The returning-lead eval (release R3, ship bar D5): scenario templating and the pass/fail gate.

Scenarios in scenarios_returning.json are written once, with tokens, and expanded for each
live tenant's own offerings and required details (a tenant's config carries "roles"):

    {pkg.cheap} {pkg.dear}          offering keys       {name.cheap} {name.dear}   offering names
    {d.name} {d.dob} {d.tob} ...    required-detail keys of that tenant
    {price.cheap} {price.cheap.old} current price in paise / a stale price the deal was made at

A dict key or value that names a token the tenant does not have (e.g. {d.gender}) is dropped.

Run the gate on a results file:
    .venv/bin/python -m evals.conversations.returning results_returning_<tenant>.json ... [--configs scenarios_returning.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

from evals.conversations import checks  # noqa: E402

STALE_EXTRA_PAISE = 3000
MIN_RIGHT_ACTION_RATE = 0.90
_TOKEN = re.compile(r"\{([a-z]+)\.([a-z_]+)(?:\.([a-z]+))?\}")
_DROP = object()


def _package(config: dict, role: str) -> dict | None:
    key = (config.get("roles") or {}).get(role)
    return next((p for p in config.get("packages") or [] if p["key"] == key), None)


def _lookup(config: dict, kind: str, name: str, extra: str | None):
    if kind == "pkg":
        package = _package(config, name)
        return package["key"] if package else _DROP
    if kind == "name":
        package = _package(config, name)
        return package["name"] if package else _DROP
    if kind == "d":
        return (config.get("detail_keys") or {}).get(name, _DROP)
    if kind == "price":
        package = _package(config, name)
        if not package:
            return _DROP
        return package["amount_paise"] + (STALE_EXTRA_PAISE if extra == "old" else 0)
    return _DROP


def _resolve(value, config: dict):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key, val = _resolve(k, config), _resolve(v, config)
            if key is not _DROP and val is not _DROP:
                out[key] = val
        return out
    if isinstance(value, list):
        return [r for r in (_resolve(v, config) for v in value) if r is not _DROP]
    if not isinstance(value, str):
        return value
    whole = _TOKEN.fullmatch(value)
    if whole:
        return _lookup(config, *whole.groups())
    missing = []

    def sub(match):
        found = _lookup(config, *match.groups())
        missing.append(found is _DROP)
        return str(found)

    text = _TOKEN.sub(sub, value)
    return _DROP if any(missing) else text


def expand(scenario: dict, config: dict) -> dict:
    """The scenario with every token replaced by this tenant's own keys, names and prices."""
    return _resolve(scenario, config)


# ---------------------------------------------------------------- the gate

def scenario_metrics(row: dict, scenario: dict, config: dict) -> dict:
    """wrong_closes, bad_links (dead or old price) and whether every stated action was right."""
    transcript = row.get("transcript") or []
    check_config = {"expect": scenario.get("expect") or {}, **{k: config.get(k) for k in ("packages", "catalog")}}
    close = checks.returning_close(transcript, check_config)
    link = checks.returning_link(transcript, check_config)
    action_checks = [
        close, link, checks.returning_new_booking(transcript, check_config),
        checks.returning_confirm_details(transcript, check_config), checks.returning_package(transcript, check_config),
        _question_result(row),
    ]
    return {
        "wrong_closes": close.detail.count("WRONG_CLOSE"),
        "bad_links": sum(len(checks._link_problems(t)) for t in transcript),
        "right_action": not row.get("crash") and all(c.status != checks.FAIL for c in action_checks),
        "undecided": any(c.status == checks.SKIP for c in action_checks),
    }


def _question_result(row: dict) -> "checks.CheckResult":
    found = next((c for c in row.get("checks") or [] if c["name"] == "returning_question"), None)
    if not found:
        return checks.CheckResult("returning_question", checks.PASS)
    return checks.CheckResult("returning_question", found["status"], found["detail"])


def gate(rows: list[dict], scenarios: dict[str, dict], config: dict) -> dict:
    per = [(r, scenario_metrics(r, scenarios[r["id"].split("#")[0]], config)) for r in rows if r["id"].split("#")[0] in scenarios]
    total = len(per)
    right = sum(1 for _, m in per if m["right_action"])
    wrong = sum(m["wrong_closes"] for _, m in per)
    bad = sum(m["bad_links"] for _, m in per)
    rate = right / total if total else 0.0
    return {
        "scenarios": total, "right": right, "right_rate": rate, "wrong_closes": wrong, "bad_links": bad,
        "passed": total > 0 and wrong == 0 and bad == 0 and rate >= MIN_RIGHT_ACTION_RATE,
        "failures": [(r["id"], m) for r, m in per if not m["right_action"] or m["wrong_closes"] or m["bad_links"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", help="results_returning_<config>.json files from run_aira --out")
    parser.add_argument("--scenarios", default=str(HERE / "scenarios_returning.json"))
    args = parser.parse_args()
    data = json.loads(Path(args.scenarios).read_text())
    ok = True
    for path in args.results:
        rows = json.loads(Path(path).read_text())
        name = rows[0].get("config") if rows else None
        config = data["configs"][name]
        scenarios = {s["id"]: expand(s, config) for s in data["scenarios"]}
        result = gate(rows, scenarios, config)
        ok = ok and result["passed"]
        print(f"{name}: {result['scenarios']} scenarios, right actions {result['right_rate']:.0%}, "
              f"wrong closes {result['wrong_closes']}, dead/old-price links {result['bad_links']} -> "
              f"{'PASS' if result['passed'] else 'FAIL'}")
        for sid, m in result["failures"]:
            print(f"    {sid}: {m}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
