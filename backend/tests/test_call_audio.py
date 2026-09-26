"""Splitting call recordings so long calls are transcribed completely."""
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_audio as ca

RATE = 8000


def _wav(samples: bytes, audio_format: int, bits: int, channels: int = 1, rate: int = RATE) -> bytes:
    block = channels * bits // 8
    fmt = struct.pack("<HHIIHH", audio_format, channels, rate, rate * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(samples)) + samples
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _tone_pcm(seconds: float, rate: int = RATE) -> bytes:
    return b"".join(struct.pack("<h", int(6000 * math.sin(i / 9))) for i in range(int(seconds * rate)))


class CompandingTests(unittest.TestCase):
    def test_mu_law_reference_values(self):
        self.assertEqual(ca._ulaw_to_linear(0xFF), 0)
        self.assertEqual(ca._ulaw_to_linear(0x00), -32124)
        self.assertEqual(ca._ulaw_to_linear(0x80), 32124)

    def test_a_law_reference_values(self):
        self.assertEqual(ca._alaw_to_linear(0xD5), 8)
        self.assertEqual(ca._alaw_to_linear(0x55), -8)


class WavTests(unittest.TestCase):
    def test_mu_law_telephony_wav_decodes_to_pcm16(self):
        decoded = ca._decode_wav(_wav(bytes([0xFF, 0x00, 0x80]), 7, 8))
        pcm, rate, channels = decoded
        self.assertEqual((rate, channels), (RATE, 1))
        self.assertEqual(struct.unpack("<3h", pcm), (0, -32124, 32124))

    def test_a_law_and_8bit_pcm_decode(self):
        self.assertIsNotNone(ca._decode_wav(_wav(bytes(100), 6, 8)))
        pcm, _, _ = ca._decode_wav(_wav(bytes([128, 255]), 1, 8))
        self.assertEqual(struct.unpack("<2h", pcm), (0, 127 << 8))

    def test_unsupported_wav_returns_none(self):
        self.assertIsNone(ca._decode_wav(_wav(bytes(100), 2, 4)))
        self.assertIsNone(ca._decode_wav(b"not a wav"))

    def test_short_wav_is_one_piece_reencoded_as_mp3(self):
        chunks = ca.split_audio(_wav(_tone_pcm(90), 1, 16), "audio/wav")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].mime_type, "audio/mpeg")
        self.assertAlmostEqual(chunks[0].end_seconds, 90, delta=0.1)

    def test_twelve_minute_wav_splits_into_five_minute_pieces_in_order(self):
        ulaw = bytes((i * 7) & 0xFF for i in range(RATE * 12 * 60))
        wav = _wav(ulaw, 7, 8)
        chunks = ca.split_audio(wav, "audio/wav")
        self.assertEqual([(round(c.start_seconds), round(c.end_seconds)) for c in chunks], [(0, 300), (300, 600), (600, 720)])
        self.assertLess(sum(len(c.data) for c in chunks), len(wav))


class Mp3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.long_mp3 = ca._encode_mp3(_tone_pcm(11 * 60), RATE, 1)

    def test_frames_cover_the_real_duration(self):
        frames = ca._mp3_frames(self.long_mp3)
        self.assertAlmostEqual(sum(f[2] for f in frames), 660, delta=1)

    def test_long_mp3_is_cut_on_frame_boundaries(self):
        chunks = ca.split_audio(self.long_mp3, "audio/mpeg")
        self.assertEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertIsNotNone(ca._mp3_frames(chunk.data), "every piece must be a valid MP3")
        self.assertEqual(b"".join(c.data for c in chunks), self.long_mp3[ca._mp3_frames(self.long_mp3)[0][0]:])

    def test_short_mp3_passes_through_untouched(self):
        short = ca._encode_mp3(_tone_pcm(60), RATE, 1)
        chunks = ca.split_audio(short, "audio/mpeg")
        self.assertEqual(len(chunks), 1)
        self.assertIs(chunks[0].data, short)

    def test_oversized_mp3_is_split_by_bytes_even_when_short(self):
        short = ca._encode_mp3(_tone_pcm(120), RATE, 1)
        original = ca.MAX_INLINE_BYTES
        ca.MAX_INLINE_BYTES = len(short) // 3
        try:
            chunks = ca.split_audio(short, "audio/mpeg")
        finally:
            ca.MAX_INLINE_BYTES = original
        self.assertGreaterEqual(len(chunks), 3)

    def test_resplit_halves_a_piece_and_keeps_absolute_times(self):
        piece = ca.split_audio(self.long_mp3, "audio/mpeg")[1]
        halves = ca.resplit_chunk(piece)
        self.assertEqual(len(halves), 2)
        self.assertAlmostEqual(halves[0].start_seconds, 300, delta=1)
        self.assertAlmostEqual(halves[1].end_seconds, 600, delta=1)

    def test_resplit_refuses_below_the_minimum_piece(self):
        piece = ca.split_audio(ca._encode_mp3(_tone_pcm(100), RATE, 1), "audio/mpeg")[0]
        self.assertIsNone(ca.resplit_chunk(piece))


class FallbackTests(unittest.TestCase):
    def test_unknown_format_is_sent_whole(self):
        blob = b"OggS" + bytes(5000)
        chunks = ca.split_audio(blob, "audio/ogg")
        self.assertEqual(len(chunks), 1)
        self.assertIs(chunks[0].data, blob)
        self.assertIsNone(ca.resplit_chunk(chunks[0]))


if __name__ == "__main__":
    unittest.main()
