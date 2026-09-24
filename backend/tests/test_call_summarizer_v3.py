"""Speaker-labelled chunked transcription and the v3 selectable-criteria evaluation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_summarizer as cs
from app.services.call_audio import AudioChunk
from app.services.gemini_client import _hit_output_cap


def _model_json(criteria, **overrides):
    data = {k: 8 for k in criteria}
    data.update({f"{k}_reason": "ok" for k in criteria})
    data.update({
        "brief": "Discussed fees.",
        "next_action": "Send brochure",
        "real_conversation": True,
        "detected_outcome": "interested",
        "acceptable_outcomes": ["interested", "callback", "bogus"],
        "closing_move": 7,
        "closing_move_reason": "Fixed a demo time.",
        "coaching_tip": "Ask about budget earlier.",
    })
    data.update(overrides)
    return data


class CriteriaTests(unittest.TestCase):
    def test_eight_criteria_including_tone(self):
        self.assertEqual(len(cs.DEFAULT_CRITERIA), 8)
        self.assertIn("tone", cs.DEFAULT_CRITERIA)

    def test_normalize_keeps_canonical_order_and_drops_unknowns(self):
        self.assertEqual(cs.normalize_criteria(["tone", "nonsense", "greeting_quality", "tone"]), ["greeting_quality", "tone"])
        self.assertEqual(cs.normalize_criteria([]), [])
        self.assertEqual(cs.normalize_criteria(None), [])

    def test_engagement_judges_the_telecaller_not_the_customer(self):
        self.assertIn("not how interested the customer was", cs.SCORE_CRITERIA["conversation_engagement"][1])


class BuildEvaluationTests(unittest.TestCase):
    def test_average_is_over_selected_criteria_only(self):
        evaluation = cs.build_evaluation(_model_json(["greeting_quality", "tone"], tone=6), ["greeting_quality", "tone"])
        self.assertEqual(evaluation["ai_average"], 7.0)
        self.assertEqual(evaluation["criteria"], ["greeting_quality", "tone"])
        self.assertEqual(evaluation["evaluation_version"], 3)
        self.assertNotIn("professionalism", evaluation)

    def test_scores_are_clamped_to_0_10_and_zero_is_allowed(self):
        evaluation = cs.build_evaluation(_model_json(["greeting_quality", "tone"], greeting_quality=0, tone=14), ["greeting_quality", "tone"])
        self.assertEqual((evaluation["greeting_quality"], evaluation["tone"]), (0, 10))

    def test_missing_criterion_raises_so_the_call_is_retried(self):
        data = _model_json(["greeting_quality"])
        with self.assertRaises(cs.CallAnalysisError):
            cs.build_evaluation(data, ["greeting_quality", "tone"])

    def test_outcome_fields_are_validated(self):
        evaluation = cs.build_evaluation(
            _model_json(["tone"], detected_outcome="weird", real_conversation="yes"), ["tone"],
        )
        self.assertEqual(evaluation["acceptable_outcomes"], ["interested", "callback"])
        self.assertEqual(evaluation["detected_outcome"], "no_conversation")
        self.assertFalse(evaluation["real_conversation"], "only a real boolean true counts")
        self.assertEqual(evaluation["closing_move"], 7)


class TranscribeCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_pieces_are_joined_in_order_with_later_pieces_told_their_offset(self):
        pieces = [AudioChunk(b"a", "audio/mpeg", 0, 300), AudioChunk(b"b", "audio/mpeg", 300, 480)]
        gemini = AsyncMock(side_effect=[("Telecaller: Hello", True), ("Customer: Bye", True)])
        with patch.object(cs, "split_audio", return_value=pieces), patch.object(cs, "gemini_transcribe_audio", gemini):
            transcript, used = await cs.transcribe_call(b"x", "audio/wav", tenant_id="t")
        self.assertEqual(transcript, "Telecaller: Hello\nCustomer: Bye")
        self.assertEqual(used, pieces)
        first_prompt, second_prompt = gemini.call_args_list[0].args[2], gemini.call_args_list[1].args[2]
        self.assertIn("'Telecaller:' or 'Customer:'", first_prompt)
        self.assertNotIn("later piece", first_prompt)
        self.assertIn("starting 05:00 into it", second_prompt)

    async def test_cut_off_piece_is_halved_and_redone(self):
        whole = AudioChunk(b"w", "audio/mpeg", 0, 400)
        halves = [AudioChunk(b"h1", "audio/mpeg", 0, 200), AudioChunk(b"h2", "audio/mpeg", 200, 400)]
        gemini = AsyncMock(side_effect=[("Telecaller: cut o", False), ("Telecaller: one", True), ("Customer: two", True)])
        with patch.object(cs, "split_audio", return_value=[whole]), \
             patch.object(cs, "resplit_chunk", return_value=halves), \
             patch.object(cs, "gemini_transcribe_audio", gemini):
            transcript, used = await cs.transcribe_call(b"x", "audio/mpeg")
        self.assertEqual(transcript, "Telecaller: one\nCustomer: two")
        self.assertEqual(used, halves)

    async def test_piece_that_cannot_be_cut_smaller_fails_instead_of_returning_half_a_call(self):
        with patch.object(cs, "split_audio", return_value=[AudioChunk(b"w", "audio/ogg", 0, 0)]), \
             patch.object(cs, "resplit_chunk", return_value=None), \
             patch.object(cs, "gemini_transcribe_audio", AsyncMock(return_value=("partial", False))):
            with self.assertRaises(cs.TranscriptionIncomplete):
                await cs.transcribe_call(b"x", "audio/ogg")


class AnalyzeCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_asks_only_for_selected_criteria_and_never_sees_the_marked_outcome(self):
        gemini = AsyncMock(return_value=_model_json(["greeting_quality", "professionalism"]))
        with patch.object(cs, "gemini_analysis_json", gemini):
            summary, evaluation = await cs.analyze_call("Telecaller: hi", ["greeting_quality", "professionalism"], tenant_id="t")
        prompt = gemini.call_args.kwargs["user_prompt"]
        self.assertIn("- greeting_quality /", prompt)
        self.assertNotIn("- tone /", prompt)
        self.assertNotIn("Caller-recorded outcome", prompt)
        self.assertEqual(gemini.call_args.kwargs["audio"], [])
        self.assertEqual(summary["brief"], "Discussed fees.")
        self.assertEqual(evaluation["ai_average"], 8.0)

    async def test_tone_attaches_the_audio(self):
        chunks = [AudioChunk(b"audio-1", "audio/mpeg", 0, 300), AudioChunk(b"audio-2", "audio/mpeg", 300, 400)]
        gemini = AsyncMock(return_value=_model_json(["tone"]))
        with patch.object(cs, "gemini_analysis_json", gemini):
            await cs.analyze_call("Telecaller: hi", ["tone"], chunks=chunks)
        self.assertEqual(gemini.call_args.kwargs["audio"], [(b"audio-1", "audio/mpeg"), (b"audio-2", "audio/mpeg")])
        self.assertIn("call audio is attached", gemini.call_args.kwargs["user_prompt"])

    async def test_tone_is_skipped_and_recorded_when_no_audio_fits(self):
        gemini = AsyncMock(return_value=_model_json(["greeting_quality"]))
        with patch.object(cs, "gemini_analysis_json", gemini), patch.object(cs, "audio_for_evaluation", return_value=[]):
            _, evaluation = await cs.analyze_call("Telecaller: hi", ["greeting_quality", "tone"], chunks=[])
        self.assertEqual(evaluation["criteria"], ["greeting_quality"])
        self.assertEqual(evaluation["criteria_skipped"], ["tone"])

    async def test_tone_only_with_no_audio_raises(self):
        with patch.object(cs, "audio_for_evaluation", return_value=[]):
            with self.assertRaises(cs.CallAnalysisError):
                await cs.analyze_call("Telecaller: hi", ["tone"], chunks=[])


class OutputCapTests(unittest.TestCase):
    def test_hitting_the_token_cap_counts_as_cut_off(self):
        self.assertTrue(_hit_output_cap({"usage": {"total_output_tokens": 24000}}, 24000))
        self.assertFalse(_hit_output_cap({"usage": {"total_output_tokens": 9000}}, 24000))

    def test_explicit_incomplete_status_counts_as_cut_off(self):
        self.assertTrue(_hit_output_cap({"status": "incomplete", "usage": {"total_output_tokens": 10}}, 24000))
        self.assertFalse(_hit_output_cap({"status": "completed", "usage": {}}, 24000))


if __name__ == "__main__":
    unittest.main()
