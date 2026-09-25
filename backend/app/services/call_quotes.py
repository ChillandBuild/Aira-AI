"""Match an AI-supplied quote back to a real transcript line.

Matching ignores case, punctuation and spacing, and tolerates small spelling
differences (the AI often re-spells Tamil slightly), but a quote that isn't
substantially present in one line from an allowed speaker is rejected.
"""
import unicodedata
from difflib import SequenceMatcher

from app.services.call_lines import Line
from app.services.scoring_rules import QUOTE_MAX_CHARS

_MATCH_RATIO = 0.85


def _norm(text: str) -> str:
    kept = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text.lower())
    return "".join(kept.split())


def clip(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= QUOTE_MAX_CHARS else text[: QUOTE_MAX_CHARS - 1].rstrip() + "…"


def find_quote(quote: str | None, lines: list[Line], speakers: tuple[str, ...] = ("telecaller", "customer")) -> Line | None:
    q = _norm(quote or "")
    if len(q) < 2:
        return None
    for line in lines:
        if line.speaker not in speakers:
            continue
        body = _norm(line.text)
        if q in body:
            return line
        match = SequenceMatcher(None, q, body, autojunk=False).find_longest_match(0, len(q), 0, len(body))
        if match.size / len(q) >= _MATCH_RATIO:
            return line
        if SequenceMatcher(None, q, body, autojunk=False).ratio() >= _MATCH_RATIO and len(q) >= len(body) * 0.6:
            return line
    return None
