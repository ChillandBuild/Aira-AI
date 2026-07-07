import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClientConfigTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.operator.get_supabase")
    def test_get_client_config(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": "tenant-1",
                    "enabled_features": ["whatsapp", "telecalling"]
                }
            elif name == "app_settings":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"key": "ai_auto_reply_enabled", "value": "true"},
                    {"key": "ai_voice_reply_enabled", "value": "true"},
                    {"key": "ai_voice_reply_speaker", "value": "shubh"},
                    {"key": "ai_voice_reply_pace", "value": "1.2"},
                    {"key": "ai_voice_reply_language_mode", "value": "fixed"},
                    {"key": "ai_voice_reply_language_code", "value": "ta-IN"},
                    {"key": "sarvam_api_key", "value": "client-sarvam-key"},
                    {"key": "telegram_bot_token", "value": "123:abc"},
                    {"key": "instagram_page_id", "value": "ig-page"},
                    {"key": "instagram_access_token", "value": "ig-token"},
                    {"key": "facebook_page_id", "value": "fb-page"},
                    {"key": "facebook_access_token", "value": "fb-token"},
                    {"key": "reengagement_enabled", "value": "false"},
                    {"key": "kb_retrieval_mode", "value": "hybrid"}
                ]
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            elif name == "tenant_usage_counters":
                tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                    {"metric": "ai_speech_to_text", "used": 3, "included": 0, "hard_cap": None},
                    {"metric": "ai_text_to_speech", "used": 5, "included": 0, "hard_cap": None},
                ]
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/config")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["enabled_features"], ["whatsapp", "telecalling"])
        self.assertEqual(body["settings"]["ai_auto_reply_enabled"], True)
        self.assertEqual(body["settings"]["ai_voice_reply_enabled"], True)
        self.assertEqual(body["settings"]["ai_voice_reply_speaker"], "shubh")
        self.assertEqual(body["settings"]["ai_voice_reply_pace"], 1.2)
        self.assertEqual(body["settings"]["ai_voice_reply_language_mode"], "fixed")
        self.assertEqual(body["settings"]["ai_voice_reply_language_code"], "ta-IN")
        self.assertEqual(body["settings"]["reengagement_enabled"], False)
        self.assertEqual(body["settings"]["kb_retrieval_mode"], "hybrid")
        self.assertEqual(body["credentials_status"]["ai"], "configured")
        self.assertEqual(body["credentials_status"]["telegram"], "configured")
        self.assertEqual(body["credentials_status"]["instagram"], "configured")
        self.assertEqual(body["credentials_status"]["facebook"], "configured")
        self.assertNotIn("payments", body["credentials_status"])
        self.assertEqual(body["voice_usage"]["speech_to_text"], 3)
        self.assertEqual(body["voice_usage"]["text_to_speech"], 5)

    @patch("app.config_dynamic.invalidate_cache")
    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_patch_client_config(self, mock_get_db, mock_record_audit, mock_invalidate_cache):
        db = MagicMock()
        app_settings_table = MagicMock()
        app_settings_table.upsert.return_value.execute.return_value.data = [{"key": "kb_retrieval_mode"}]

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": "tenant-1"
                }
            elif name == "app_settings":
                return app_settings_table
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        payload = {
            "settings": {
                "kb_retrieval_mode": "keyword",
                "reengagement_enabled": True,
                "ai_voice_reply_enabled": True,
                "ai_voice_reply_speaker": "shubh",
                "ai_voice_reply_pace": "1.2",
                "ai_voice_reply_language_mode": "fixed",
                "ai_voice_reply_language_code": "ta-IN",
                "sarvam_api_key": "client-secret",
            }
        }
        res = self.client.patch("/api/v1/operator/clients/tenant-1/config", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

        upserted_rows = [call.args[0] for call in app_settings_table.upsert.call_args_list]
        sarvam_row = next(row for row in upserted_rows if row["key"] == "sarvam_api_key")
        self.assertTrue(sarvam_row["is_secret"])
        mock_invalidate_cache.assert_called_once()
        mock_record_audit.assert_called_once()
        audit_kwargs = mock_record_audit.call_args.kwargs
        self.assertEqual(audit_kwargs["metadata"], {"settings": payload["settings"]})
        self.assertNotIn("new_value", audit_kwargs)

    @patch("app.routes.operator.get_supabase")
    def test_get_client_config_survives_usage_counter_lookup_failure(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": "tenant-1",
                    "enabled_features": ["whatsapp"]
                }
            elif name == "app_settings":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"key": "ai_voice_reply_enabled", "value": "true"},
                ]
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            elif name == "tenant_usage_counters":
                tbl.select.return_value.eq.return_value.eq.return_value.execute.side_effect = RuntimeError("usage table missing")
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/config")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["credentials_status"]["ai"], "not_configured")
        self.assertEqual(body["voice_usage"], {"speech_to_text": 0, "text_to_speech": 0})
        self.assertEqual(body["usage"]["counters"], [])

    @patch("app.routes.operator._build_fleet_rows", side_effect=RuntimeError("fleet query failed"))
    @patch("app.routes.operator.get_supabase")
    def test_operator_alerts_survives_signal_lookup_failure(self, mock_get_db, _mock_fleet):
        mock_get_db.return_value = MagicMock()

        res = self.client.get("/api/v1/operator/alerts")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"data": []})


if __name__ == "__main__":
    unittest.main()
