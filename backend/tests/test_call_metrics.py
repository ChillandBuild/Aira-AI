"""Transcript lines, talk share by words, and the level caps from the method document."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_lines import Line, clock, format_transcript, parse_transcript
from app.services import call_metrics as cm


def _words(n: int, word: str = "word") -> str:
    return " ".join([word] * n)


class LineFormatTests(unittest.TestCase):
    def test_round_trip(self):
        lines = [Line(72.4, "customer", "We have two branches actually."), Line(75.0, "telecaller", "Okay sir.")]
        text = format_transcript(lines)
        self.assertEqual(text.splitlines()[0], "[01:12] Customer: We have two branches actually.")
        self.assertEqual(parse_transcript(text), [Line(72.0, "customer", "We have two branches actually."), Line(75.0, "telecaller", "Okay sir.")])

    def test_legacy_lines_without_time(self):
        self.assertEqual(parse_transcript("Telecaller: Hello."), [Line(0.0, "telecaller", "Hello.")])

    def test_clock(self):
        self.assertEqual(clock(0), "00:00")
        self.assertEqual(clock(160.9), "02:40")


class TalkShareTests(unittest.TestCase):
    def test_document_example_65(self):
        lines = [Line(0, "telecaller", _words(650)), Line(1, "customer", _words(350))]
        self.assertEqual(cm.talk_share(lines), 65.0)

    def test_fillers_ignored(self):
        lines = [Line(0, "telecaller", _words(30) + " hmm uh aah"), Line(1, "customer", _words(30)), Line(2, "customer", "ok ok")]
        self.assertEqual(cm.talk_share(lines), 50.0)

    def test_tamil_words_count_as_words(self):
        lines = [Line(0, "telecaller", "சரி சார் நான் அனுப்புறேன் " * 10), Line(1, "customer", "ok thanks " * 10)]
        self.assertAlmostEqual(cm.talk_share(lines), 66.67, places=2)

    def test_under_50_words_is_none(self):
        self.assertIsNone(cm.talk_share([Line(0, "telecaller", _words(20)), Line(1, "customer", _words(20))]))


class CapTests(unittest.TestCase):
    def test_listening_caps(self):
        self.assertEqual(cm.listening_cap(64, 0.5), "excellent")
        self.assertEqual(cm.listening_cap(64, 1.25), "good")      # document full example
        self.assertEqual(cm.listening_cap(70, 0.5), "good")
        self.assertEqual(cm.listening_cap(80, 0.5), "partial")
        self.assertEqual(cm.listening_cap(60, 4), "partial")
        self.assertEqual(cm.listening_cap(80, 4), "poor")
        self.assertEqual(cm.listening_cap(None, None), "excellent")

    def test_courtesy_cap(self):
        self.assertEqual(cm.courtesy_cap(3), "excellent")
        self.assertEqual(cm.courtesy_cap(3.5), "good")
        self.assertEqual(cm.courtesy_cap(None), "excellent")

    def test_lower_level(self):
        self.assertEqual(cm.lower_level("excellent", "good"), "good")
        self.assertEqual(cm.lower_level("poor", "good"), "poor")

    def test_tips(self):
        self.assertEqual(cm.tips(60, 0.5), [])
        self.assertIn("Let the customer speak more. Aim to talk less than 65% of the time.", cm.tips(72, 0.5))
        self.assertIn("Let the customer finish before you reply.", cm.tips(60, 2))
        self.assertIn("Guide the conversation more: ask questions and explain the next step.", cm.tips(25, 0))


if __name__ == "__main__":
    unittest.main()
