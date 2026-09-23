"""Tabulate several simulation runs side by side.

    python -m scripts.sim.compare sim-out/<run>.json sim-out/<run>.json ...

Built for the platform-prompt bake-off: same tenant, same description, same
knowledge base, one variable (the master prompt). Reports rule findings by code,
judge verdicts, prompt size and latency per variant, so "shorter is better" is a
measurement rather than an opinion.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
JUDGE_FAIL = ("high", "critical")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def summarize(run: dict) -> dict:
    codes: Counter[str] = Counter()
    sev: Counter[str] = Counter()
    judge_sev: Counter[str] = Counter()
    turns = 0
    prompt_chars: list[int] = []
    reply_chars: list[int] = []
    latency: list[int] = []
    ungrounded = 0
    unsupported = 0

    for persona in run["personas"]:
        for turn in persona.get("turns", []):
            turns += 1
            prompt_chars.append(turn["prompt_chars"])
            reply_chars.append(len(turn["reply"] or ""))
            latency.append(turn["latency_ms"])
            for finding in turn["findings"]:
                codes[finding["code"]] += 1
                sev[finding["severity"]] += 1
            verdict = turn["judge"]
            judge_sev[verdict.get("severity") or "none"] += 1
            if verdict.get("grounded") is False:
                ungrounded += 1
            unsupported += len(verdict.get("unsupported_claims") or [])

    def avg(xs: list[int]) -> int:
        return round(sum(xs) / len(xs)) if xs else 0

    return {
        "label": run.get("label") or run["run_id"],
        "master_chars": run.get("master_chars"),
        "turns": turns,
        "codes": codes,
        "sev": sev,
        "judge_sev": judge_sev,
        "ungrounded": ungrounded,
        "unsupported": unsupported,
        "hard_total": sum(sev.values()),
        "judge_fails": sum(judge_sev[s] for s in JUDGE_FAIL),
        "avg_prompt": avg(prompt_chars),
        "avg_reply": avg(reply_chars),
        "avg_latency": avg(latency),
    }


def row(label: str, values: list[str], width: int = 18) -> str:
    return f"{label:<26}" + "".join(f"{v:>{width}}" for v in values)


def main(paths: list[str]) -> int:
    runs = [summarize(load(p)) for p in paths]
    labels = [r["label"] for r in runs]

    print()
    print(row("", labels))
    print("-" * (26 + 18 * len(runs)))
    print(row("master prompt chars", [f"{r['master_chars'] or 0:,}" for r in runs]))
    print(row("turns run", [str(r["turns"]) for r in runs]))
    print()
    print(row("HARD FINDINGS (total)", [str(r["hard_total"]) for r in runs]))
    for s in SEVERITY_ORDER:
        if any(r["sev"].get(s) for r in runs):
            print(row(f"  {s.lower()}", [str(r["sev"].get(s, 0)) for r in runs]))

    all_codes = sorted({c for r in runs for c in r["codes"]})
    if all_codes:
        print()
        print(row("BY RULE", [""] * len(runs)))
        for code in all_codes:
            print(row(f"  {code}", [str(r["codes"].get(code, 0)) for r in runs]))

    print()
    print(row("JUDGE failures (high+crit)", [str(r["judge_fails"]) for r in runs]))
    print(row("  ungrounded replies", [str(r["ungrounded"]) for r in runs]))
    print(row("  unsupported claims", [str(r["unsupported"]) for r in runs]))

    print()
    print(row("avg prompt chars", [f"{r['avg_prompt']:,}" for r in runs]))
    print(row("avg reply chars", [f"{r['avg_reply']:,}" for r in runs]))
    print(row("avg latency ms", [f"{r['avg_latency']:,}" for r in runs]))
    print()

    best = min(runs, key=lambda r: (r["hard_total"] + r["judge_fails"], r["avg_prompt"]))
    print(f"fewest problems: {best['label']} "
          f"({best['hard_total']} rule findings + {best['judge_fails']} judge failures)")
    print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1:]))
