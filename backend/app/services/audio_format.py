"""Audio container detection for call recordings.

TeleCMI CHUB does not commit to one container: the docs show both .mp3 and
.wav, and real CDRs observed in production carry .wav filenames
(`1789452492960_1000010414748_5130_33337312.wav`). Everything downstream has to
agree on the actual format — Supabase storage needs the right content type, and
Gemini's speech-to-text takes the mime type as an explicit argument and trusts
it, so a WAV announced as audio/mp3 is handed to the model mislabelled.

Sniffing the bytes rather than trusting the filename means a provider switching
container (or serving .wav behind an .mp3 name) can't silently break
transcription.
"""
import logging
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# (extension, mime_type) — mime types are the ones Gemini's audio input accepts.
_WAV = ("wav", "audio/wav")
_MP3 = ("mp3", "audio/mpeg")
_OGG = ("ogg", "audio/ogg")
_FLAC = ("flac", "audio/flac")
_M4A = ("m4a", "audio/mp4")
_AIFF = ("aiff", "audio/aiff")

DEFAULT_FORMAT = _MP3

# Gemini names MP3 "audio/mp3" rather than the standard HTTP "audio/mpeg", and
# that exact string is the one live-tested against the interactions endpoint
# (see gemini_client.gemini_speech_to_text). Storage keeps the standard type;
# only the model call gets this spelling, and only where the two differ.
_GEMINI_MIME_OVERRIDES = {"mp3": "audio/mp3"}

_EXTENSION_MAP = {
    "wav": _WAV, "wave": _WAV,
    "mp3": _MP3, "mpeg": _MP3, "mpga": _MP3,
    "ogg": _OGG, "oga": _OGG,
    "flac": _FLAC,
    "m4a": _M4A, "mp4": _M4A, "aac": _M4A,
    "aif": _AIFF, "aiff": _AIFF,
}


def _sniff(data: bytes) -> tuple[str, str] | None:
    """Identify the container from its magic bytes, or None if unrecognised."""
    if len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return _WAV
    if data[:4] == b"FORM" and data[8:12] in (b"AIFF", b"AIFC"):
        return _AIFF
    if data[:4] == b"OggS":
        return _OGG
    if data[:4] == b"fLaC":
        return _FLAC
    if data[4:8] == b"ftyp":
        return _M4A
    # ID3-tagged mp3, or a bare MPEG audio frame sync (11 set bits).
    if data[:3] == b"ID3":
        return _MP3
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return _MP3
    return None


def _hint_candidates(filename_hint: str | None) -> list[str]:
    """Names worth reading an extension from, best first.

    The CHUB playback URL keeps the real filename in the query string
    (`/v2/play?appid=…&secret=…&file=rec.wav`), so the path alone is just
    "play" — the query has to be checked first, otherwise a plain bare
    filename is all this could ever handle.
    """
    if not filename_hint:
        return []
    parsed = urlparse(filename_hint)
    candidates = [v for v in parse_qs(parsed.query).get("file", []) if v]
    tail = (parsed.path or filename_hint).rsplit("/", 1)[-1]
    if tail:
        candidates.append(tail)
    return [c for c in candidates if "." in c]


def detect_audio_format(data: bytes, filename_hint: str | None = None) -> tuple[str, str]:
    """Return (extension, mime_type) for `data`.

    Magic bytes win. Falls back to the extension in `filename_hint` (a CDR
    filename or a URL), then to mp3 — matching what this code assumed before
    any detection existed, so an unrecognised container is no worse off.
    """
    sniffed = _sniff(data)
    if sniffed:
        return sniffed

    for candidate in _hint_candidates(filename_hint):
        by_extension = _EXTENSION_MAP.get(candidate.rsplit(".", 1)[-1].strip().lower())
        if by_extension:
            logger.info(
                f"Audio format not recognised from bytes; using the {by_extension[0]} "
                f"extension from {candidate}"
            )
            return by_extension

    logger.warning(
        f"Could not determine audio format (first bytes: {data[:12]!r}, hint: {filename_hint!r}) "
        f"— defaulting to {DEFAULT_FORMAT[1]}"
    )
    return DEFAULT_FORMAT


def detect_gemini_audio_mime(data: bytes, filename_hint: str | None = None) -> str:
    """Mime type to hand Gemini's speech-to-text for `data`.

    Same detection as `detect_audio_format`, but spelled the way Gemini names
    the format. It takes this argument on trust, so it has to be both accurate
    about the container and a spelling the endpoint accepts.
    """
    extension, content_type = detect_audio_format(data, filename_hint)
    return _GEMINI_MIME_OVERRIDES.get(extension, content_type)
