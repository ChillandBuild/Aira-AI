"""Step 1 — is this a real sales conversation?

The AI only points at lines (the 6 signs). The system checks every quote against the
transcript and the allowed speaker, then counts. The group is never the AI's opinion.
The same request also returns the call summary and the early-exit basic check.
"""
import asyncio
from collections import Counter
from dataclasses import dataclass

from app.services.call_lines import Line, clock, format_transcript
from app.services.call_quotes import clip, find_quote
from app.services.gemini_client import gemini_analysis_json
from app.services.scoring_rules import AI_VOTES, MIN_SIGNS

SIGN_SPEAKERS: dict[int, tuple[str, ...]] = {
    1: ("customer",), 2: ("telecaller",), 3: ("telecaller", "customer"),
    4: ("customer",), 5: ("customer",), 6: ("telecaller", "customer"),
}
EXPECTED_CRM = ("wrong_number", "not_enquired", "callback", "language_barrier", "voicemail", "other")
_SUMMARY_KEYS = (
    "course", "product", "budget", "timeline", "next_action", "sentiment", "brief",
    "objections", "commitments", "open_questions",
)

_SYSTEM = (
    "You review telecalling calls. You get a transcript whose every line is labelled with its "
    "time and whether the Telecaller or the Customer said it. The labels are certain; trust them. "
    "The call may be in English, Tamil, Hindi or a mix; write every output value in English, "
    "but copy quotes exactly as they appear in the transcript, in the original script. "
    "Only use what is in the transcript. Never invent a quote."
)

_PROMPT = """Transcript:
{transcript}

What this business sells to its customers:
{kb_block}
Talk about anything else — the telecaller's own work, internal tools, personal matters, or
anything not part of what this business sells to its customers — is casual talk, however long
or sales-like it sounds, and NEVER counts as a sign.

Find the signs of a real sales discussion. For each sign you find, copy ONE exact line (or part of a line) that proves it.
1. The customer shared a need or situation (e.g. "I need software for my shop"). Must be the customer.
2. The telecaller explained the product, service or offer: features, benefits or how it works. Just saying the company name or "I'm calling about your enquiry" does NOT count. Must be the telecaller.
3. Price, cost, plan, discount or payment was discussed. Either person.
4. The customer asked a question about the product or service (delivery, features, timing, warranty). "Who is this?" or "where did you get my number?" do NOT count. Must be the customer.
5. The customer raised a concern or objection about the offer ("too costly", "I'll think about it", "already using another one"). "I never enquired", "wrong number" or "I'm busy" do NOT count. Must be the customer.
6. A clear next step about the product: a demo, a visit, a meeting, sending a quote or a payment link, or a callback for a stated purpose. A vague "I'll do it and tell you", "I'll let you know" or a plain "call me later" does NOT count — it must be a specific, agreed action. Either person.
These NEVER count as signs, however long they go on: asking who is calling or where the number came from; wrong number or "I never enquired" with no further sales talk; "call me later", "I'm driving", "I'm busy"; not understanding each other's language; network problems, "hello? hello?", silence; voicemail, IVR or automated messages; casual talk unrelated to what this business sells.

Also answer:
- polite: false only if the telecaller was rude, mocking, dismissive or abusive; then rude_quote = the telecaller's exact line.
- enquiry_confirmed_early: true if within the first 30 seconds the telecaller referred to the customer's enquiry (e.g. "You enquired about our product yesterday, right?").
- expected_crm: what the wrap-up should say if this was not a sales conversation: one of "wrong_number", "not_enquired", "callback", "language_barrier", "voicemail", "other".
- language_barrier: true only if the two people genuinely could not understand each other (mixed Tamil-English is normal); language_barrier_quote = a line showing it.
- summary: course, product, budget, timeline, next_action, sentiment ("positive"|"neutral"|"negative"), brief (2-3 sentences), objections, commitments, open_questions (null when not mentioned).

Return JSON only:
{{"signs": [{{"sign": 1, "quote": "..."}}], "polite": true, "rude_quote": null, "enquiry_confirmed_early": false, "expected_crm": "other", "language_barrier": false, "language_barrier_quote": null, "summary": {{...}}}}"""


@dataclass
class SortResult:
    group: str
    signs: list[dict]
    summary: dict
    early_exit_check: dict | None
    language_barrier: bool
    language_barrier_quote: str | None
    rude_quote: str | None


def validate_signs(raw, lines: list[Line]) -> list[dict]:
    seen: set[int] = set()
    valid = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        sign = item.get("sign")
        if sign not in SIGN_SPEAKERS or sign in seen:
            continue
        line = find_quote(item.get("quote"), lines, SIGN_SPEAKERS[sign])
        if not line:
            continue
        seen.add(sign)
        valid.append({"sign": sign, "speaker": line.speaker, "quote": clip(item["quote"]), "time": clock(line.start)})
    return sorted(valid, key=lambda s: s["sign"])


def group_for(valid_count: int) -> str:
    return "real_conversation" if valid_count >= MIN_SIGNS else "early_exit"


def _telecaller_quote(quote, lines: list[Line]) -> str | None:
    line = find_quote(quote, lines, ("telecaller",))
    return f"[{clock(line.start)}] {clip(quote)}" if line else None


async def sort_call(lines: list[Line], tenant_id: str | None, kb_context: str | None = None) -> SortResult:
    prompt = _PROMPT.format(transcript=format_transcript(lines), kb_block=kb_context or "unknown")
    runs = await asyncio.gather(*(
        gemini_analysis_json(
            system_prompt=_SYSTEM,
            user_prompt=prompt,
            tenant_id=tenant_id,
            temperature=0.0,
            purpose="call_sorting",
        )
        for _ in range(AI_VOTES)
    ))

    sign_votes: dict[int, list[dict]] = {}
    for data in runs:
        for s in validate_signs(data.get("signs"), lines):
            sign_votes.setdefault(s["sign"], []).append(s)
    signs = sorted((votes[0] for votes in sign_votes.values() if len(votes) >= 2), key=lambda s: s["sign"])
    group = group_for(len(signs))

    summary_data = next((d.get("summary") for d in runs if isinstance(d.get("summary"), dict)), {})
    summary = {k: v for k, v in summary_data.items() if k in _SUMMARY_KEYS}

    rude_votes = []
    for d in runs:
        if d.get("polite") is False:
            quote = _telecaller_quote(d.get("rude_quote"), lines)
            if quote is not None:
                rude_votes.append(quote)
    rude_quote = rude_votes[0] if len(rude_votes) >= 2 else None

    barrier_votes = []
    for d in runs:
        if d.get("language_barrier") is True:
            line = find_quote(d.get("language_barrier_quote"), lines)
            if line is not None:
                barrier_votes.append((line, d.get("language_barrier_quote")))
    language_barrier = len(barrier_votes) >= 2
    barrier_line, barrier_quote_raw = barrier_votes[0] if language_barrier else (None, None)

    confirmed_count = sum(1 for d in runs if d.get("enquiry_confirmed_early") is True)
    enquiry_confirmed_early = confirmed_count > len(runs) / 2

    expected_votes = [d.get("expected_crm") if d.get("expected_crm") in EXPECTED_CRM else "other" for d in runs]
    counts = Counter(expected_votes)
    top = max(counts.values())
    winners = [v for v, n in counts.items() if n == top]
    expected_crm = winners[0] if len(winners) == 1 else "other"

    early = None
    if group == "early_exit":
        early = {
            "polite": rude_quote is None,
            "rude_quote": rude_quote,
            "enquiry_confirmed_early": enquiry_confirmed_early,
            "expected_crm": expected_crm,
            "crm_matches": None,
        }
    return SortResult(
        group=group,
        signs=signs,
        summary=summary,
        early_exit_check=early,
        language_barrier=language_barrier,
        language_barrier_quote=f"[{clock(barrier_line.start)}] {clip(barrier_quote_raw)}" if barrier_line else None,
        rude_quote=rude_quote,
    )
