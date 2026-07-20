"""
Tests for the track-only, non-blocking token metering wrapper `record_tokens()`
and its raw-groq-sdk counterpart `record_groq_sdk()`.

Contract under test (same as entitlements.meter(), see test_metering.py):
metering must NEVER block, cap, delay, or break the AI call it instruments.
record_tokens() must swallow any exception raised while calling the
increment_token_usage RPC and must no-op when tenant_id is empty.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import token_meter


class RecordTokensNeverRaisesTests(unittest.TestCase):
    def test_swallows_exception_from_supabase_rpc(self):
        with patch("app.db.supabase.get_supabase", side_effect=RuntimeError("db is down")):
            try:
                result = token_meter.record_tokens(
                    "tenant-1", "ai_reply", "groq", "llama-3.3-70b-versatile", 100, 50
                )
            except Exception as e:  # pragma: no cover - failure path
                self.fail(f"record_tokens() must never raise, but raised: {e}")
            self.assertIsNone(result)

    def test_skips_when_tenant_id_empty(self):
        with patch("app.db.supabase.get_supabase") as mock_get_db:
            token_meter.record_tokens("", "ai_reply", "groq", "m", 1, 1)
            token_meter.record_tokens(None, "ai_reply", "groq", "m", 1, 1)
            mock_get_db.assert_not_called()

    def test_calls_rpc_with_expected_params_on_happy_path(self):
        mock_db = MagicMock()
        with patch("app.db.supabase.get_supabase", return_value=mock_db):
            token_meter.record_tokens("tenant-1", "call_analysis", "gemini", "gemini-3.1-flash-lite", 120, 45)
        mock_db.rpc.assert_called_once_with(
            "increment_token_usage",
            {
                "p_tenant_id": "tenant-1",
                "p_purpose": "call_analysis",
                "p_provider": "gemini",
                "p_model": "gemini-3.1-flash-lite",
                "p_input_tokens": 120,
                "p_output_tokens": 45,
            },
        )
        mock_db.rpc.return_value.execute.assert_called_once()

    def test_none_token_counts_recorded_as_zero(self):
        """A provider that omits its usage block still records the call
        (calls count stays trustworthy) rather than being silently dropped."""
        mock_db = MagicMock()
        with patch("app.db.supabase.get_supabase", return_value=mock_db):
            token_meter.record_tokens("tenant-1", "voice_reply_tts", "gemini", "gemini-3.1-flash-tts-preview", None, None)
        call_kwargs = mock_db.rpc.call_args[0][1]
        self.assertEqual(call_kwargs["p_input_tokens"], 0)
        self.assertEqual(call_kwargs["p_output_tokens"], 0)


class RecordGroqSdkTests(unittest.TestCase):
    def test_reads_usage_off_sdk_response_object(self):
        resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=200, completion_tokens=30))
        with patch.object(token_meter, "record_tokens") as mock_record:
            token_meter.record_groq_sdk("tenant-1", "scoring", "llama-3.3-70b-versatile", resp)
        mock_record.assert_called_once_with(
            "tenant-1", "scoring", "groq", "llama-3.3-70b-versatile", 200, 30
        )

    def test_missing_usage_attribute_does_not_raise(self):
        resp = SimpleNamespace()  # no .usage at all
        with patch.object(token_meter, "record_tokens") as mock_record:
            try:
                token_meter.record_groq_sdk("tenant-1", "scoring", "m", resp)
            except Exception as e:  # pragma: no cover - failure path
                self.fail(f"record_groq_sdk() must never raise, but raised: {e}")
        mock_record.assert_called_once_with("tenant-1", "scoring", "groq", "m", None, None)


if __name__ == "__main__":
    unittest.main()
