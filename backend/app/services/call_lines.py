"""One transcript line: when it started, who said it, what was said."""
import re
from dataclasses import dataclass
from typing import Literal

Speaker = Literal["telecaller", "customer"]
_LABEL = {"telecaller": "Telecaller", "customer": "Customer"}
_LINE_RE = re.compile(r"^(?:\[(\d+):(\d{2})\]\s*)?(Telecaller|Customer):\s*(.*)$")


@dataclass(frozen=True)
class Line:
    start: float
    speaker: Speaker
    text: str


def clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def format_transcript(lines: list[Line]) -> str:
    return "\n".join(f"[{clock(l.start)}] {_LABEL[l.speaker]}: {l.text}" for l in lines)


def parse_transcript(text: str | None) -> list[Line]:
    out: list[Line] = []
    for raw in (text or "").splitlines():
        m = _LINE_RE.match(raw.strip())
        if not m:
            continue
        minutes, secs, label, body = m.groups()
        start = float(int(minutes) * 60 + int(secs)) if minutes is not None else 0.0
        out.append(Line(start, "telecaller" if label == "Telecaller" else "customer", body.strip()))
    return out
