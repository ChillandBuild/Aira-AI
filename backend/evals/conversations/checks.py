"""Deterministic (hard) checks over a conversation transcript.

Design: docs/plans/ai-native-conversation.md section 5. Names match the keys in
scenarios.json -> hard_checks. Each check is a pure function
(transcript, config) -> CheckResult; nothing here touches the DB or an LLM.

Transcript = list of turns:
  {"lead": str,
   "replies": [{"text": str, "kind": "text"|"buttons"|"list", "options": [str]}],
   "events": [{"type": "payment_link", "url": str, "missing_required": [str]},
              {"type": "handover", "reason": str}]}

A check that cannot be decided offline (language, the 24-hour window) returns
"skip" -- never a silent pass.
"""
import difflib
import re
from dataclasses import dataclass
from urllib.parse import urlparse

PASS, FAIL, SKIP = "pass", "fail", "skip"

MAX_QUANTITY_MULTIPLE = 10
SIMILAR_REPLY_RATIO = 0.9
MENU_KINDS = ("buttons", "list")

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT_BEFORE_RE = re.compile(rf"(?:₹|\bRs\.?|\bINR)\s*({_NUMBER})", re.IGNORECASE)
_AMOUNT_AFTER_RE = re.compile(rf"({_NUMBER})\s*(?:Rs\b|rupees?\b|ரூபாய்)", re.IGNORECASE)
_NUMBER_RE = re.compile(_NUMBER)
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_EMPTY_BLOCK_RE = re.compile(r"\n[ \t]*\n[ \t]*\n")
_PAYMENT_WORD_RE = re.compile(r"\b(paid|payment|pay pana|pay pannen|pay panna|money)\b", re.IGNORECASE)
_HUMAN_REQUEST_RE = re.compile(r"\b(person|human|agent|talk to|speak to|call me)\b", re.IGNORECASE)
_REFUSAL_RE = re.compile(
    r"(not interested|don'?t message|dont message|stop messaging|vendaam|வேண்டாம்|leave me alone)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""


def _replies(turn: dict) -> list[dict]:
    return turn.get("replies") or []


def _all_reply_text(transcript: list[dict]) -> list[str]:
    return [r["text"] for turn in transcript for r in _replies(turn)]


def _events(transcript: list[dict], kind: str) -> list[tuple[int, dict]]:
    return [(i, e) for i, t in enumerate(transcript) for e in t.get("events") or [] if e.get("type") == kind]


def _collect_amounts(nodes: list[dict], key: str) -> set[float]:
    """Rupee prices from a nested list of packages / add-ons / catalog items."""
    found: set[float] = set()
    for node in nodes or []:
        if node.get(key):
            found.add(node[key] / 100)
        for child_key in ("children", "options", "addons"):
            found |= _collect_amounts(node.get(child_key) or [], key)
    return found


def _with_addons(nodes: list[dict]) -> set[float]:
    """Each package price plus every combination of its add-ons (a real total the customer pays)."""
    totals: set[float] = set()
    for node in nodes or []:
        combos = {node.get("amount_paise") or 0}
        for addon in node.get("addons") or []:
            combos |= {c + addon["amount_paise"] for c in combos}
        totals |= {c / 100 for c in combos if c}
        totals |= _with_addons(node.get("options") or [])
    return totals


def _allowed_prices(config: dict) -> set[float]:
    base = _collect_amounts(config.get("packages") or [], "amount_paise") | _with_addons(config.get("packages") or [])
    base |= _collect_amounts(config.get("catalog") or [], "price_paise")
    return {p * n for p in base for n in range(1, MAX_QUANTITY_MULTIPLE + 1)}


def _amounts_in(text: str) -> set[float]:
    raw = _AMOUNT_BEFORE_RE.findall(text) + _AMOUNT_AFTER_RE.findall(text)
    return {float(a.replace(",", "")) for a in raw}


def no_invented_price(transcript: list[dict], config: dict) -> CheckResult:
    allowed = _allowed_prices(config)
    lead_said: set[float] = set()
    bad: set[float] = set()
    for turn in transcript:
        lead_said |= {float(n.replace(",", "")) for n in _NUMBER_RE.findall(turn.get("lead", ""))}
        for reply in _replies(turn):
            bad |= {a for a in _amounts_in(reply["text"]) if a not in allowed and a not in lead_said}
    if bad:
        return CheckResult("no_invented_price", FAIL, f"amounts not in config: {sorted(bad)}")
    return CheckResult("no_invented_price", PASS)


def no_invented_link(transcript: list[dict], config: dict) -> CheckResult:
    """A link must come from a tool in the SAME turn, or from a host the business uses. A payment
    link copied from an earlier turn may be for a different amount, so it does not count."""
    hosts = tuple(config.get("allowed_hosts") or ())
    bad = []
    for turn in transcript:
        turn_urls = {e.get("url") for e in turn.get("events") or [] if e.get("type") == "payment_link"}
        for reply in _replies(turn):
            for url in _URL_RE.findall(reply["text"]):
                host = urlparse(url).hostname or ""
                if url in turn_urls or any(host == h or host.endswith("." + h) for h in hosts):
                    continue
                bad.append(url)
    if bad:
        return CheckResult("no_invented_link", FAIL, f"links not from this turn's tool or the business: {bad}")
    return CheckResult("no_invented_link", PASS)


def link_needs_details(transcript: list[dict], config: dict) -> CheckResult:
    for idx, event in _events(transcript, "payment_link"):
        if event.get("missing_required"):
            return CheckResult(
                "link_needs_details", FAIL,
                f"turn {idx}: link created while missing {event['missing_required']}",
            )
    return CheckResult("link_needs_details", PASS)


def no_empty_block(transcript: list[dict], config: dict) -> CheckResult:
    for i, turn in enumerate(transcript):
        for reply in _replies(turn):
            if _EMPTY_BLOCK_RE.search(reply["text"]):
                return CheckResult("no_empty_block", FAIL, f"turn {i}: blank gap where a list or summary should be")
    return CheckResult("no_empty_block", PASS)


def _menu_signature(turn: dict) -> tuple | None:
    for reply in _replies(turn):
        if reply.get("kind") in MENU_KINDS:
            return tuple(reply.get("options") or ())
    return None


def _last_text(turn: dict) -> str | None:
    replies = _replies(turn)
    return replies[-1]["text"].strip().lower() if replies else None


def no_repeat(transcript: list[dict], config: dict) -> CheckResult:
    for i in range(1, len(transcript)):
        prev_text, text = _last_text(transcript[i - 1]), _last_text(transcript[i])
        if prev_text and text and difflib.SequenceMatcher(None, prev_text, text).ratio() >= SIMILAR_REPLY_RATIO:
            return CheckResult("no_repeat", FAIL, f"turn {i}: near-identical to the previous reply")
        menu, prev_menu = _menu_signature(transcript[i]), _menu_signature(transcript[i - 1])
        if menu and menu == prev_menu:
            return CheckResult("no_repeat", FAIL, f"turn {i}: same menu sent two turns in a row")
    return CheckResult("no_repeat", PASS)


def _first_turn_matching(transcript: list[dict], pattern: re.Pattern) -> int | None:
    for i, turn in enumerate(transcript):
        if pattern.search(turn.get("lead", "")):
            return i
    return None


def _handover_by(name: str, transcript: list[dict], trigger_idx: int | None, why: str) -> CheckResult:
    if trigger_idx is None:
        return CheckResult(name, SKIP, "scenario has no matching lead message")
    handovers = _events(transcript, "handover")
    if not handovers:
        return CheckResult(name, FAIL, f"no handover at all ({why})")
    first = min(i for i, _ in handovers)
    if first > trigger_idx:
        return CheckResult(name, FAIL, f"handover at turn {first}, but {why} at turn {trigger_idx}")
    return CheckResult(name, PASS)


def handover_on_payment_complaint(transcript: list[dict], config: dict) -> CheckResult:
    idx = _first_turn_matching(transcript, _PAYMENT_WORD_RE)
    return _handover_by("handover_on_payment_complaint", transcript, idx, "the lead first mentioned paying")


def handover_on_human_request(transcript: list[dict], config: dict) -> CheckResult:
    idx = _first_turn_matching(transcript, _HUMAN_REQUEST_RE)
    return _handover_by("handover_on_human_request", transcript, idx, "the lead asked for a person")


def handover_on_unknown_twice(transcript: list[dict], config: dict) -> CheckResult:
    """Whether Aira 'could not answer' is a judgement call, so offline this only
    requires that some handover happened by the end of the scenario."""
    if not transcript:
        return CheckResult("handover_on_unknown_twice", SKIP, "empty transcript")
    return _handover_by("handover_on_unknown_twice", transcript, len(transcript) - 1, "the scenario ended")


def respects_opt_out(transcript: list[dict], config: dict) -> CheckResult:
    idx = _first_turn_matching(transcript, _REFUSAL_RE)
    if idx is None:
        return CheckResult("respects_opt_out", SKIP, "scenario has no refusal")
    for turn in transcript[idx:]:
        pushed = any(r.get("kind") in MENU_KINDS or _URL_RE.search(r["text"]) for r in _replies(turn))
        if pushed or any(e.get("type") == "payment_link" for e in turn.get("events") or []):
            return CheckResult("respects_opt_out", FAIL, "menu or link sent after a clear refusal")
    return CheckResult("respects_opt_out", PASS)


_MARKER_RESIDUE_RE = re.compile(r"\bCHOICES?\s*[:：]", re.IGNORECASE)


def choices_tappable(transcript: list[dict], config: dict) -> CheckResult:
    """Options offered in a plain-text reply must have gone out as buttons or a list, and the
    model's CHOICES line must never reach the customer (services/choices.py)."""
    from app.services import choices

    for i, turn in enumerate(transcript):
        for reply in _replies(turn):
            if reply.get("kind") != "text":
                continue
            text = reply["text"]
            if _MARKER_RESIDUE_RE.search(text):
                return CheckResult("choices_tappable", FAIL, f"turn {i}: CHOICES line leaked to the customer")
            if choices.extract(text)[1] or choices.inline_options(text):
                return CheckResult("choices_tappable", FAIL, f"turn {i}: options listed as plain text, no buttons")
    return CheckResult("choices_tappable", PASS)


def offers_tappable_choice(transcript: list[dict], config: dict) -> CheckResult:
    """The scenario is built so that Aira has to ask the lead to pick: some reply must carry
    buttons or a list."""
    for turn in transcript:
        if any(reply.get("kind") in MENU_KINDS for reply in _replies(turn)):
            return CheckResult("offers_tappable_choice", PASS)
    return CheckResult("offers_tappable_choice", FAIL, "no reply carried tappable options")


def _undecidable(name: str, why: str):
    def check(transcript: list[dict], config: dict) -> CheckResult:
        return CheckResult(name, SKIP, why)
    return check


HARD_CHECKS = {
    "no_invented_price": no_invented_price,
    "no_invented_link": no_invented_link,
    "link_needs_details": link_needs_details,
    "no_empty_block": no_empty_block,
    "no_repeat": no_repeat,
    "handover_on_payment_complaint": handover_on_payment_complaint,
    "handover_on_unknown_twice": handover_on_unknown_twice,
    "handover_on_human_request": handover_on_human_request,
    "respects_opt_out": respects_opt_out,
    "choices_tappable": choices_tappable,
    "offers_tappable_choice": offers_tappable_choice,
    "window_respected": _undecidable("window_respected", "needs the real send path; not testable offline"),
    "language_matches": _undecidable("language_matches", "graded by the LLM judge, not a fixed rule"),
}


ALWAYS_CHECKS = ("choices_tappable",)  # run on every scenario, listed or not


def run_check(name: str, transcript: list[dict], config: dict) -> CheckResult:
    check = HARD_CHECKS.get(name)
    if check is None:
        return CheckResult(name, SKIP, "unknown check")
    return check(transcript, config)
