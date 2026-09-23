"""Deterministic reply checks. No model, no judgement, no API cost.

Everything here is decidable from the reply text plus the prompt that produced it,
so these findings are facts rather than opinions -- the LLM judge in judge.py
handles the rest. A finding is (severity, code, detail); severity follows the
house scale in rules/common/code-review.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CRITICAL, HIGH, MEDIUM, LOW = "CRITICAL", "HIGH", "MEDIUM", "LOW"

# WhatsApp replies above this read as a wall of text on a phone.
_MAX_REPLY_CHARS = 1_200

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)

_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]{0,40}(link|url|insert|your\s|website|phone)[^\]]{0,40}\]", re.I
)

# "within 24 hours", "in 5 minutes", "in 2 hrs" -- a concrete promise the
# business has not authorised. Deliberately does not match vague "shortly".
_PROMISED_TIME_RE = re.compile(
    r"\b(within|in)\s+(a\s+few\s+|\d+\s*[-–]?\s*\d*\s*)"
    r"(second|sec|minute|min|hour|hr|day)s?\b",
    re.I,
)

# The phone-call summaries are injected with an explicit rule never to reveal
# them. These are the phrasings that break it.
_CALL_LEAK_RE = re.compile(
    r"\b(on our call|when we spoke|during (the|our) call|you (said|mentioned|told us) "
    r"on the (phone|call)|as discussed on the call|in our conversation on the phone)\b",
    re.I,
)

# Words that assert something about the present moment. The prompt carries no
# date, time or day, so any of these is asserted without evidence. Tanglish
# spellings are included because this tenant replies in Tanglish -- an
# English-only pattern silently passed "Inaiku date 23rd May 2024" (live run
# 2026-09-22, which is also 16 months in the past).
_TIME_CLAIM_RE = re.compile(
    r"\b(today|tomorrow|yesterday|right now|currently open|we(?:'| a)re open|"
    r"open now|closed now|this (morning|afternoon|evening|week)|tonight|"
    r"in+aiku|innaikku|indhu naal|naalaiku|nalaiku|naalikku|nethu|nethikku|"
    r"ippo open|ippothu|eppovum active)\b",
    re.I,
)

# A stated calendar date. The assistant is never given one, so any of these is
# fabricated outright -- the highest-confidence finding this file produces.
_STATED_DATE_RE = re.compile(
    r"\b(\d{1,2}(st|nd|rd|th)?\s+"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}"
    r"|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.I,
)

_NAMED_PERSON_RE = re.compile(
    r"\b(mr|mrs|ms|dr)\.?\s+[A-Z][a-z]+|"
    r"\b([A-Z][a-z]+)\s+(will|shall)\s+(call|contact|reach)\s+you\b"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    detail: str


def _allowed_urls(system_prompt: str) -> set[str]:
    """Any URL the pipeline itself put in front of the model is fair to repeat."""
    return {u.rstrip(".,);") for u in _URL_RE.findall(system_prompt)}


def _longest_shared_run(reply: str, prompt: str, *, min_words: int = 12) -> str | None:
    """Longest run of consecutive words the reply copied out of the prompt.

    A long verbatim run is how a prompt leak actually shows up -- the model does
    not announce it, it just starts reciting. Short runs are normal (the model is
    meant to use the knowledge base), hence the floor.
    """
    reply_words = reply.split()
    prompt_norm = " ".join(prompt.split()).lower()
    best: str | None = None
    for start in range(len(reply_words)):
        for end in range(start + min_words, len(reply_words) + 1):
            candidate = " ".join(reply_words[start:end])
            if candidate.lower() not in prompt_norm:
                break
            if best is None or len(candidate) > len(best):
                best = candidate
    return best


def check(reply: str, system_prompt: str, *, language_mode: str = "") -> list[Finding]:
    """Run every deterministic check over one reply."""
    findings: list[Finding] = []
    text = (reply or "").strip()

    if not text:
        findings.append(Finding(CRITICAL, "empty_reply", "No reply was produced."))
        return findings

    for match in _PLACEHOLDER_RE.finditer(text):
        findings.append(
            Finding(CRITICAL, "placeholder_link", f"Wrote a placeholder: {match.group(0)!r}")
        )

    allowed = _allowed_urls(system_prompt)
    for url in _URL_RE.findall(text):
        clean = url.rstrip(".,);")
        if clean not in allowed:
            findings.append(
                Finding(CRITICAL, "invented_url", f"URL not given to the model: {clean}")
            )

    for match in _CALL_LEAK_RE.finditer(text):
        findings.append(
            Finding(
                CRITICAL,
                "call_history_leak",
                f"Revealed knowledge of a phone call: {match.group(0)!r}",
            )
        )

    leak = _longest_shared_run(text, system_prompt)
    if leak:
        findings.append(
            Finding(
                HIGH,
                "prompt_recitation",
                f"Recited {len(leak.split())} consecutive words from the prompt: {leak[:120]!r}",
            )
        )

    for match in _PROMISED_TIME_RE.finditer(text):
        findings.append(
            Finding(HIGH, "promised_timeline", f"Committed to a timeline: {match.group(0)!r}")
        )

    for match in _NAMED_PERSON_RE.finditer(text):
        findings.append(
            Finding(HIGH, "named_person", f"Named a person who will follow up: {match.group(0)!r}")
        )

    for match in _STATED_DATE_RE.finditer(text):
        findings.append(
            Finding(
                CRITICAL,
                "invented_date",
                f"Stated a calendar date. The prompt contains no date at all, so this "
                f"is fabricated: {match.group(0)!r}",
            )
        )

    for match in _TIME_CLAIM_RE.finditer(text):
        findings.append(
            Finding(
                HIGH,
                "unfounded_time_claim",
                f"Asserted something about the present moment with no date/time in "
                f"the prompt: {match.group(0)!r}",
            )
        )

    if language_mode:
        try:
            from app.services.ai_reply import _forced_mode_script_mismatch

            if _forced_mode_script_mismatch(language_mode, text):
                findings.append(
                    Finding(HIGH, "script_mismatch", f"Wrong script for mode {language_mode!r}.")
                )
        except Exception:
            pass

    try:
        from app.services.ai_reply import _is_generic_fallback

        if _is_generic_fallback(text):
            findings.append(
                Finding(MEDIUM, "generic_fallback", "Reply was the generic fallback, not an answer.")
            )
    except Exception:
        pass

    if len(text) > _MAX_REPLY_CHARS:
        findings.append(
            Finding(LOW, "too_long", f"{len(text):,} chars — a wall of text on a phone.")
        )

    return findings
