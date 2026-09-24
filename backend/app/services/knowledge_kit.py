"""Aira Business Kit helpers -- spec: docs/superpowers/specs/2026-09-24-aira-business-kit-design.md

The Kit is the one document shape every client is steered toward (8 headings). Clients
get it from a Word template or by pasting our prompt into their own AI, so an upload can
carry two kinds of text that must never reach replies:

- the template's invented example business, below a "delete before uploading" marker
  (strip_example) -- a client who uploads the whole file would otherwise publish fake
  prices as their own;
- placeholders: "[OWNER TO CHECK]" (what the AI prompt writes instead of guessing) and
  unfilled "[WRITE ...]" template hints (scrub_placeholders) -- otherwise a lead could be
  told "price: [OWNER TO CHECK]".

split_kit() routes a file that carries the Kit headings by heading instead of by AI
label. Without it the splitter packs short Kit sections together (a 180-char "About"
glued to the title was labelled FACT and never reached the Description) -- measured
with evals/knowledge_sort/run_kit_eval.py: 3/12 industry files sorted cleanly.

readiness() is the no-AI check behind the readiness line on the Documents tab.

No I/O here: everything is deterministic and unit-tested directly."""
import re

_EXAMPLE_MARKER_RE = re.compile(r"^.*\bexample\b.*\bdelete\b.*$", re.IGNORECASE | re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"\[(OWNER TO CHECK|WRITE\b[^\]]*)\]", re.IGNORECASE)
_HINT_RE = re.compile(r"\[WRITE\b[^\]]*\]", re.IGNORECASE)
_BARE_LABEL_RE = re.compile(r"^\s*(?:[-*\u2022]|[QA]\s*[:.)])?\s*$", re.IGNORECASE)
_QUESTION_RE = re.compile(r"^\s*Q\s*[:.)]\s*", re.IGNORECASE)
_ANSWER_RE = re.compile(r"^\s*A\s*[:.)]\s*$", re.IGNORECASE)

_PRICE_RE = re.compile(
    r"₹\s?\d|\bRs\.?\s?\d|\bINR\s?\d|\$\s?\d|\d\s?/-|\d\s?%|\d\s?(?:rupees|lakhs?|crores?)\b",
    re.IGNORECASE,
)
_QUESTIONS_RE = re.compile(
    r"^\s*Q\s*[:.)]|\b(?:refund|cancel\w*|return|warranty|guarantee|delivery|shipping|payment|instal\w*|emi)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Kit heading -> the auto-sort label it always gets. Rules feed the Description (the
# compile step also pulls the handover line out of them); facts go to lookup verbatim.
KIT_HEADINGS = {
    "ABOUT YOUR BUSINESS": "RULE",
    "WHO YOUR CUSTOMERS ARE": "RULE",
    "HOW A CUSTOMER BUYS FROM YOU": "RULE",
    "HOW AIRA SHOULD SOUND": "RULE",
    "WHAT AIRA MUST NEVER SAY OR PROMISE": "RULE",
    "WHEN TO HAND OVER TO A PERSON": "RULE",
    "PRODUCTS, SERVICES, PRICES": "FACT",
    "CUSTOMER QUESTIONS AND POLICIES": "FACT",
}
_MIN_KIT_HEADINGS = 4
_TEMPLATE_TITLE_RE = re.compile(r"^\s*(?:Aira Business Kit|Template for:.*)\s*$", re.IGNORECASE)


def _heading_key(line: str) -> str:
    """ "## 1. Who your customers are:" -> "WHO YOUR CUSTOMERS ARE". Letters only, so
    markdown, numbering and punctuation an AI or Word adds never hide a heading."""
    return " ".join(re.sub(r"[^A-Z ]", " ", line.upper()).split())


_KIT_BY_KEY = {_heading_key(h): h for h in KIT_HEADINGS}

# (key, label, level) in display order: must-haves first.
_ITEMS = [
    ("about", "About your business", "must"),
    ("how_to_buy", "How a customer buys", "must"),
    ("prices", "Products and prices", "must"),
    ("handover", "When to hand over to a person", "must"),
    ("who", "Who your customers are", "nice"),
    ("never", "What Aira must never say", "nice"),
    ("questions", "Customer questions and policies", "nice"),
    ("voice", "How Aira should sound", "optional"),
]
_DESCRIPTION_KEYS = {"about", "how_to_buy", "who", "never", "voice"}


def strip_example(text: str) -> str:
    """Cut the template's example business: everything from the marker line on."""
    match = _EXAMPLE_MARKER_RE.search(text or "")
    return (text or "")[: match.start()].rstrip() if match else (text or "")


def _gap_text(line: str) -> str:
    rest = _PLACEHOLDER_RE.sub("", line).strip()
    if not _BARE_LABEL_RE.match(rest):
        return rest
    hint = re.sub(r"^WRITE\s+", "", _PLACEHOLDER_RE.search(line).group(1).strip(), flags=re.IGNORECASE)
    return hint[:1].upper() + hint[1:]


def scrub_placeholders(text: str) -> tuple[str, list[str]]:
    """Drop every line holding a placeholder and return (clean text, gaps). An answer
    line left as a placeholder also drops its question, reported as the gap. A [WRITE]
    hint with text beside it is removed on its own and the text kept."""
    kept: list[str] = []
    gaps: list[str] = []
    for line in (text or "").split("\n"):
        if not _PLACEHOLDER_RE.search(line):
            kept.append(line)
            continue
        # A client who typed the answer beside a hint instead of over it keeps the answer.
        answered = _HINT_RE.sub("", line).strip()
        if not _BARE_LABEL_RE.match(answered) and not _PLACEHOLDER_RE.search(answered):
            kept.append(answered)
            continue
        if _ANSWER_RE.match(_PLACEHOLDER_RE.sub("", line)) and kept and _QUESTION_RE.match(kept[-1]):
            gaps.append(_QUESTION_RE.sub("", kept.pop()).strip())
        else:
            gaps.append(_gap_text(line))
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return clean, gaps


def readiness(*, description: str, handover_line: str, facts: list[str]) -> list[dict]:
    """The 8 Kit headings, each with whether Aira already has it."""
    # Imported here: business_profile imports knowledge_sort, which imports this module.
    from app.services import business_profile

    sections = business_profile.parse(description or "").sections
    facts_text = "\n\n".join(f for f in facts if f)
    found = {key: bool(sections.get(key, "").strip()) for key in _DESCRIPTION_KEYS}
    found["prices"] = bool(_PRICE_RE.search(facts_text))
    found["questions"] = bool(_QUESTIONS_RE.search(facts_text))
    found["handover"] = bool((handover_line or "").strip())
    return [{"key": key, "label": label, "level": level, "ok": found[key]} for key, label, level in _ITEMS]


def split_kit(text: str) -> list[tuple[str | None, str]] | None:
    """Cut a Kit file on its headings: [(label, "HEADING\\nbody"), ...]. Text outside
    any Kit heading comes back with label None for the AI labeller; the template's own
    title lines are dropped. None when the file has fewer than 4 Kit headings."""
    parts: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []
    seen: set[str] = set()

    def flush() -> None:
        lines = body if heading else [line for line in body if not _TEMPLATE_TITLE_RE.match(line)]
        content = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if content:
            parts.append((KIT_HEADINGS[heading], f"{heading}\n{content}") if heading else (None, content))

    for line in (text or "").split("\n"):
        canonical = _KIT_BY_KEY.get(_heading_key(line)) if len(line) <= 80 else None
        if canonical:
            flush()
            heading, body = canonical, []
            seen.add(canonical)
        else:
            body.append(line)
    flush()
    return parts if len(seen) >= _MIN_KIT_HEADINGS else None
