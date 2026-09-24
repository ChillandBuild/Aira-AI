"""Split call recordings into pieces Gemini can transcribe completely.

A single transcription request has two hard ceilings: the inline request size
(Gemini rejects payloads past ~20MB, and base64 inflates audio by a third) and
the output-token cap (a long Tamil call runs past it and comes back cut off).
Long recordings are therefore cut into ~5 minute pieces. WAV (TeleCMI's usual
container, often 8kHz mu-law) is decoded to PCM and re-encoded as small mono/
stereo MP3s; MP3 is cut on frame boundaries so every piece is a valid file.
Anything unrecognised is passed through whole, exactly as before.
"""
import logging
import struct
from array import array
from dataclasses import dataclass

import lameenc

logger = logging.getLogger(__name__)

SINGLE_PASS_SECONDS = 8 * 60
CHUNK_SECONDS = 5 * 60
MIN_CHUNK_SECONDS = 60
MAX_INLINE_BYTES = 12 * 1024 * 1024


@dataclass
class AudioChunk:
    data: bytes
    mime_type: str
    start_seconds: float
    end_seconds: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


# ── WAV ──────────────────────────────────────────────────────────────

def _ulaw_to_linear(u: int) -> int:
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def _alaw_to_linear(a: int) -> int:
    a ^= 0x55
    sign = a & 0x80
    exponent = (a >> 4) & 0x07
    mantissa = a & 0x0F
    if exponent == 0:
        sample = (mantissa << 4) + 8
    else:
        sample = ((mantissa << 4) + 0x108) << (exponent - 1)
    return sample if sign else -sample


def _companded_tables(decode) -> tuple[bytes, bytes]:
    lo = bytearray(256)
    hi = bytearray(256)
    for i in range(256):
        v = decode(i) & 0xFFFF
        lo[i] = v & 0xFF
        hi[i] = v >> 8
    return bytes(lo), bytes(hi)


_ULAW_LO, _ULAW_HI = _companded_tables(_ulaw_to_linear)
_ALAW_LO, _ALAW_HI = _companded_tables(_alaw_to_linear)


def _expand_8bit(data: bytes, lo_table: bytes, hi_table: bytes) -> bytes:
    out = bytearray(len(data) * 2)
    out[0::2] = data.translate(lo_table)
    out[1::2] = data.translate(hi_table)
    return bytes(out)


def _decode_wav(data: bytes) -> tuple[bytes, int, int] | None:
    """Return (interleaved PCM16 little-endian, sample_rate, channels), or None."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos = 12
    fmt: tuple | None = None
    samples: bytes | None = None
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body_start = pos + 8
        body_end = len(data) if size in (0, 0xFFFFFFFF) and chunk_id == b"data" else min(len(data), body_start + size)
        if chunk_id == b"fmt " and body_end - body_start >= 16:
            audio_format, channels, sample_rate, _byte_rate, _align, bits = struct.unpack_from("<HHIIHH", data, body_start)
            if audio_format == 0xFFFE and body_end - body_start >= 26:
                audio_format = struct.unpack_from("<H", data, body_start + 24)[0]
            fmt = (audio_format, channels, sample_rate, bits)
        elif chunk_id == b"data":
            samples = data[body_start:body_end]
            break
        pos = body_start + size + (size & 1)
    if not fmt or samples is None:
        return None
    audio_format, channels, sample_rate, bits = fmt
    if channels not in (1, 2) or sample_rate <= 0:
        return None

    if audio_format == 7 and bits == 8:
        pcm = _expand_8bit(samples, _ULAW_LO, _ULAW_HI)
    elif audio_format == 6 and bits == 8:
        pcm = _expand_8bit(samples, _ALAW_LO, _ALAW_HI)
    elif audio_format == 1 and bits == 16:
        pcm = samples[: len(samples) - (len(samples) % 2)]
    elif audio_format == 1 and bits == 8:
        pcm = _expand_8bit(samples, bytes(256), bytes(((i - 128) & 0xFF) for i in range(256)))
    elif audio_format == 1 and bits in (24, 32):
        width = bits // 8
        usable = len(samples) - (len(samples) % width)
        out = bytearray(usable // width * 2)
        out[0::2] = samples[width - 2:usable:width]
        out[1::2] = samples[width - 1:usable:width]
        pcm = bytes(out)
    elif audio_format == 3 and bits == 32:
        floats = array("f")
        floats.frombytes(samples[: len(samples) - (len(samples) % 4)])
        pcm = array("h", (max(-32768, min(32767, int(f * 32767))) for f in floats)).tobytes()
    else:
        return None
    frame_bytes = 2 * channels
    return pcm[: len(pcm) - (len(pcm) % frame_bytes)], sample_rate, channels


def _encode_mp3(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(32 if channels == 1 else 48)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(5)
    return bytes(encoder.encode(pcm) + encoder.flush())


def _split_wav(pcm: bytes, sample_rate: int, channels: int, max_chunk_seconds: float) -> list[AudioChunk]:
    frame_bytes = 2 * channels
    total_seconds = len(pcm) / (sample_rate * frame_bytes)
    piece_seconds = total_seconds if total_seconds <= max_chunk_seconds else max_chunk_seconds
    step = max(frame_bytes, int(piece_seconds * sample_rate) * frame_bytes)
    chunks = []
    for offset in range(0, len(pcm), step):
        piece = pcm[offset:offset + step]
        start = offset / (sample_rate * frame_bytes)
        chunks.append(AudioChunk(
            data=_encode_mp3(piece, sample_rate, channels),
            mime_type="audio/mpeg",
            start_seconds=start,
            end_seconds=start + len(piece) / (sample_rate * frame_bytes),
        ))
    return chunks


# ── MP3 ──────────────────────────────────────────────────────────────

_MP3_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3_frame_at(data: bytes, pos: int) -> tuple[int, int, int] | None:
    """Return (frame_length, samples_per_frame, sample_rate) for a Layer III header at pos."""
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    version_bits = (data[pos + 1] >> 3) & 0x03
    layer_bits = (data[pos + 1] >> 1) & 0x03
    bitrate_index = (data[pos + 2] >> 4) & 0x0F
    rate_index = (data[pos + 2] >> 2) & 0x03
    padding = (data[pos + 2] >> 1) & 0x01
    if version_bits == 1 or layer_bits != 1 or bitrate_index in (0, 15) or rate_index == 3:
        return None
    mpeg1 = version_bits == 3
    bitrate = _MP3_BITRATES[1 if mpeg1 else 2][bitrate_index] * 1000
    sample_rate = _MP3_SAMPLE_RATES[version_bits][rate_index]
    coefficient = 144 if mpeg1 else 72
    length = coefficient * bitrate // sample_rate + padding
    return (length, 1152 if mpeg1 else 576, sample_rate) if length > 4 else None


def _mp3_frames(data: bytes) -> list[tuple[int, int, float]] | None:
    """Return [(offset, length, seconds)] for every frame, or None if this isn't a clean MP3."""
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        pos = 10 + size + (10 if data[5] & 0x10 else 0)
    frames: list[tuple[int, int, float]] = []
    covered = 0
    while pos < len(data):
        frame = _mp3_frame_at(data, pos)
        if frame and pos + frame[0] <= len(data):
            length, samples, rate = frame
            frames.append((pos, length, samples / rate))
            covered += length
            pos += length
        else:
            pos += 1
    if not frames or covered < len(data) * 0.5:
        return None
    return frames


def _split_mp3(data: bytes, frames: list[tuple[int, int, float]], max_chunk_seconds: float) -> list[AudioChunk]:
    chunks: list[AudioChunk] = []
    group_start = 0
    group_seconds = 0.0
    elapsed = 0.0
    for i, (offset, length, seconds) in enumerate(frames):
        group_bytes = offset + length - frames[group_start][0]
        if i > group_start and (group_seconds + seconds > max_chunk_seconds or group_bytes > MAX_INLINE_BYTES):
            first, last = frames[group_start], frames[i - 1]
            chunks.append(AudioChunk(data[first[0]:last[0] + last[1]], "audio/mpeg", elapsed, elapsed + group_seconds))
            elapsed += group_seconds
            group_start, group_seconds = i, 0.0
        group_seconds += seconds
    first, last = frames[group_start], frames[-1]
    chunks.append(AudioChunk(data[first[0]:last[0] + last[1]], "audio/mpeg", elapsed, elapsed + group_seconds))
    return chunks


# ── Public API ───────────────────────────────────────────────────────

def split_audio(audio_bytes: bytes, mime_type: str, max_chunk_seconds: float = CHUNK_SECONDS) -> list[AudioChunk]:
    """Cut a recording into transcribable pieces, in order.

    A recording short enough for one pass (and small enough for one request)
    comes back as a single piece. WAV is always re-encoded to MP3 because it is
    ~10x larger for the same audio.
    """
    try:
        decoded = _decode_wav(audio_bytes)
        if decoded:
            pcm, rate, channels = decoded
            total = len(pcm) / (rate * 2 * channels)
            limit = max_chunk_seconds if total > SINGLE_PASS_SECONDS or max_chunk_seconds < CHUNK_SECONDS else total
            return _split_wav(pcm, rate, channels, max(limit, 1))

        frames = _mp3_frames(audio_bytes)
        if frames:
            total = sum(f[2] for f in frames)
            fits = total <= SINGLE_PASS_SECONDS and len(audio_bytes) <= MAX_INLINE_BYTES
            if fits and max_chunk_seconds >= CHUNK_SECONDS:
                return [AudioChunk(audio_bytes, "audio/mpeg", 0.0, total)]
            return _split_mp3(audio_bytes, frames, max_chunk_seconds)
    except Exception as e:
        logger.warning(f"call_audio: could not split {mime_type} recording ({type(e).__name__}: {e}); sending whole")
    return [AudioChunk(audio_bytes, mime_type, 0.0, 0.0)]


def resplit_chunk(chunk: AudioChunk) -> list[AudioChunk] | None:
    """Halve a piece whose transcript came back cut off. None when it can't be cut smaller."""
    if chunk.duration and chunk.duration / 2 < MIN_CHUNK_SECONDS:
        return None
    half = (chunk.duration or 0) / 2
    if not half:
        return None
    pieces = split_audio(chunk.data, chunk.mime_type, max_chunk_seconds=half)
    if len(pieces) < 2:
        return None
    for piece in pieces:
        piece.start_seconds += chunk.start_seconds
        piece.end_seconds += chunk.start_seconds
    return pieces


def audio_for_evaluation(chunks: list[AudioChunk]) -> list[AudioChunk]:
    """The leading pieces that fit in one request, for the tone criterion."""
    picked: list[AudioChunk] = []
    total = 0
    for chunk in chunks:
        if total + len(chunk.data) > MAX_INLINE_BYTES:
            break
        picked.append(chunk)
        total += len(chunk.data)
    return picked
