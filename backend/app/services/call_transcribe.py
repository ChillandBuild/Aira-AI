"""Transcribe each voice track on its own, so every line's speaker is certain.

TeleCMI records the telecaller on the right channel and the customer on the left.
Guessing speakers from a mixed recording swapped them on a real call (2026-09-25),
so the tracks are split, transcribed separately, and merged by time. A recording
without two channels falls back to one labelled pass that identifies the telecaller
by what they say (company name, "calling from", explaining the product).
"""
import logging
import re
from dataclasses import dataclass, field, replace

from app.services.call_audio import AudioChunk, resplit_chunk, split_audio, split_pcm
from app.services.call_lines import Line, clock, parse_transcript
from app.services.call_tracks import NotStereo, Segment, speech_segments, split_stereo
from app.services.gemini_client import gemini_transcribe_audio
from app.services.scoring_rules import SNAP_WINDOW_S

logger = logging.getLogger(__name__)

_TIMED_RE = re.compile(r"^\[(\d+):(\d{2})\]\s*(.*)$")
_CLUE_PHRASES = ("calling from", "call from", "i am calling", "i'm calling", "பேசுறேன்", "பேசுகிறேன்", "கம்பெனி")


class TranscriptionIncomplete(Exception):
    """A piece of the recording kept coming back cut off and could not be cut smaller."""


@dataclass
class TrackTranscript:
    lines: list[Line]
    telecaller_segments: list[Segment] = field(default_factory=list)
    customer_segments: list[Segment] = field(default_factory=list)
    stereo: bool = True


_TRACK_PROMPT = (
    "This audio is ONE side of a phone call: only one person's voice is on it. "
    "Transcribe everything this person says, completely and verbatim, in the language and "
    "script they used (Tamil, Hindi, English or a mix). Do not translate or summarise.\n"
    "Put each utterance on its own line, starting with its start time in the audio as [mm:ss], "
    "e.g. '[00:07] Hello sir'. If a stretch is unclear, write [inaudible]. If nobody speaks, "
    "return nothing. Return only the transcript."
)

_MIXED_PROMPT = (
    "Transcribe this phone call recording completely and verbatim, in the language and script "
    "each speaker used (Tamil, Hindi, English or a mix). Do not translate or summarise.\n"
    "Put each speaker turn on its own line as '[mm:ss] Telecaller: …' or '[mm:ss] Customer: …'. "
    "Decide who the telecaller is by what they say: the telecaller says the company name, says "
    "they are calling from somewhere, introduces themselves, refers to the customer's enquiry, "
    "or explains the product and its price. The customer is the one asking about it.\n"
    "If a stretch is unclear, write [inaudible]. If there is no speech, return nothing. "
    "Return only the transcript."
)


def _later_piece(prompt: str, chunk: AudioChunk) -> str:
    if chunk.start_seconds <= 0:
        return prompt
    return prompt + (
        f"\nThis audio is a later piece of the same call, starting {clock(chunk.start_seconds)} into it. "
        "Give times relative to the start of THIS piece."
    )


def parse_track_text(text: str, speaker: str, offset: float) -> list[Line]:
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = _TIMED_RE.match(raw)
        if m:
            out.append(Line(offset + int(m.group(1)) * 60 + int(m.group(2)), speaker, m.group(3).strip()))
        else:
            out.append(Line(offset, speaker, raw))
    return [l for l in out if l.text]


def snap(lines: list[Line], segments: list[Segment]) -> list[Line]:
    """Move each line's AI-given time to the nearest real speech start on its own track."""
    starts = [s for s, _ in segments]
    out = []
    for line in lines:
        near = min(starts, key=lambda s: abs(s - line.start), default=None)
        if near is not None and abs(near - line.start) <= SNAP_WINDOW_S:
            line = replace(line, start=float(near))
        out.append(line)
    return out


async def _transcribe_pieces(pieces: list[AudioChunk], prompt: str, tenant_id: str | None) -> list[tuple[str, float]]:
    pending = list(pieces)
    out: list[tuple[str, float]] = []
    while pending:
        chunk = pending.pop(0)
        text, complete = await gemini_transcribe_audio(
            chunk.data, chunk.mime_type, _later_piece(prompt, chunk), tenant_id=tenant_id, temperature=0.0,
        )
        if not complete:
            smaller = resplit_chunk(chunk)
            if not smaller:
                raise TranscriptionIncomplete(f"transcript cut off in the piece starting at {clock(chunk.start_seconds)}")
            pending[:0] = smaller
            continue
        out.append((text, chunk.start_seconds))
    return out


async def transcribe_tracks(audio: bytes, mime_type: str, tenant_id: str | None) -> TrackTranscript:
    try:
        tele_pcm, cust_pcm, rate = split_stereo(audio)
    except NotStereo:
        logger.warning("Call recording is not stereo; falling back to one labelled transcription pass")
        parts = await _transcribe_pieces(split_audio(audio, mime_type), _MIXED_PROMPT, tenant_id)
        lines: list[Line] = []
        for text, offset in parts:
            lines.extend(replace(l, start=l.start + offset) for l in parse_transcript(text))
        return TrackTranscript(sorted(lines, key=lambda l: l.start), stereo=False)

    tele_segs = speech_segments(tele_pcm, rate)
    cust_segs = speech_segments(cust_pcm, rate)
    if not tele_segs and cust_segs:
        logger.warning("Telecaller track is silent while the customer track has speech: check TELECALLER_CHANNEL")

    lines = []
    for pcm, speaker, segs in ((tele_pcm, "telecaller", tele_segs), (cust_pcm, "customer", cust_segs)):
        for text, offset in await _transcribe_pieces(split_pcm(pcm, rate, 1), _TRACK_PROMPT, tenant_id):
            lines.extend(snap(parse_track_text(text, speaker, offset), segs))
    order = {"telecaller": 0, "customer": 1}
    lines.sort(key=lambda l: (l.start, order[l.speaker]))
    return TrackTranscript(lines, tele_segs, cust_segs, stereo=True)


def _has_clue(text: str, company: str | None) -> bool:
    low = text.lower()
    if company and company.strip() and company.strip().lower() in low:
        return True
    return any(p in low for p in _CLUE_PHRASES)


def tracks_look_swapped(lines: list[Line], company_name: str | None) -> bool:
    """True when "who's calling" clues appear only on the customer's track."""
    cust = any(_has_clue(l.text, company_name) for l in lines if l.speaker == "customer")
    tele = any(_has_clue(l.text, company_name) for l in lines if l.speaker == "telecaller")
    return cust and not tele
