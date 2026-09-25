"""Step 2 — mark a real conversation out of 100 on 10 fixed checks.

The AI chooses only a level (+ reason + quote) per check. The system validates
every quote, applies the talk-share/interruption caps, forces product info to
Missing on a proven wrong statement, and computes every mark and the total.
Check 10 (CRM update) is left pending here and marked from the wrap-up.
"""
from dataclasses import dataclass, field

from app.services.call_lines import Line, clock, format_transcript
from app.services.call_metrics import courtesy_cap, listening_cap, lower_level, tips
from app.services.call_quotes import clip, find_quote
from app.services.gemini_client import gemini_analysis_json
from app.services.scoring_rules import CHECK_MARKS, LEVEL_ORDER, LEVEL_SHARE

CHECKS: list[dict] = [
    {"key": "opening", "label": "Opening", "stage": "connect"},
    {"key": "courtesy", "label": "Courtesy & empathy", "stage": "connect"},
    {"key": "questions", "label": "Asking questions", "stage": "understand"},
    {"key": "listening", "label": "Listening", "stage": "understand"},
    {"key": "product_info", "label": "Correct product information", "stage": "explain"},
    {"key": "doubts", "label": "Clearing doubts", "stage": "explain"},
    {"key": "clarity", "label": "Clarity", "stage": "explain"},
    {"key": "next_step", "label": "Next step", "stage": "close"},
    {"key": "decision", "label": "Asking for the decision", "stage": "close"},
    {"key": "crm_update", "label": "CRM update", "stage": "close"},
]
for _c in CHECKS:
    _c["full"] = CHECK_MARKS[_c["key"]]
AI_CHECKS = [c["key"] for c in CHECKS if c["key"] != "crm_update"]


class CallMarkingError(Exception):
    """The AI reply didn't give a valid level for every check."""


@dataclass
class MarkResult:
    checks: list[dict]
    rude_quote: str | None = None
    wrong_info: list[dict] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)
    proof_missing: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)


def check_marks(key: str, level: str | None) -> float:
    return CHECK_MARKS[key] * LEVEL_SHARE[level] if level else 0.0


def total_score(checks: list[dict]) -> float:
    return round(sum(check_marks(c["key"], c.get("level")) for c in checks), 1)


def top_improve(checks: list[dict]) -> list[str]:
    marked = [c for c in checks if c.get("level")]
    marked.sort(key=lambda c: (check_marks(c["key"], c["level"]) / CHECK_MARKS[c["key"]], -CHECK_MARKS[c["key"]]))
    return [c["key"] for c in marked[:2]]


def apply_level(check: dict, ai_level: str, cap: str, cap_name: str | None) -> dict:
    level = lower_level(ai_level, cap)
    out = dict(check)
    out.update({
        "ai_level": ai_level,
        "level": level,
        "capped_by": cap_name if level != ai_level else None,
        "marks": round(check_marks(check["key"], level), 2),
    })
    return out


_SYSTEM = (
    "You are a strict, consistent quality reviewer for a telecalling team. You mark ONE real sales "
    "conversation using a fixed rubric. The transcript lines carry exact times and certain speaker "
    "labels. Judge only what the telecaller did, never whether the customer bought. Use only the "
    "transcript, the knowledge base, the previous notes and the two numbers given. No guessing. "
    "Write reasons in English; copy quotes exactly as they appear in the transcript."
)

_RUBRIC = """Mark checks 1-9. For each give level ("excellent"|"good"|"partial"|"poor"|"missing"), a one-line reason, and a short exact quote from the transcript that supports it (for "missing", quote the line showing the gap, or null and say in the reason what was not said).
1 opening: greeting, telecaller's name, company name, reminder of the enquiry/reason for the call, asking if it's a good time. excellent = all within ~30s; good = one missing; partial = two+ missing or rushed/unclear reason; poor = straight into selling without introducing; missing = no introduction or rude start.
2 courtesy: polite words, acknowledging feelings, patience, no pressure (no "decide now", no false urgency, no pushing after a no), respectful ending. excellent = all; good = misses one; partial = dry/scripted or slightly pushy once; poor = impatient or pushy several times (also: still pushing after the customer's 2nd "not interested" is poor at most); missing = rude, sarcastic, dismissive or abusive.
3 questions: open questions on need, budget, timing, decision-maker. excellent = need + at least 2 of the others; good = need + 1; partial = only 1-2 basic or yes/no questions; poor = assumed the need; missing = none. On a follow-up call where the need is already known (see previous notes), confirming the need counts as asking.
4 listening: repeating back/summarising, using the customer's answers, balanced talk. excellent = summarised/confirmed, built on answers; good = one missed chance to confirm; partial = some points ignored or talked too much; poor = mostly ignored answers or interrupted often; missing = talked over the customer or ignored everything.
5 product_info: compare with the knowledge base. excellent = all correct and linked to the customer's need; good = correct but general; partial = mostly correct but vague/missing details; poor = several gaps or couldn't answer basics; missing = gave wrong information. Something the knowledge base doesn't cover is NOT wrong: list it under unverified_claims. Only statements that clearly contradict the knowledge base are wrong: list each under wrong_info with the telecaller's exact quote and the knowledge-base fact.
6 doubts: excellent = answered every question/concern clearly and checked the customer was satisfied, or (if none were raised) explained common doubts upfront; good = answered but didn't check; partial = vague answers; poor = avoided or brushed off, or confusing; missing = ignored or argued.
7 clarity: excellent = simple, organised, customer never asked "what?"; good = a little repetition; partial = some confusing parts or overly long; poor = frequently confusing; missing = customer clearly couldn't follow.
8 next_step: excellent = specific next step agreed by the customer with date and time; good = agreed, no exact time; partial = vague ("I'll call you sometime"); poor = mentioned but not agreed; missing = none. A correctly disqualified customer ended politely counts as excellent.
9 decision: excellent = asked clearly at a suitable moment without pressure; good = asked weakly/indirectly; partial = only hinted; poor = asked too early or pushed; missing = never asked. For a correctly disqualified customer, politely keeping the door open counts as excellent.
Also: rude (true only if the telecaller was rude/abusive; rude_quote = their exact line); excused_interruptions = how many of the interruptions were the telecaller politely bringing a long off-topic customer back ("Sorry to cut in, sir…"), with the reason in the courtesy reason.

Return JSON only:
{"checks": {"opening": {"level": "...", "reason": "...", "quote": "..."}, ... all 9 keys ...}, "rude": false, "rude_quote": null, "excused_interruptions": 0, "wrong_info": [{"quote": "...", "kb_fact": "..."}], "unverified_claims": ["..."]}"""


def _numbers_block(share, ipm, count) -> str:
    share_txt = f"{share:.0f}% of the words were the telecaller's" if share is not None else "not measured (too few words)"
    int_txt = f"{count} times ({ipm:.2f} per 5 minutes)" if ipm is not None else "not measured"
    return (
        f"Talk share: {share_txt}. Interruptions (telecaller cut in while the customer was speaking): {int_txt}.\n"
        "These numbers guide listening and courtesy, but you must still read what was said.\n"
    )


def _quote_ok(level: str, quote, lines: list[Line]) -> tuple[bool, Line | None]:
    line = find_quote(quote, lines)
    if line:
        return True, line
    return level == "missing" and not quote, None


async def mark_call(
    lines: list[Line], *, kb_context: str | None, previous_notes: str | None, talk_share: float | None,
    interruptions_per_5min: float | None, interruption_count: int | None, duration_seconds: int | None,
    tenant_id: str | None,
) -> MarkResult:
    kb = kb_context or "none available (treat product claims you can't check as unverified, not wrong)"
    prompt = (
        f"Transcript:\n{format_transcript(lines)}\n\n"
        f"Knowledge base:\n{kb}\n\n"
        f"Previous notes on this lead:\n{previous_notes or 'none'}\n\n"
        f"{_numbers_block(talk_share, interruptions_per_5min, interruption_count)}\n{_RUBRIC}"
    )
    data = await gemini_analysis_json(
        system_prompt=_SYSTEM, user_prompt=prompt, tenant_id=tenant_id, temperature=0.0, purpose="call_marking",
    )
    raw = data.get("checks") if isinstance(data.get("checks"), dict) else {}

    excused = data.get("excused_interruptions")
    excused = excused if isinstance(excused, int) and not isinstance(excused, bool) and excused > 0 else 0
    ipm_for_caps = interruptions_per_5min
    if ipm_for_caps is not None and interruption_count and excused:
        remaining = max(0, interruption_count - excused)
        ipm_for_caps = round(ipm_for_caps * remaining / interruption_count, 2)

    rude_line = find_quote(data.get("rude_quote"), lines, ("telecaller",)) if data.get("rude") is True else None
    wrong = []
    for item in data.get("wrong_info") or []:
        if isinstance(item, dict):
            line = find_quote(item.get("quote"), lines, ("telecaller",))
            if line:
                wrong.append({"quote": clip(item["quote"]), "time": clock(line.start), "kb_fact": clip(item.get("kb_fact"))})

    lcap = listening_cap(talk_share, ipm_for_caps)
    lcap_name = None
    if lcap != "excellent":
        hi_share = talk_share is not None and talk_share > 65
        hi_int = ipm_for_caps is not None and ipm_for_caps > 1
        lcap_name = "talk_share_and_interruptions" if hi_share and hi_int else ("talk_share" if hi_share else "interruptions")

    checks, proof_missing = [], []
    for base in CHECKS:
        key = base["key"]
        slim = {"key": key, "full": base["full"]}
        if key == "crm_update":
            checks.append({**slim, "level": None, "ai_level": None, "capped_by": None, "marks": None,
                           "reason": None, "quote": None, "time": None, "proof_missing": False})
            continue
        item = raw.get(key)
        level = item.get("level") if isinstance(item, dict) else None
        if level not in LEVEL_ORDER:
            raise CallMarkingError(f"no valid level for check {key}")
        cap, cap_name = "excellent", None
        if key == "listening":
            cap, cap_name = lcap, lcap_name
        elif key == "courtesy":
            if rude_line:
                cap, cap_name = "missing", "rude"
            else:
                cap = courtesy_cap(ipm_for_caps)
                cap_name = "interruptions" if cap != "excellent" else None
        elif key == "product_info" and wrong:
            cap, cap_name = "missing", "wrong_info"
        check = apply_level(slim, level, cap, cap_name)
        ok, line = _quote_ok(level, item.get("quote"), lines)
        check.update({
            "reason": clip(item.get("reason")),
            "quote": clip(item.get("quote")) if line else None,
            "time": clock(line.start) if line else None,
            "proof_missing": not ok,
        })
        if not ok:
            proof_missing.append(key)
        checks.append(check)

    return MarkResult(
        checks=checks,
        rude_quote=f"[{clock(rude_line.start)}] {clip(data.get('rude_quote'))}" if rude_line else None,
        wrong_info=wrong,
        unverified_claims=[clip(c) for c in data.get("unverified_claims") or [] if isinstance(c, str)][:10],
        proof_missing=proof_missing,
        tips=tips(talk_share, interruptions_per_5min),
    )
