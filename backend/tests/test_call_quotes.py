"""An AI quote only counts if it's really in the transcript, from the right person."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_lines import Line
from app.services.call_quotes import clip, find_quote

LINES = [
    Line(5.0, "telecaller", "Our plan includes GST billing and stock tracking."),
    Line(12.0, "customer", "How much is the yearly plan?"),
    Line(20.0, "customer", "ஸ்கோரிங் இப்பதான் நான் அந்த டூல் காலிங் மட்டும் பண்ற மாதிரி"),
]


class FindQuoteTests(unittest.TestCase):
    def test_exact_substring(self):
        self.assertEqual(find_quote("How much is the yearly plan", LINES).start, 12.0)

    def test_punctuation_and_case_ignored(self):
        self.assertEqual(find_quote("our plan includes GST billing, and stock tracking", LINES).start, 5.0)

    def test_fabricated_quote_rejected(self):
        self.assertIsNone(find_quote("We offer a free trial for 30 days", LINES))

    def test_wrong_speaker_rejected(self):
        self.assertIsNone(find_quote("How much is the yearly plan", LINES, speakers=("telecaller",)))

    def test_small_spelling_difference_tolerated(self):
        self.assertEqual(find_quote("ஸ்கோரிங் இப்ப தான் நான் அந்த டூல் காலிங் மட்டும்", LINES).start, 20.0)

    def test_empty_quote(self):
        self.assertIsNone(find_quote("", LINES))
        self.assertIsNone(find_quote(None, LINES))

    def test_clip(self):
        self.assertEqual(len(clip("x" * 500)), 240)
        self.assertIsNone(clip(None))


if __name__ == "__main__":
    unittest.main()
