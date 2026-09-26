"""Tests for call-recording container detection.

TeleCMI CHUB serves both .wav and .mp3. Gemini's speech-to-text takes the mime
type as an explicit argument and trusts it, so announcing a WAV as audio/mp3
hands the model a mislabelled file. These pin the detection down, including the
real filename shape seen in production CDRs.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.audio_format import detect_audio_format, detect_gemini_audio_mime

# Real filename from a production CDR (2026-09-15).
REAL_CDR_FILENAME = "1789452492960_1000010414748_5130_33337312.wav"
REAL_PLAY_URL = (
    "https://rest.telecmi.com/v2/play?appid=33337312&secret=abc-def&file=" + REAL_CDR_FILENAME
)

# Minimal valid container headers.
WAV = b"RIFF" + b"\x24\x08\x00\x00" + b"WAVEfmt " + b"\x00" * 64
MP3_ID3 = b"ID3\x04\x00\x00" + b"\x00" * 64
MP3_BARE = b"\xff\xfb\x90\x64" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
FLAC = b"fLaC\x00\x00\x00\x22" + b"\x00" * 64
M4A = b"\x00\x00\x00\x20" + b"ftypM4A " + b"\x00" * 64
AIFF = b"FORM\x00\x00\x08\x00" + b"AIFF" + b"\x00" * 64


class DetectAudioFormatTests(unittest.TestCase):
    def test_wav_is_detected_from_magic_bytes(self):
        """The case that was broken: real CHUB recordings are WAV."""
        self.assertEqual(detect_audio_format(WAV), ("wav", "audio/wav"))

    def test_mp3_is_detected_both_tagged_and_bare(self):
        self.assertEqual(detect_audio_format(MP3_ID3), ("mp3", "audio/mpeg"))
        self.assertEqual(detect_audio_format(MP3_BARE), ("mp3", "audio/mpeg"))

    def test_other_containers_are_recognised(self):
        self.assertEqual(detect_audio_format(OGG), ("ogg", "audio/ogg"))
        self.assertEqual(detect_audio_format(FLAC), ("flac", "audio/flac"))
        self.assertEqual(detect_audio_format(M4A), ("m4a", "audio/mp4"))
        self.assertEqual(detect_audio_format(AIFF), ("aiff", "audio/aiff"))

    def test_bytes_win_over_a_misleading_filename(self):
        """A .mp3 name on WAV bytes must not mislabel the audio."""
        self.assertEqual(detect_audio_format(WAV, "recording.mp3"), ("wav", "audio/wav"))

    def test_extension_is_read_from_the_play_url_query_string(self):
        """The CHUB playback URL's path is just '/v2/play' — the name is in ?file=."""
        unknown = b"\x00" * 64
        self.assertEqual(detect_audio_format(unknown, REAL_PLAY_URL), ("wav", "audio/wav"))

    def test_extension_is_read_from_a_bare_filename(self):
        unknown = b"\x00" * 64
        self.assertEqual(detect_audio_format(unknown, REAL_CDR_FILENAME), ("wav", "audio/wav"))

    def test_gemini_mime_keeps_the_live_tested_mp3_spelling(self):
        """Gemini names MP3 'audio/mp3'; 'audio/mpeg' is the HTTP type for storage.

        The endpoint trusts this string, and 'audio/mp3' is the spelling that
        was live-tested, so it must not drift to the storage type.
        """
        self.assertEqual(detect_gemini_audio_mime(MP3_ID3), "audio/mp3")
        self.assertEqual(detect_gemini_audio_mime(MP3_BARE), "audio/mp3")
        # ...while storage still gets the standard type for the same bytes.
        self.assertEqual(detect_audio_format(MP3_ID3)[1], "audio/mpeg")

    def test_gemini_mime_is_the_true_type_for_non_mp3(self):
        self.assertEqual(detect_gemini_audio_mime(WAV), "audio/wav")
        self.assertEqual(detect_gemini_audio_mime(FLAC), "audio/flac")
        self.assertEqual(detect_gemini_audio_mime(OGG), "audio/ogg")

    def test_unknown_audio_falls_back_to_mp3(self):
        """Previous behaviour assumed mp3, so an unknown container is no worse off."""
        self.assertEqual(detect_audio_format(b"\x00" * 64), ("mp3", "audio/mpeg"))
        self.assertEqual(detect_audio_format(b"\x00" * 64, "https://x.test/v2/play"), ("mp3", "audio/mpeg"))

    def test_short_and_empty_payloads_do_not_raise(self):
        for payload in (b"", b"RI", b"RIFF"):
            self.assertEqual(detect_audio_format(payload), ("mp3", "audio/mpeg"))
        # A truncated body still honours a usable filename hint.
        self.assertEqual(detect_audio_format(b"RI", REAL_CDR_FILENAME), ("wav", "audio/wav"))


class RecordingPipelineWiringTests(unittest.TestCase):
    """The detector is only useful if both consumers actually call it."""

    def _read(self, path):
        return (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")

    def test_storage_upload_uses_the_detected_type(self):
        source = self._read("app/services/call_ai_pipeline.py")
        self.assertIn('extension, content_type = detect_audio_format(audio, row["recording_filename"])', source)
        self.assertIn("storage_path = f\"{row['id']}.{extension}\"", source)
        self.assertIn('{"content-type": content_type, "upsert": "true"}', source)
        # The old hardcoded assumptions must not come back.
        self.assertNotIn(".mp3\"", source)
        self.assertNotIn('{"content-type": "audio/mpeg", "upsert": "true"}', source)

    def test_transcription_sends_the_detected_mime_type(self):
        source = self._read("app/services/call_ai_pipeline.py")
        self.assertIn('detect_gemini_audio_mime(audio, row["recording_url"])', source)
        self.assertIn('detect_gemini_audio_mime(audio, row["recording_filename"])', source)
        self.assertIn("transcribe_tracks(audio, mime_type", source)
        self.assertNotIn('"audio/mp3"', source)

if __name__ == "__main__":
    unittest.main()
