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

    def test_negation_flip_rejected(self):
        """Quote flips meaning: 'no' vs 'an' charge."""
        line = Line(1.0, "telecaller", "Sir there is no extra charge for downloading the report anytime you like")
        quote = "there is an extra charge for downloading the report anytime"
        self.assertIsNone(find_quote(quote, [line]))

    def test_long_word_misspelling_tolerated(self):
        """'installation' vs 'instalation' (missing 'l') should match."""
        line = Line(1.0, "telecaller", "We provide installation support for every customer")
        quote = "We provide instalation support for every customer"
        self.assertEqual(find_quote(quote, [line]).start, 1.0)

    def test_short_word_swap_rejected(self):
        """Short word swap: 'not' vs 'now' should not match."""
        line = Line(1.0, "telecaller", "The plan is not refundable")
        quote = "The plan is now refundable"
        self.assertIsNone(find_quote(quote, [line]))

    def test_non_string_quote_rejected(self):
        """Non-string quotes are rejected, not converted."""
        self.assertIsNone(find_quote(12345, LINES))
        self.assertIsNone(find_quote(["x"], LINES))

    def test_clip_non_string(self):
        """clip returns None for non-string inputs."""
        self.assertIsNone(clip(5))
        self.assertIsNone(clip(["text"]))


if __name__ == "__main__":
    unittest.main()
