"""Per-track transcription: certain speakers, times from the audio, mono fallback."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_transcribe as tr
from app.services.call_audio import AudioChunk
from app.services.call_lines import Line
from app.services.call_tracks import NotStereo


class ParseTrackTextTests(unittest.TestCase):
    def test_times_are_offset_by_piece_start(self):
        lines = tr.parse_track_text("[00:05] Hello sir\n[01:10] Thank you", "telecaller", offset=300.0)
        self.assertEqual(lines, [Line(305.0, "telecaller", "Hello sir"), Line(370.0, "telecaller", "Thank you")])

    def test_untimed_text_kept_at_offset(self):
        self.assertEqual(tr.parse_track_text("Hello", "customer", 0.0), [Line(0.0, "customer", "Hello")])

    def test_blank_lines_skipped(self):
        self.assertEqual(tr.parse_track_text("\n\n", "customer", 0.0), [])


class SnapTests(unittest.TestCase):
    def test_snaps_to_nearest_segment_start_within_window(self):
        lines = [Line(10.0, "telecaller", "a")]
        self.assertEqual(tr.snap(lines, [(8.4, 12.0), (30.0, 31.0)])[0].start, 8.4)

    def test_keeps_ai_time_when_nothing_close(self):
        lines = [Line(10.0, "telecaller", "a")]
        self.assertEqual(tr.snap(lines, [(30.0, 31.0)])[0].start, 10.0)


class SwappedTracksTests(unittest.TestCase):
    def test_company_name_only_on_customer_track(self):
        lines = [Line(0, "customer", "Hello, I'm calling from Aira Softwares"), Line(3, "telecaller", "Yes tell me")]
        self.assertTrue(tr.tracks_look_swapped(lines, "Aira Softwares"))

    def test_normal_call_not_swapped(self):
        lines = [Line(0, "telecaller", "Calling from Aira Softwares"), Line(3, "customer", "Yes")]
        self.assertFalse(tr.tracks_look_swapped(lines, "Aira Softwares"))

    def test_no_clues_anywhere_not_swapped(self):
        self.assertFalse(tr.tracks_look_swapped([Line(0, "telecaller", "hello")], None))


class TranscribeTracksTests(unittest.IsolatedAsyncioTestCase):
    async def test_stereo_merges_both_tracks_in_time_order(self):
        async def fake(data, mime, prompt, **kw):
            return ("[00:02] Hello" if data == b"T" else "[00:01] Who is this?\n[00:05] Okay"), True

        with patch.object(tr, "split_stereo", return_value=(b"tele", b"cust", 8000)), \
             patch.object(tr, "speech_segments", return_value=[]), \
             patch.object(tr, "split_pcm", side_effect=lambda pcm, r, c: [AudioChunk(b"T" if pcm == b"tele" else b"C", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "gemini_transcribe_audio", AsyncMock(side_effect=fake)):
            result = await tr.transcribe_tracks(b"wav", "audio/wav", tenant_id="t")
        self.assertTrue(result.stereo)
        self.assertEqual([(l.start, l.speaker) for l in result.lines], [(1.0, "customer"), (2.0, "telecaller"), (5.0, "customer")])

    async def test_mono_falls_back_to_labelled_single_pass(self):
        gemini = AsyncMock(return_value=("[00:01] Telecaller: Calling from Aira\n[00:04] Customer: Yes", True))
        with patch.object(tr, "split_stereo", side_effect=NotStereo("mono")), \
             patch.object(tr, "split_audio", return_value=[AudioChunk(b"M", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "gemini_transcribe_audio", gemini):
            result = await tr.transcribe_tracks(b"mp3", "audio/mpeg", tenant_id="t")
        self.assertFalse(result.stereo)
        self.assertEqual([l.speaker for l in result.lines], ["telecaller", "customer"])
        self.assertIn("company name", gemini.call_args.args[2])

    async def test_cut_off_piece_that_cannot_split_raises(self):
        with patch.object(tr, "split_stereo", return_value=(b"tele", b"cust", 8000)), \
             patch.object(tr, "speech_segments", return_value=[]), \
             patch.object(tr, "split_pcm", return_value=[AudioChunk(b"T", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "resplit_chunk", return_value=None), \
             patch.object(tr, "gemini_transcribe_audio", AsyncMock(return_value=("[00:01] Hel", False))):
            with self.assertRaises(tr.TranscriptionIncomplete):
                await tr.transcribe_tracks(b"wav", "audio/wav", tenant_id="t")


if __name__ == "__main__":
    unittest.main()
