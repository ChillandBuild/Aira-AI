"""Pure text helpers for Knowledge Auto-Sort (spec §4.1, §4.3).

split_sections() cuts an extracted document into sections small enough to label one
by one. critical_tokens()/verify_fact() are the no-AI check that a fact the model
copied out of a section still carries that section's exact numbers, prices, links and
emails -- so a "₹29" can never come out the other side as "₹49".

No I/O here: everything is deterministic and unit-tested directly."""
import re
from dataclasses import dataclass

MAX_SECTION_CHARS = 1_000
# A heading only starts a new section once the current one has some substance --
# otherwise every "Examples" line would become its own one-line section.
_MIN_SECTION_CHARS = 200


@dataclass(frozen=True)
class Section:
    id: str
    text: str


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if line.startswith("#"):
        return True
    if not (3 <= len(line) <= 60) or line.endswith((".", "?", "!", ",", ":", ";")):
        return False
    words = line.split()
    return len(words) >= 2 and line[0].isupper() and any(len(w) >= 4 and w.isalpha() for w in words)


def _hard_split(block: str, max_chars: int) -> list[str]:
    """Split one oversized block, preferring line then sentence boundaries -- the same
    preference as knowledge_service._chunk_text, without the overlap."""
    out: list[str] = []
    rest = block
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = -1
        for sep in ("\n", ". "):
            idx = window.rfind(sep)
            if idx > max_chars // 2:
                cut = idx + len(sep)
                break
        if cut == -1:
            cut = max_chars
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def split_sections(text: str, max_chars: int = MAX_SECTION_CHARS) -> list[Section]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    pieces: list[str] = []
    for block in blocks:
        pieces.extend([block] if len(block) <= max_chars else _hard_split(block, max_chars))

    sections: list[str] = []
    current = ""
    for piece in pieces:
        starts_topic = _looks_like_heading(piece.split("\n", 1)[0])
        too_big = len(current) + 2 + len(piece) > max_chars
        if current and (too_big or (starts_topic and len(current) >= _MIN_SECTION_CHARS)):
            sections.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        sections.append(current)
    return [Section(id=f"s{i + 1}", text=t) for i, t in enumerate(sections)]


_URL_RE = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def critical_tokens(text: str | None) -> set[str]:
    """Every URL, email and number in the text. Numbers cover prices ("₹29" -> "29"),
    phone numbers and counts. Thousands separators are dropped so "1,10,000" and
    "110000" compare equal; emails compare case-insensitively."""
    text = text or ""
    urls = {u.rstrip(".,;:!?") for u in _URL_RE.findall(text)}
    rest = _URL_RE.sub(" ", text)
    emails = {e.lower() for e in _EMAIL_RE.findall(rest)}
    rest = _EMAIL_RE.sub(" ", rest)
    numbers = {n.replace(",", "") for n in _NUMBER_RE.findall(rest)}
    return urls | emails | numbers


def unverified_tokens(candidate: str | None, *sources: str | None) -> set[str]:
    """Tokens in the candidate that appear in none of the sources."""
    known: set[str] = set()
    for source in sources:
        known |= critical_tokens(source)
    return critical_tokens(candidate) - known


def verify_fact(fact: str, source: str) -> bool:
    return not unverified_tokens(fact, source)
