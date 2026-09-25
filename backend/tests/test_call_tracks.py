"""Two-track audio analysis: stereo split, speech segments, interruptions."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_tracks as ct

RATE = 8000


def _tone(seconds: float, level: int) -> list[int]:
    n = int(seconds * RATE)
    return [level if i % 2 else -level for i in range(n)]


def _wav(left: list[int], right: list[int] | None = None) -> bytes:
    channels = 1 if right is None else 2
    if right is None:
        samples = left
    else:
        samples = [s for pair in zip(left, right) for s in pair]
    data = struct.pack(f"<{len(samples)}h", *samples)
    fmt = struct.pack("<HHIIHH", 1, channels, RATE, RATE * 2 * channels, 2 * channels, 16)
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data


def _pcm(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


class SplitStereoTests(unittest.TestCase):
    def test_right_channel_is_telecaller(self):
        left = _tone(1, 100)
        right = _tone(1, 2000)
        tele, cust, rate = ct.split_stereo(_wav(left, right))
        self.assertEqual(rate, RATE)
        self.assertEqual(struct.unpack_from("<h", tele, 2)[0], 2000)
        self.assertEqual(struct.unpack_from("<h", cust, 2)[0], 100)

    def test_mono_raises_not_stereo(self):
        with self.assertRaises(ct.NotStereo):
            ct.split_stereo(_wav(_tone(1, 100)))

    def test_non_wav_raises_not_stereo(self):
        with self.assertRaises(ct.NotStereo):
            ct.split_stereo(b"ID3not-a-wav")


class SpeechSegmentTests(unittest.TestCase):
    def test_finds_speech_between_silence(self):
        samples = _tone(1, 5) + _tone(2, 3000) + _tone(1, 5)
        segs = ct.speech_segments(_pcm(samples), RATE)
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0][0], 1.0, delta=0.11)
        self.assertAlmostEqual(segs[0][1], 3.0, delta=0.11)

    def test_steady_hiss_is_not_speech(self):
        samples = _tone(5, 400)
        self.assertEqual(ct.speech_segments(_pcm(samples), RATE), [])

    def test_speech_over_hiss_is_found(self):
        samples = _tone(2, 400) + _tone(1, 4000) + _tone(2, 400)
        segs = ct.speech_segments(_pcm(samples), RATE)
        self.assertEqual(len(segs), 1)

    def test_short_gap_is_merged(self):
        samples = _tone(1, 3000) + _tone(0.2, 5) + _tone(1, 3000) + _tone(1, 5)
        self.assertEqual(len(ct.speech_segments(_pcm(samples), RATE)), 1)

    def test_empty_audio(self):
        self.assertEqual(ct.speech_segments(b"", RATE), [])


class InterruptionTests(unittest.TestCase):
    def test_counts_long_overlap_while_customer_speaks(self):
        self.assertEqual(ct.count_interruptions([(3.0, 6.0)], [(0.0, 5.0)]), 1)

    def test_short_overlap_not_counted(self):
        self.assertEqual(ct.count_interruptions([(4.5, 8.0)], [(0.0, 5.0)]), 0)

    def test_backchannel_not_counted(self):
        # telecaller says "hmm" for 0.6s inside the customer's turn
        self.assertEqual(ct.count_interruptions([(2.0, 2.6)], [(0.0, 5.0)]), 0)

    def test_customer_interrupting_telecaller_not_counted(self):
        self.assertEqual(ct.count_interruptions([(0.0, 5.0)], [(3.0, 6.0)]), 0)

    def test_no_segments(self):
        self.assertEqual(ct.count_interruptions([], []), 0)

    def test_per_5_min(self):
        self.assertEqual(ct.per_5_min(4, 600), 2.0)
        self.assertIsNone(ct.per_5_min(None, 600))
        self.assertIsNone(ct.per_5_min(2, 0))


if __name__ == "__main__":
    unittest.main()
