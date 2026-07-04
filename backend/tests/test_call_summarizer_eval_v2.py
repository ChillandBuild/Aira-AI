"""
Tests for call evaluation v2 — derivation helpers and analyze_call wiring.
No real Groq/Supabase calls — groq and app.config are stubbed.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

mock_settings = MagicMock()
mock_settings.groq_api_key = None  # disables module-level _client
mock_settings.sarvam_api_key = None

with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
    from app.services import call_summarizer


class QualityLabelTests(unittest.TestCase):
    def test_quality_label_thresholds(self):
        self.assertEqual(call_summarizer._quality_label(9.5), "Excellent")
        self.assertEqual(call_summarizer._quality_label(9.0), "Excellent")
        self.assertEqual(call_summarizer._quality_label(8.9), "Good")
        self.assertEqual(call_summarizer._quality_label(7.0), "Good")
        self.assertEqual(call_summarizer._quality_label(6.9), "Average")
        self.assertEqual(call_summarizer._quality_label(5.0), "Average")
        self.assertEqual(call_summarizer._quality_label(4.9), "Bad")
        self.assertEqual(call_summarizer._quality_label(1.0), "Bad")


class FinalizeEvaluationTests(unittest.TestCase):
    def test_finalize_evaluation_computes_overall_and_label(self):
        evaluation = {
            "greeting_quality": 8,
            "communication_clarity": 8,
            "product_knowledge": 8,
            "requirement_understanding": 8,
            "conversation_engagement": 8,
            "objection_handling": 8,
            "professionalism": 8,
            "coaching_tip": "Keep it up",
        }
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertEqual(result["overall_score"], 8.0)
        self.assertEqual(result["quality_label"], "Good")
        self.assertEqual(result["evaluation_version"], 2)

    def test_finalize_evaluation_handles_missing_scores(self):
        evaluation = {"coaching_tip": "no scores returned"}
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertNotIn("overall_score", result)
        self.assertNotIn("quality_label", result)
        self.assertEqual(result["evaluation_version"], 2)

    def test_finalize_evaluation_rounds_to_one_decimal(self):
        evaluation = {
            "greeting_quality": 8,
            "communication_clarity": 7,
            "product_knowledge": 6,
            "requirement_understanding": 8,
            "conversation_engagement": 7,
            "objection_handling": 5,
            "professionalism": 9,
        }
        # mean = 50/7 = 7.142857...
        result = call_summarizer._finalize_evaluation(evaluation)
        self.assertEqual(result["overall_score"], 7.1)
        self.assertEqual(result["quality_label"], "Good")


class AnalyzeCallV2Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self._orig_get_groq_client = call_summarizer.get_groq_client
        call_summarizer.get_groq_client = MagicMock(return_value=self.mock_client)

    def tearDown(self):
        call_summarizer.get_groq_client = self._orig_get_groq_client

    async def test_analyze_call_returns_v2_evaluation_with_derived_fields(self):
        llm_payload = {
            "course": "CRM Pro",
            "product": "CRM Pro",
            "budget": "50000",
            "timeline": "next month",
            "next_action": "Send proposal",
            "sentiment": "positive",
            "brief": "Lead is interested in CRM Pro.",
            "greeting_quality": 8,
            "greeting_quality_reason": "Clear intro, didn't ask the customer's name.",
            "communication_clarity": 7,
            "communication_clarity_reason": "Mostly clear; a couple of rushed lines.",
            "product_knowledge": 6,
            "product_knowledge_reason": "Quoted an outdated price vs. the knowledge base.",
            "requirement_understanding": 8,
            "requirement_understanding_reason": "Identified budget and timeline early.",
            "conversation_engagement": 7,
            "conversation_engagement_reason": "Good rapport, customer talked a lot at the end.",
            "objection_handling": 5,
            "objection_handling_reason": "Dismissed the price objection.",
            "professionalism": 9,
            "professionalism_reason": "Polite throughout, no interruptions.",
            "talk_ratio": 62,
            "clear_next_step": True,
            "next_step_summary": "Demo scheduled for Friday.",
            "outcome_match": False,
            "outcome_match_reason": "Marked converted but customer said they'd think about it.",
            "purchase_intent": "medium",
            "missed_opportunity": True,
            "missed_opportunity_note": "Didn't offer the premium plan when asked about pricing tiers.",
            "coaching_tip": "Acknowledge the price objection before pivoting to value.",
        }
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_payload)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        self.mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        summary, evaluation = await call_summarizer.analyze_call(
            "transcript text",
            lead_name="Jane",
            outcome="converted",
            kb_context="CRM Pro costs 4999/month per seat.",
        )

        # Summary fields pass through unchanged
        self.assertEqual(summary["course"], "CRM Pro")
        self.assertEqual(summary["sentiment"], "positive")

        # All 23 LLM-graded evaluation fields pass through
        for key in call_summarizer._SCORE_KEYS:
            self.assertEqual(evaluation[key], llm_payload[key])
            self.assertEqual(evaluation[f"{key}_reason"], llm_payload[f"{key}_reason"])
        self.assertEqual(evaluation["talk_ratio"], 62)
        self.assertEqual(evaluation["clear_next_step"], True)
        self.assertEqual(evaluation["next_step_summary"], "Demo scheduled for Friday.")
        self.assertEqual(evaluation["outcome_match"], False)
        self.assertEqual(evaluation["purchase_intent"], "medium")
        self.assertEqual(evaluation["missed_opportunity"], True)
        self.assertEqual(evaluation["coaching_tip"], llm_payload["coaching_tip"])

        # Derived fields
        expected_overall = round(sum(llm_payload[k] for k in call_summarizer._SCORE_KEYS) / 7, 1)
        self.assertEqual(evaluation["overall_score"], expected_overall)
        self.assertEqual(evaluation["quality_label"], call_summarizer._quality_label(expected_overall))
        self.assertEqual(evaluation["evaluation_version"], 2)

        # Prompt grounding: KB context, outcome, and bumped max_tokens reached Groq
        sent_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        user_msg = sent_kwargs["messages"][1]["content"]
        self.assertIn("CRM Pro costs 4999/month per seat.", user_msg)
        self.assertIn("converted", user_msg)
        self.assertEqual(sent_kwargs["max_tokens"], 1100)

    async def test_analyze_call_without_kb_context_still_grades_leniently(self):
        llm_payload = {
            "course": "CRM Pro", "product": "CRM Pro", "budget": None, "timeline": None,
            "next_action": "Call back", "sentiment": "neutral", "brief": "Brief call.",
            "greeting_quality": 7, "greeting_quality_reason": "Fine.",
            "communication_clarity": 7, "communication_clarity_reason": "Fine.",
            "product_knowledge": 7, "product_knowledge_reason": "No KB available, graded neutrally.",
            "requirement_understanding": 7, "requirement_understanding_reason": "Fine.",
            "conversation_engagement": 7, "conversation_engagement_reason": "Fine.",
            "objection_handling": 7, "objection_handling_reason": "Fine.",
            "professionalism": 7, "professionalism_reason": "Fine.",
            "talk_ratio": 50,
            "clear_next_step": False, "next_step_summary": None,
            "outcome_match": True, "outcome_match_reason": "Matches.",
            "purchase_intent": "low",
            "missed_opportunity": False, "missed_opportunity_note": None,
            "coaching_tip": "Keep going.",
        }
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_payload)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        self.mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        summary, evaluation = await call_summarizer.analyze_call(
            "transcript text", lead_name=None, outcome=None, kb_context=None,
        )

        self.assertEqual(evaluation["overall_score"], 7.0)
        self.assertEqual(evaluation["quality_label"], "Good")
        sent_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        user_msg = sent_kwargs["messages"][1]["content"]
        self.assertIn("none available", user_msg.lower())


class TranscribeRecordingTests(unittest.IsolatedAsyncioTestCase):
    """Uses patch.object(call_summarizer, ...) / patch("httpx.AsyncClient", ...) rather than
    string-target patch("app.services.call_summarizer.X", ...): the module-level
    patch.dict("sys.modules", ...) at file top snapshots and restores the FULL sys.modules
    dict on exit, silently dropping "app.services.call_summarizer" from the cache. A later
    string-target patch() would re-import a phantom copy of the module (with real, unmocked
    app.config) that the test never actually exercises. patch.object works directly against
    the already-imported `call_summarizer` reference instead of re-resolving by dotted path."""

    def setUp(self):
        self._orig_get_sarvam_api_key = call_summarizer.get_sarvam_api_key

    def tearDown(self):
        call_summarizer.get_sarvam_api_key = self._orig_get_sarvam_api_key

    async def test_transcribe_recording_success(self):
        download_resp = MagicMock()
        download_resp.content = b"fake-audio-bytes"
        download_resp.raise_for_status = MagicMock()

        sarvam_resp = MagicMock()
        sarvam_resp.raise_for_status = MagicMock()
        sarvam_resp.json.return_value = {"transcript": "Hello, how are you?", "language_code": "en-IN"}

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(return_value=download_resp)
        mock_instance.post = AsyncMock(return_value=sarvam_resp)

        call_summarizer.get_sarvam_api_key = MagicMock(return_value="test-key")
        with patch.object(call_summarizer.httpx, "AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_instance
            transcript = await call_summarizer.transcribe_recording("https://example.com/rec.mp3")

        self.assertEqual(transcript, "Hello, how are you?")
        post_args, post_kwargs = mock_instance.post.call_args
        self.assertEqual(post_args[0], "https://api.sarvam.ai/speech-to-text")
        self.assertEqual(post_kwargs["headers"], {"api-subscription-key": "test-key"})
        self.assertEqual(post_kwargs["data"]["model"], "saaras:v3")
        self.assertEqual(post_kwargs["data"]["mode"], "transcribe")

    async def test_transcribe_recording_missing_api_key_returns_empty(self):
        call_summarizer.get_sarvam_api_key = MagicMock(
            side_effect=RuntimeError("Sarvam API key not configured")
        )
        transcript = await call_summarizer.transcribe_recording("https://example.com/rec.mp3")
        self.assertEqual(transcript, "")

    async def test_transcribe_recording_download_failure_returns_empty(self):
        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(side_effect=Exception("network error"))

        call_summarizer.get_sarvam_api_key = MagicMock(return_value="test-key")
        with patch.object(call_summarizer.httpx, "AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_instance
            transcript = await call_summarizer.transcribe_recording("https://example.com/rec.mp3")

        self.assertEqual(transcript, "")

    async def test_transcribe_recording_sarvam_api_failure_returns_empty(self):
        download_resp = MagicMock()
        download_resp.content = b"fake-audio-bytes"
        download_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(return_value=download_resp)
        mock_instance.post = AsyncMock(side_effect=Exception("503 Service Unavailable"))

        call_summarizer.get_sarvam_api_key = MagicMock(return_value="test-key")
        with patch.object(call_summarizer.httpx, "AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_instance
            transcript = await call_summarizer.transcribe_recording("https://example.com/rec.mp3")

        self.assertEqual(transcript, "")


if __name__ == "__main__":
    unittest.main()
