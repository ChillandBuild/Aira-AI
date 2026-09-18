"""Line-level helpers for the Description review screen (spec §5, §6).

The Description is plain text the client edits freely. These pure functions diff the
current text against Aira's proposal, apply only the hunks the client ticked, and make
targeted single-line changes. Lines are compared whitespace-normalised so a stray
double space never shows up as a change, while equal lines always keep the client's
exact original text.

Mirrored in frontend/app/dashboard/knowledge/descriptionDiff.ts -- hunk positions index
into lines_of() on both sides, so the two splitters must stay identical."""
import difflib
from dataclasses import asdict, dataclass

_KIND_BY_TAG = {"insert": "add", "delete": "remove", "replace": "change"}


def normalize(line: str | None) -> str:
    return " ".join((line or "").split())


def lines_of(text: str | None) -> list[str]:
    r"""\r\n and \r become \n, and one trailing newline is ignored."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return []
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    return parts


def normalize_text(text: str | None) -> str:
    """Whole-text comparison key: blank lines and spacing don't count as changes."""
    return "\n".join(n for n in (normalize(line) for line in lines_of(text)) if n)


@dataclass
class Hunk:
    id: str
    kind: str  # "add" | "change" | "remove"
    start: int  # index into lines_of(current) where old_lines begin
    old_lines: list[str]
    new_lines: list[str]
    touches_client_lines: bool

    def to_dict(self) -> dict:
        return asdict(self)


def client_lines(description: str, machine_lines: set[str]) -> set[str]:
    """Normalised Description lines no sorted document claims: the client typed them,
    or edited a line a document had added."""
    return {n for n in (normalize(line) for line in lines_of(description)) if n and n not in machine_lines}


def diff_hunks(current: str, proposed: str, machine_lines: set[str]) -> list[Hunk]:
    a, b = lines_of(current), lines_of(proposed)
    matcher = difflib.SequenceMatcher(
        a=[normalize(line) for line in a], b=[normalize(line) for line in b], autojunk=False
    )
    hunks: list[Hunk] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = a[i1:i2]
        touches = any(normalize(line) and normalize(line) not in machine_lines for line in old)
        hunks.append(
            Hunk(
                id=f"h{len(hunks) + 1}",
                kind=_KIND_BY_TAG[tag],
                start=i1,
                old_lines=old,
                new_lines=b[j1:j2],
                touches_client_lines=touches,
            )
        )
    return hunks


def apply_hunks(current: str, hunks: list[Hunk], accepted_ids: set[str]) -> str:
    """Rebuild the text taking each hunk's new lines if ticked, its old lines if not.
    Hunks must be in the order diff_hunks() produced them (document order)."""
    a = lines_of(current)
    out: list[str] = []
    pos = 0
    for hunk in hunks:
        out.extend(a[pos:hunk.start])
        out.extend(hunk.new_lines if hunk.id in accepted_ids else hunk.old_lines)
        pos = hunk.start + len(hunk.old_lines)
    out.extend(a[pos:])
    return "\n".join(out)


def is_heading_line(line: str) -> bool:
    """An UPPERCASE line such as "WHAT YOU MUST NEVER DO". Requires an ASCII capital so a
    line in a caseless script (Tamil, Hindi) is never mistaken for a heading."""
    s = line.strip()
    return bool(s) and len(s) <= 60 and s == s.upper() and any("A" <= c <= "Z" for c in s)


def insert_under_heading(text: str, heading: str, line: str) -> str:
    """Add a line at the end of the heading's section; append at the end of the text
    when the heading doesn't exist."""
    lines = lines_of(text)
    target = normalize(heading).upper()
    idx = next((i for i, l in enumerate(lines) if target and normalize(l).upper() == target), None)
    if idx is None:
        return "\n".join(lines + [line]) if lines else line
    end = idx + 1
    while end < len(lines) and not is_heading_line(lines[end]):
        end += 1
    while end > idx + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    return "\n".join(lines)


def replace_exact_line(text: str, old_line: str, new_line: str) -> str | None:
    """Swap the first line matching old_line (whitespace-normalised); None if it's gone."""
    lines = lines_of(text)
    target = normalize(old_line)
    for i, line in enumerate(lines):
        if target and normalize(line) == target:
            lines[i] = new_line
            return "\n".join(lines)
    return None


def remove_lines(text: str, normalized: set[str]) -> str:
    kept = [line for line in lines_of(text) if not normalize(line) or normalize(line) not in normalized]
    out: list[str] = []
    for line in kept:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return "\n".join(out).strip()


def closest_line(target: str, candidates: list[str], cutoff: float = 0.6) -> str | None:
    """The candidate that most resembles target -- used to find the client's edited
    version of a line a document once added."""
    by_norm = {normalize(c): c for c in candidates if normalize(c)}
    match = difflib.get_close_matches(normalize(target), list(by_norm), n=1, cutoff=cutoff)
    return by_norm[match[0]] if match else None
