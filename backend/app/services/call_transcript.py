"""Call transcripts are stored in full (scoring and the no-answer safety gate read
them) but never sent to the browser: every API response carries only the first
and last line, with the middle masked. The recording is the evidence when an
admin needs more."""

_MAX_LINE_CHARS = 240


def _clip(line: str) -> str:
    return line if len(line) <= _MAX_LINE_CHARS else line[: _MAX_LINE_CHARS - 1].rstrip() + "…"


def transcript_preview(transcript: str | None) -> dict | None:
    lines = [line.strip() for line in (transcript or "").splitlines() if line.strip()]
    if not lines:
        return None
    return {
        "first": _clip(lines[0]),
        "last": _clip(lines[-1]) if len(lines) > 1 else None,
        "hidden_lines": max(0, len(lines) - 2),
    }


def mask_transcript(row: dict | None) -> dict | None:
    if isinstance(row, dict) and "transcript" in row:
        row["transcript_preview"] = transcript_preview(row.pop("transcript"))
    return row


def mask_transcripts(rows: list[dict] | None) -> list[dict]:
    return [mask_transcript(row) for row in (rows or [])]
