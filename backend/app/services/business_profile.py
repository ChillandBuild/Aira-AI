"""Business profile: fixed sections on top of free-text description.

Each section (about, how_to_buy, who, voice, job, never, hours_contact, handover) has a
heading, label, hint, and per-section word limit. The Description is stored in app_settings as plain text with
all sections combined and optional free-form "other" text. parse() splits by headings,
render() reconstructs, propose_conversion() uses LLM to migrate free-text descriptions
into structured sections.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.config_dynamic import get_setting
from app.services.knowledge_sort import _llm_json

logger = logging.getLogger(__name__)

HARD_WORD_LIMIT = 700


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    label: str
    hint: str
    word_limit: int


SECTIONS = [
    Section("about", "ABOUT US", "About us",
            "What you are and what you sell, in two or three lines.", 80),
    Section("how_to_buy", "HOW CUSTOMERS BUY", "How customers buy",
            "The steps to buy or book, where, and a one-line price summary. Full price lists go in Documents.", 60),
    Section("who", "WHO WE TALK TO", "Who we talk to",
            "Who messages you and why.", 60),
    Section("voice", "HOW TO SOUND", "How to sound",
            "Tone, greeting and closing lines, words and spellings to use. Not which language: that is a setting.", 120),
    Section("job", "YOUR JOB IN EVERY CONVERSATION", "Your job in every conversation",
            "Rules specific to your business. General good behaviour is already built in.", 120),
    Section("never", "WHAT YOU MUST NEVER DO", "Never do",
            "Things specific to your business the assistant must never say or do.", 80),
    Section("hours_contact", "BUSINESS HOURS AND CONTACT", "Business hours and contact",
            "When you are open, and the phone number, email or address customers may be given.", 60),
    Section("handover", "WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM", "What Aira says when it brings in your team",
            "The line Aira says when a person from your team takes over, in your own words.", 50),
]

HANDOVER_KEY = "handover"

HEADING_ALIASES = {
    "WHAT WE OFFER": "about",
    "GREETINGS AND CLOSINGS": "voice",
    "LANGUAGE": "voice",
}

_SECTION_BY_KEY = {s.key: s for s in SECTIONS}
_SECTION_BY_HEADING = {s.heading: s.key for s in SECTIONS}


def _normalize_heading(text: str) -> str:
    """Normalize heading for comparison (strip, uppercase, strip trailing colon)."""
    return text.strip().rstrip(":").upper()


_HEADING_RE = re.compile(r"^[A-Z][A-Z0-9 &/'()-]{2,}:?$")


def _looks_like_heading(line: str) -> bool:
    """An all-caps line with no bullet, e.g. "HAND OVER TO A PERSON WHEN"."""
    stripped = line.strip()
    return bool(stripped) and bool(_HEADING_RE.match(stripped))


looks_like_heading = _looks_like_heading


def section_key_for_heading(line: str) -> Optional[str]:
    """The section key when the line is a known heading (or alias), else None."""
    normalized = _normalize_heading(line)
    return _SECTION_BY_HEADING.get(normalized) or HEADING_ALIASES.get(normalized)


def heading_keys(text: str) -> set[str]:
    """Keys of every section whose heading appears in the text, even when the section
    under it is empty (parse() drops empty sections, so it cannot tell "no heading" from
    "heading with nothing under it")."""
    keys = {section_key_for_heading(line) for line in (text or "").split("\n")}
    return {key for key in keys if key}


@dataclass(frozen=True)
class ParsedProfile:
    sections: dict[str, str]  # key -> text
    other: str = ""


def parse(text: str) -> ParsedProfile:
    """Split text by section headings into ParsedProfile.
    
    A heading is a line that, stripped and uppercased, matches a known heading or alias.
    Text before any heading, or under an unknown heading, goes to 'other'.
    Multiple blocks for one key are joined with newline.
    """
    if not text:
        return ParsedProfile(sections={}, other="")
    
    sections: dict[str, str] = {}
    other_parts: list[str] = []
    current_key: Optional[str] = None
    lines = text.split("\n")
    has_handover_heading = False
    
    for line in lines:
        found_key = section_key_for_heading(line)
        
        if found_key:
            current_key = found_key
            has_handover_heading = has_handover_heading or found_key == HANDOVER_KEY
        elif _looks_like_heading(line):
            # An unknown heading ends the current section: its block goes to "other"
            # (heading kept) instead of being glued onto the section above it.
            current_key = None
            other_parts.append(line)
        else:
            # Not a heading; append to current section or other
            if current_key:
                sections[current_key] = (sections.get(current_key, "") + "\n" + line).lstrip("\n")
            else:
                other_parts.append(line)
    
    # Clean up: strip trailing whitespace from each section and join other
    clean_sections = {k: v.strip() for k, v in sections.items() if v.strip()}
    if has_handover_heading:
        # An empty handover heading is the owner's choice ("use Aira's default wording"),
        # not a missing section, so it must survive a parse/render round trip.
        clean_sections.setdefault(HANDOVER_KEY, "")
    clean_other = "\n".join(other_parts).strip()
    
    return ParsedProfile(sections=clean_sections, other=clean_other)


def render(sections: dict[str, str], other: str = "") -> str:
    """Reconstruct text from sections dict and optional other.
    
    Renders sections in SECTIONS order, each section on one line with heading,
    followed by blank line. Then other text last (if any). Empty sections are dropped,
    except handover: a handover key set to "" keeps its heading with an empty body, so
    get_handover_line returns "" and the legacy handover_line setting does not come back.
    """
    parts: list[str] = []
    
    for section in SECTIONS:
        text = sections.get(section.key, "").strip()
        if text:
            parts.append(f"{section.heading}\n{text}")
        elif section.key == HANDOVER_KEY and HANDOVER_KEY in sections:
            parts.append(section.heading)
    
    if other.strip():
        parts.append(other.strip())
    
    return "\n\n".join(parts)


def word_count(text: str) -> int:
    """Count words by splitting on whitespace."""
    return len(text.split())


def is_structured(text: str) -> bool:
    """Return True if text has at least one section and no 'other' content."""
    parsed = parse(text)
    return any(parsed.sections.values()) and not parsed.other.strip()


def validate(sections: dict[str, str], other: str = "") -> list[str]:
    """Validate sections and other.
    
    Returns list of error strings:
    - unknown keys in sections
    - total word count exceeds HARD_WORD_LIMIT
    """
    errors: list[str] = []
    
    # Check for unknown keys
    for key in sections.keys():
        if key not in _SECTION_BY_KEY:
            errors.append(f"Unknown section: {key}")
    
    # Check total word count
    total = sum(word_count(text) for text in sections.values()) + word_count(other)
    if total > HARD_WORD_LIMIT:
        errors.append(f"Total is {total} words; the limit is {HARD_WORD_LIMIT}.")
    
    return errors


def warnings(sections: dict[str, str]) -> list[dict]:
    """Return list of per-section word limit warnings.
    
    Each item: {"key": str, "words": int, "limit": int}
    """
    result: list[dict] = []
    for section in SECTIONS:
        text = sections.get(section.key, "").strip()
        if text:
            words = word_count(text)
            if words > section.word_limit:
                result.append({
                    "key": section.key,
                    "words": words,
                    "limit": section.word_limit,
                })
    return result


def get_handover_line(tenant_id: Optional[str]) -> str:
    """What Aira says when it brings in the team: the 8th Description section.

    The one reader every consumer uses (the reply prompt, the Knowledge readiness
    route, the conflict check). The old handover_line setting is consulted only while
    the Description has no 8th heading at all. A heading with nothing under it is the
    owner's choice: empty here, so Aira uses its default wording, and the legacy line
    never comes back. (scripts/migrate_handover_to_description.py copies each legacy
    line into the section and blanks the old setting.)"""
    description = get_setting("business_description", tenant_id=tenant_id) or ""
    if HANDOVER_KEY in heading_keys(description):
        return parse(description).sections.get(HANDOVER_KEY, "").strip()
    return (get_setting("handover_line", tenant_id=tenant_id) or "").strip()


async def propose_conversion(tenant_id: str, text: str) -> dict:
    """Convert free-text description into structured sections using LLM.
    
    Returns dict with:
    - "sections": {key: text} - only known keys, stripped
    - "removed": [{text, why}] - lines removed (in master or about language)
    - "facts_to_move": [str] - concrete facts that belong in Documents
    - "suggested_handover": str - always "" now; kept so an older frontend does not crash.
      Handover wording goes into the "handover" section, phone and hours into "hours_contact".
    - "total_words": int - total word count across sections
    - "warnings": [...] - per-section word limit warnings
    - "errors": [...] - validation errors
    """
    if not text or not text.strip():
        return {
            "sections": {},
            "removed": [],
            "facts_to_move": [],
            "suggested_handover": "",
            "total_words": 0,
            "warnings": [],
            "errors": ["Description is empty."],
        }
    
    from app.services.ai_reply import get_master_prompt
    
    master_prompt = get_master_prompt()[:16000]  # Truncate to 16K
    
    system_prompt = """You convert a free-text business description into a structured profile.

The profile has 8 sections with limits (total 700 words):
- ABOUT US (80 words): What you are and what you sell.
- HOW CUSTOMERS BUY (60 words): Steps to buy/book, where, one-line price summary.
- WHO WE TALK TO (60 words): Who messages you and why.
- HOW TO SOUND (120 words): Tone, greetings, closings, spellings, style.
- YOUR JOB IN EVERY CONVERSATION (120 words): Business-specific rules.
- WHAT YOU MUST NEVER DO (80 words): Business-specific prohibitions.
- BUSINESS HOURS AND CONTACT (60 words): Opening hours, phone/WhatsApp number, email, address customers may be given.
- WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM (50 words): The one line said to the customer when a person from the team takes over, in the business's own words.

Rules:
1. Keep the business's own wording wherever possible; shorten only to fit limits.
2. REMOVE lines that repeat the platform's master prompt (already built in). List them in "removed".
3. REMOVE language/reply-language rules (e.g., "reply in Tamil") — that's a setting. Keep style/phrases/spellings.
4. Route contact and handover text, never drop it: phone numbers, opening hours and contact details go to "hours_contact"; the sentence said to the customer when a person takes over ("hand over", "support team", "contact us") goes to "handover"; which situations need a person goes to "job".
5. Move concrete facts (prices, offers, counts, policies, links) to "facts_to_move" — but keep a one-line price summary in HOW CUSTOMERS BUY.
6. Drop example conversations unless an exact phrase must be used.
7. NOTHING MAY DISAPPEAR SILENTLY. Every rule or fact in the description must end up in
   exactly one place: a section, "removed" (with a short why), or "facts_to_move".
   Before answering, go through the description line by line and check this.
8. Only remove a rule as "already in the platform rules" when the master prompt clearly
   says the same thing. Business-specific rules (about this business's products, offers,
   phrases, or what it must never claim) are never duplicates: keep them, shortened.

Output JSON (only these keys):
{"sections": {"about": "...", "how_to_buy": "...", "who": "...", "voice": "...", "job": "...", "never": "...", "hours_contact": "...", "handover": "..."},
 "removed": [{"text": "...", "why": "..."}],
 "facts_to_move": ["..."]}"""
    
    user_message = (
        f"Free-text description:\n{text}\n\n"
        f"Platform master prompt (already in Aira):\n{master_prompt}"
    )
    
    try:
        data = await _llm_json(system_prompt, user_message, tenant_id=tenant_id, max_tokens=4000)
    except Exception as e:
        logger.warning(f"propose_conversion LLM failed for tenant {tenant_id}: {e}")
        return {
            "sections": {},
            "removed": [],
            "facts_to_move": [],
            "suggested_handover": "",
            "total_words": 0,
            "warnings": [],
            "errors": [str(e)],
        }
    
    # Extract and clean up sections
    sections: dict[str, str] = {}
    raw_sections = data.get("sections") or {}
    for key in _SECTION_BY_KEY.keys():
        text = str(raw_sections.get(key, "") or "").strip()
        if text:
            sections[key] = text
    
    # Extract removed and facts_to_move
    removed: list[dict] = []
    for item in (data.get("removed") or []):
        if isinstance(item, dict):
            removed.append({
                "text": str(item.get("text", "")).strip()[:500],
                "why": str(item.get("why", "")).strip()[:200],
            })
    
    facts_to_move: list[str] = []
    for item in (data.get("facts_to_move") or []):
        fact = str(item).strip()
        if fact:
            facts_to_move.append(fact[:500])
    
    # Compute totals and validate
    total_words = sum(word_count(text) for text in sections.values())
    errs = validate(sections, "")
    warns = warnings(sections)
    
    return {
        "sections": sections,
        "removed": removed,
        "facts_to_move": facts_to_move,
        "suggested_handover": "",
        "total_words": total_words,
        "warnings": warns,
        "errors": errs,
    }
