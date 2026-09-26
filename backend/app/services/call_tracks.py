"""TeleCMI records each person on their own channel: right = telecaller, left = customer.

Everything here is plain signal counting — no AI, same answer every run.
"""
from array import array

from app.services.call_audio import decode_wav
from app.services.scoring_rules import (
    FRAME_SECONDS, MERGE_GAP_S, MIN_SPEECH_RUN_S, NOISE_FLOOR_MULTIPLIER, OVERLAP_MIN_S,
    SPEECH_MIN_LEVEL, TELECALLER_CHANNEL, TELECALLER_RUN_MIN_S,
)

Segment = tuple[float, float]


class NotStereo(Exception):
    """The recording isn't a two-channel WAV, so the speakers can't be separated by channel."""


def split_stereo(audio_bytes: bytes) -> tuple[bytes, bytes, int]:
    """(telecaller_pcm16, customer_pcm16, sample_rate) from a stereo WAV."""
    decoded = decode_wav(audio_bytes)
    if not decoded or decoded[2] != 2:
        raise NotStereo("recording is not a two-channel WAV")
    pcm, rate, _ = decoded
    samples = array("h")
    samples.frombytes(pcm)
    tele = samples[TELECALLER_CHANNEL::2]
    cust = samples[1 - TELECALLER_CHANNEL::2]
    return tele.tobytes(), cust.tobytes(), rate


def _frame_levels(pcm16: bytes, sample_rate: int) -> list[float]:
    samples = array("h")
    samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    size = max(1, int(sample_rate * FRAME_SECONDS))
    return [
        sum(abs(s) for s in samples[i:i + size]) / len(samples[i:i + size])
        for i in range(0, len(samples), size)
    ]


def speech_segments(pcm16: bytes, sample_rate: int) -> list[Segment]:
    """Stretches where this track's speaker is talking, in seconds.

    The threshold adapts to the track's own quiet level, so steady line hiss
    never reads as speech.
    """
    levels = _frame_levels(pcm16, sample_rate)
    if not levels:
        return []
    floor = sorted(levels)[len(levels) // 10]
    threshold = max(SPEECH_MIN_LEVEL, floor * NOISE_FLOOR_MULTIPLIER)

    runs: list[list[float]] = []
    for i, level in enumerate(levels):
        if level < threshold:
            continue
        start, end = i * FRAME_SECONDS, (i + 1) * FRAME_SECONDS
        if runs and start - runs[-1][1] <= MERGE_GAP_S:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    return [(round(s, 2), round(e, 2)) for s, e in runs if e - s >= MIN_SPEECH_RUN_S]


def count_interruptions(telecaller: list[Segment], customer: list[Segment]) -> int:
    """Times the telecaller started talking while the customer was still speaking.

    Counted only when both talked together for OVERLAP_MIN_S and the telecaller kept
    going for TELECALLER_RUN_MIN_S — so a quick "hmm / ok" is listening, not interrupting.
    """
    count = 0
    for t_start, t_end in telecaller:
        if t_end - t_start < TELECALLER_RUN_MIN_S:
            continue
        for c_start, c_end in customer:
            if c_start < t_start < c_end and min(t_end, c_end) - t_start >= OVERLAP_MIN_S:
                count += 1
                break
    return count


def per_5_min(count: int | None, duration_s: float | None) -> float | None:
    if count is None or not duration_s:
        return None
    return round(count / (duration_s / 60) * 5, 2)
