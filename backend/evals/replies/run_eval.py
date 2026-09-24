"""Reply-quality eval: build each reply with the PRODUCTION prompt builder and model call,
then grade it with fixed checks plus an LLM judge.

    cd backend && python -m evals.replies.run_eval --key-tenant <tenant_uuid> [--only real|synthetic]

The key tenant supplies the API keys, the reply model and (for real cases) its own
description and knowledge retrieval. Synthetic businesses override the description,
app link and language mode, and supply their facts as knowledge excerpts.

Nothing is written to the database: lead history reads go to a stub that returns nothing.

Sets:
  golden_synthetic.json  5 made-up businesses in different domains (committed)
  golden_real.json       real inbound messages from the key tenant (gitignored)
"""
import argparse
import asyncio
import collections
import contextvars
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

import app.config_dynamic as config_dynamic  # noqa: E402
import app.services.ai_reply as ai_reply  # noqa: E402
from app.services.gemini_client import gemini_chat_completion_json  # noqa: E402
from app.services.knowledge_service import get_knowledge_context  # noqa: E402

JUDGE_MODEL = "gemini-3.5-flash"
CONCURRENCY = 4
MAX_REPLY_CHARS = 700
_PLACEHOLDER_RE = re.compile(r"\[(?:insert|link|url|your)[^\]]*\]", re.IGNORECASE)
_UNSET = object()

# ── Settings override, per asyncio task ──────────────────────────────────────
_overrides: contextvars.ContextVar[dict] = contextvars.ContextVar("overrides", default={})
_real_get_setting = config_dynamic.get_setting


def _get_setting(key, fallback=None, tenant_id=None):
    value = _overrides.get().get(key, _UNSET)
    if value is _UNSET:
        return _real_get_setting(key, fallback=fallback, tenant_id=tenant_id)
    return value if value is not None else fallback


config_dynamic.get_setting = _get_setting
ai_reply.get_setting = _get_setting


class _StubQuery:
    """Stands in for the DB during prompt building: every read comes back empty."""

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=[])


class _StubDB:
    def table(self, _name):
        return _StubQuery()


# ── Cases ─────────────────────────────────────────────────────────────────────
def load_cases(only: str | None) -> tuple[list[dict], dict]:
    synth = json.loads((HERE / "golden_synthetic.json").read_text())
    cases: list[dict] = []
    if only in (None, "synthetic"):
        cases += synth["cases"]
    real = HERE / "golden_real.json"
    if only in (None, "real") and real.exists():
        cases += json.loads(real.read_text())
    return cases, synth["businesses"]


async def build_context(case: dict, biz: dict | None, key_tenant: str) -> tuple[str, dict]:
    if biz is None:  # real tenant: its own settings and live retrieval
        return await get_knowledge_context(key_tenant, query=case["message"]), {}
    excerpts = "\n\n".join(f"=== excerpt {i + 1} ===\n{f}" for i, f in enumerate(biz["facts"]))
    overrides = {
        "business_description": biz["description"],
        "app_download_link": biz.get("app_link"),
        "reply_language_mode": biz["language_mode"],
    }
    return excerpts, overrides


async def generate(case: dict, biz: dict | None, key_tenant: str) -> tuple[str, str, str, str]:
    context_text, overrides = await build_context(case, biz, key_tenant)
    _overrides.set(overrides)
    lead = {"name": "", "segment": "C", "tenant_id": key_tenant, "needs_human_attention": False}
    system_prompt, _mode, _intake = ai_reply.build_reply_system_prompt(
        _StubDB(), "eval-lead", key_tenant, lead, case["message"], "whatsapp",
        context_text=context_text, include_intake_context=False,
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": r, "content": c} for r, c in case.get("thread", [])]
    messages.append({"role": "user", "content": case["message"]})
    reply = (await ai_reply._llm_chat(messages, max_tokens=600, tenant_id=key_tenant)).strip()
    return reply, context_text, _overrides.get().get("business_description") or _real_get_setting(
        "business_description", tenant_id=key_tenant) or "", _mode


# ── Grading ───────────────────────────────────────────────────────────────────
def fixed_checks(case: dict, biz: dict | None, reply: str) -> list[str]:
    fails = []
    wanted = case.get("must_include_any")
    if wanted and not any(w.lower() in reply.lower() for w in wanted):
        fails.append("missing_key_fact")
    script = case.get("expect_script")
    got = ai_reply._dominant_script(reply)
    if script == "tamil" and got != "ta":
        fails.append("wrong_language")
    if script == "latin" and got != "en":
        fails.append("wrong_language")
    team_ok = biz["team_promise_allowed"] if biz else case.get("team_promise_allowed", False)
    if not team_ok and ai_reply._AI_ESCALATION_RE.search(reply):
        fails.append("promised_team_contact")
    if _PLACEHOLDER_RE.search(reply):
        fails.append("placeholder_link")
    if len(reply) > MAX_REPLY_CHARS:
        fails.append("too_long")
    return fails


_JUDGE_SYSTEM = """You are a strict grader of one WhatsApp reply written by a business's AI assistant.
First list every factual claim the reply makes, then decide. Return JSON only:
{"claims": ["..."], "answered": true|false, "invented": true|false, "broke_rule": true|false,
 "claimed_action": true|false, "wrong_language": true|false, "pushy": true|false,
 "natural": 1-5, "why": "<one short sentence naming the problem, or 'ok'>"}

answered       = the reply actually responds to what the customer asked (a greeting, stop
                 request or off-topic question counts if handled sensibly).
invented       = ANY claim not supported by the BUSINESS PROFILE or FACTS. This includes
                 negative claims: "we don't have X" or "we don't offer X" is invented unless the
                 profile/facts say so. When information is missing, the only correct move is to
                 say it isn't known / will be checked, never to answer yes or no.
broke_rule     = breaks a rule in the BUSINESS PROFILE, or a universal rule: never guarantee
                 outcomes; no medical/legal/financial advice; a stop request gets one short
                 acknowledgement and nothing else.
claimed_action = says something was done that an assistant cannot have done ("I have booked",
                 "I have updated our records", "I have informed the team", "you will not
                 receive messages") unless the conversation shows it happened.
wrong_language = the reply's language or style does not match the LANGUAGE EXPECTED line.
pushy          = selling the customer did not invite, or repeating a call to action.
natural        = 5 reads like a helpful human on WhatsApp, 1 robotic or awkward.
Use the GRADER NOTE for what a good reply does in this case. When unsure, mark the problem."""


_LANGUAGE_EXPECTED = {
    "mirror": "the same language and style as the customer's latest message "
              "(Hindi/Hinglish gets Hindi/Hinglish, Tanglish gets Tanglish, Tamil script gets Tamil script, English gets English)",
    "english": "English only, whatever the customer writes",
    "tanglish": "Tanglish (Tamil in English letters), whatever the customer writes",
    "tamil": "Tamil script, whatever the customer writes",
}


async def judge(case: dict, reply: str, profile: str, facts: str, mode: str,
                key_tenant: str) -> dict:
    thread = "\n".join(f"{r}: {c}" for r, c in case.get("thread", []))
    language = _LANGUAGE_EXPECTED.get(mode, _LANGUAGE_EXPECTED["mirror"])
    user = (
        f"BUSINESS PROFILE:\n{profile[:8000]}\n\nFACTS:\n{facts[:8000]}\n\n"
        f"LANGUAGE EXPECTED: {language}\n\n"
        f"EARLIER CHAT:\n{thread or '(none)'}\n\nCUSTOMER: {case['message']}\n\n"
        f"REPLY TO GRADE:\n{reply}\n\nGRADER NOTE: {case.get('note', '')}"
    )
    try:
        return await gemini_chat_completion_json(
            _JUDGE_SYSTEM, user, model=JUDGE_MODEL, temperature=0.0, max_tokens=900,
            tenant_id=key_tenant, purpose="eval_judge",
        )
    except Exception as e:  # a judge failure must not look like a pass
        return {"answered": False, "invented": False, "broke_rule": False, "pushy": False,
                "natural": 0, "why": f"judge_error: {e}"}


def judge_fails(verdict: dict) -> list[str]:
    fails = []
    if not verdict.get("answered"):
        fails.append("did_not_answer")
    if verdict.get("invented"):
        fails.append("invented_fact")
    if verdict.get("broke_rule"):
        fails.append("broke_rule")
    if verdict.get("pushy"):
        fails.append("pushy")
    if verdict.get("claimed_action"):
        fails.append("claimed_action")
    if verdict.get("wrong_language"):
        fails.append("wrong_language")
    return fails


async def run_case(case, businesses, key_tenant, sem) -> dict:
    biz = businesses.get(case.get("business")) if case.get("business") != "real" else None
    async with sem:
        try:
            reply, facts, profile, mode = await generate(case, biz, key_tenant)
        except Exception as e:
            return {**case, "reply": "", "fails": [f"generation_error: {e}"], "verdict": {}}
        verdict = await judge(case, reply, profile, facts, mode, key_tenant)
    fails = fixed_checks(case, biz, reply) + judge_fails(verdict)
    return {**case, "reply": reply, "fails": fails, "verdict": verdict}


def report(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(not r["fails"] for r in results)
    print(f"\nPASS: {passed}/{total} = {passed / total:.0%}")
    natural = [r["verdict"].get("natural", 0) for r in results if r["verdict"]]
    if natural:
        print(f"Natural (1-5, judge): {sum(natural) / len(natural):.1f}")
    by_biz = collections.defaultdict(lambda: [0, 0])
    for r in results:
        by_biz[r.get("business", "real")][0] += not r["fails"]
        by_biz[r.get("business", "real")][1] += 1
    for biz, (ok, n) in sorted(by_biz.items()):
        print(f"  {biz:11s} {ok}/{n}")
    counts = collections.Counter(f for r in results for f in r["fails"])
    print("\nFailure types:")
    for f, n in counts.most_common():
        print(f"  {f:24s} {n}")
    print("\nFailures:")
    for r in results:
        if r["fails"]:
            print(f"  {r['id']}: {', '.join(r['fails'])}")
            print(f"      lead:  {r['message'][:90]}")
            print(f"      reply: {r['reply'][:220]!r}")
            print(f"      judge: {r['verdict'].get('why', '')[:150]}")
    return {"pass_rate": passed / total, "failures": dict(counts)}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-tenant", required=True)
    parser.add_argument("--only", choices=["real", "synthetic"], default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    cases, businesses = load_cases(args.only)
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(run_case(c, businesses, args.key_tenant, sem) for c in cases))
    summary = report(results)
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "results": results},
                                             ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
