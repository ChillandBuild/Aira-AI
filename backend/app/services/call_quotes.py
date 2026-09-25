"""Match an AI-supplied quote back to a real transcript line.

Matching ignores case, punctuation and spacing. Short words (< 4 chars) like
"no", "not", "an", "is" must match exactly. Longer words tolerate small
spelling differences: SequenceMatcher ratio >= 0.8. A quote matches when its
words align 1:1 with a consecutive window of line words, using these rules.
This rejects fabricated quotes that flip meaning (e.g., "no charge" vs "an charge").
"""
import unicodedata
from difflib import SequenceMatcher

from app.services.call_lines import Line
from app.services.scoring_rules import QUOTE_MAX_CHARS


def _norm(text: str) -> str:
    """Normalize for substring matching: lowercase, punctuation to space, remove all whitespace."""
    kept = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text.lower())
    return "".join(kept.split())


def _norm_for_words(text: str) -> list[str]:
    """Normalize for word-level matching: return list of lowercase words with punctuation removed."""
    kept = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text.lower())
    return kept.split()


def clip(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    return text if len(text) <= QUOTE_MAX_CHARS else text[: QUOTE_MAX_CHARS - 1].rstrip() + "…"


def _words_match(quote_words: list[str], line_words: list[str], start_idx: int) -> bool:
    """Check if quote words match a window of line words starting at start_idx."""
    if start_idx + len(quote_words) > len(line_words):
        return False
    for q_word, l_word in zip(quote_words, line_words[start_idx : start_idx + len(quote_words)]):
        if len(q_word) < 4 or len(l_word) < 4:
            # Short words must match exactly
            if q_word != l_word:
                return False
        else:
            # Longer words tolerate small spelling differences
            ratio = SequenceMatcher(None, q_word, l_word, autojunk=False).ratio()
            if ratio < 0.8:
                return False
    return True


def find_quote(quote: str | None, lines: list[Line], speakers: tuple[str, ...] = ("telecaller", "customer")) -> Line | None:
    if not isinstance(quote, str):
        return None
    q_norm = _norm(quote)
    if len(q_norm) < 2:
        return None
    quote_words = _norm_for_words(quote or "")
    if not quote_words:
        return None
    for line in lines:
        if line.speaker not in speakers:
            continue
        body_norm = _norm(line.text)
        if q_norm in body_norm:
            return line
        # Try word-level matching: find a consecutive window of line words that matches quote words
        line_words = _norm_for_words(line.text)
        for i in range(len(line_words) - len(quote_words) + 1):
            if _words_match(quote_words, line_words, i):
                return line
    return None
