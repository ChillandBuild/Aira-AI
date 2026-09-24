"""Lead-classification eval: run the live classifier against hand-labelled chats.

Calls the real LLM (costs a little), reads nothing from and writes nothing to the DB
except the tenant's settings for the API key and, for real chats, its rubric.

    cd backend && python -m evals.scoring.run_eval --key-tenant <tenant_uuid> [--runs 3]

Sets:
  golden_real.json       real chats, labelled by hand (gitignored: customer data)
  golden_synthetic.json  made-up chats for other business types, with their rubrics
"""
import argparse
import asyncio
import collections
import contextvars
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

import app.config_dynamic as config_dynamic  # noqa: E402
from app.services import scoring_engine as se  # noqa: E402

SEG_TO_LABEL = {"A": "hot", "B": "warm", "C": "cold", "D": "cold"}
CONCURRENCY = 5


def load_cases() -> list[dict]:
    cases = []
    real = HERE / "golden_real.json"
    if real.exists():
        for c in json.loads(real.read_text()):
            cases.append({**c, "rubric": None})  # None -> tenant's own rubric
    synth = json.loads((HERE / "golden_synthetic.json").read_text())
    for c in synth["cases"]:
        cases.append({**c, "rubric": synth["businesses"][c["business"]]["rubric"]})
    return cases


def to_conversation(lines: list[str]) -> str:
    """Mirror compute_score(): fetch the last N messages, then drop template placeholders."""
    window = lines[-se._CONVERSATION_WINDOW:]
    kept = [l for l in window if not l.startswith("Bot: [Template")]
    return "\n".join(
        f"User: {se._AD_PREFILL_MARKER}" if l.startswith("User: [ad-prefill]") else l for l in kept
    )


# Each asyncio task gets its own copy of this, so parallel cases never share a rubric.
_case_rubric: contextvars.ContextVar[str | None] = contextvars.ContextVar("case_rubric", default=None)
_real_get_setting = config_dynamic.get_setting


def _get_setting_for_case(key, *args, **kwargs):
    rubric = _case_rubric.get()
    if key == "scoring_rubric" and rubric is not None:
        return rubric
    return _real_get_setting(key, *args, **kwargs)


config_dynamic.get_setting = _get_setting_for_case


async def classify(case: dict, key_tenant: str, runs: int, sem: asyncio.Semaphore) -> dict:
    conv = to_conversation(case["conversation"])
    answers, reasons = [], []
    _case_rubric.set(case["rubric"])
    async with sem:
        for _ in range(runs):
            seg, reason = await se._classify_segment(conv, key_tenant, fallback="C")
            answers.append(SEG_TO_LABEL[seg])
            reasons.append(reason)
    majority = collections.Counter(answers).most_common(1)[0][0]
    return {**case, "predicted": majority, "answers": answers, "model_reason": reasons[0]}


def report(results: list[dict]) -> dict:
    total = len(results)
    correct = sum(r["predicted"] == r["label"] for r in results)
    pred_hot = [r for r in results if r["predicted"] == "hot"]
    true_hot = [r for r in results if r["label"] == "hot"]
    hot_precision = sum(r["label"] == "hot" for r in pred_hot) / len(pred_hot) if pred_hot else 0.0
    hot_recall = sum(r["predicted"] == "hot" for r in true_hot) / len(true_hot) if true_hot else 0.0
    unstable = [r for r in results if len(set(r["answers"])) > 1]

    print(f"\nAccuracy: {correct}/{total} = {correct / total:.0%}")
    print(f"Hot precision (of leads called Hot, really Hot): {hot_precision:.0%}")
    print(f"Hot recall (of really Hot leads, caught): {hot_recall:.0%}")
    print(f"Unstable (different answers across runs): {len(unstable)}")

    by_biz = collections.defaultdict(lambda: [0, 0])
    for r in results:
        by_biz[r["business"]][0] += r["predicted"] == r["label"]
        by_biz[r["business"]][1] += 1
    for biz, (ok, n) in sorted(by_biz.items()):
        print(f"  {biz:11s} {ok}/{n}")

    print("\nConfusion (label -> predicted):")
    matrix = collections.Counter((r["label"], r["predicted"]) for r in results)
    for (lab, pred), n in sorted(matrix.items()):
        print(f"  {lab:5s} -> {pred:5s} {n}")

    print("\nMistakes:")
    for r in results:
        if r["predicted"] != r["label"]:
            flag = " (borderline)" if r.get("borderline") else ""
            print(f"  {r['id']}: want {r['label']}, got {r['predicted']} {r['answers']}{flag}")
            print(f"      model: {r['model_reason'][:110]}")
    return {"accuracy": correct / total, "hot_precision": hot_precision,
            "hot_recall": hot_recall, "unstable": len(unstable)}


async def regenerate_rubrics(cases: list[dict], key_tenant: str) -> list[dict]:
    """Swap each business's rubric for one made by the current generator."""
    from app.routes import ai_tune
    from app.services.gemini_client import gemini_chat_completion

    synth = json.loads((HERE / "golden_synthetic.json").read_text())
    descriptions = {b: v["description"] for b, v in synth["businesses"].items()}
    real_desc = _real_get_setting("business_description", tenant_id=key_tenant) or ""
    rubrics = {}
    for biz in {c["business"] for c in cases}:
        desc = descriptions.get(biz, real_desc)
        rubrics[biz] = (await gemini_chat_completion(
            messages=[{"role": "user", "content": ai_tune._rubric_prompt(desc)}],
            model=ai_tune._TUNE_MODEL, temperature=0.2, max_tokens=400,
            tenant_id=key_tenant, purpose="ai_tune_rubric",
        )).strip()
        print(f"--- generated rubric: {biz}\n{rubrics[biz]}\n")
    return [{**c, "rubric": rubrics[c["business"]]} for c in cases]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-tenant", required=True, help="tenant whose Gemini key and rubric to use")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default=None, help="write per-case results JSON here")
    parser.add_argument("--regen-rubrics", action="store_true",
                        help="generate every rubric from its business description with the "
                             "current generator instead of using the stored ones")
    args = parser.parse_args()

    sem = asyncio.Semaphore(CONCURRENCY)
    cases = load_cases()
    if args.regen_rubrics:
        cases = await regenerate_rubrics(cases, args.key_tenant)
    results = await asyncio.gather(*(classify(c, args.key_tenant, args.runs, sem) for c in cases))
    summary = report(results)
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "results": results},
                                             ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
