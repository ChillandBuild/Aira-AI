"""Tests for the generic per-tenant data-clearing endpoints
(GET/POST /clients/{id}/clear/{data_type}) -- the single implementation that
absorbed the old, separate /wipe-leads endpoint. The "leads" data_type is the
interesting case: it fans out across several dependent tables plus the
app_settings "broadcast_history" JSON blob (the one behavior wipe_leads had
that the original clear_data didn't, ported over when the two were merged)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.system_admin import get_system_admin


class OperatorClearDataTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, tenant_found=True):
        db = MagicMock()
        tables: dict = {}

        def table(name):
            if name not in tables:
                tbl = MagicMock()
                if name == "tenants":
                    tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = (
                        {"id": "tenant-1", "name": "Acme"} if tenant_found else None
                    )
                else:
                    tbl.select.return_value.count = 3
                    tbl.select.return_value.eq.return_value.execute.return_value.count = 3
                    tbl.select.return_value.eq.return_value.is_.return_value.execute.return_value.count = 3
                    tbl.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "r1"}]
                    tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "r1"}]
                tables[name] = tbl
            return tables[name]

        db.table.side_effect = table
        mock_get_db.return_value = db
        return db, tables

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_count_rejects_invalid_data_type(self, mock_get_db, mock_audit):
        self._mock_db(mock_get_db)
        res = self.client.get("/api/v1/operator/clients/tenant-1/clear/not-a-type/count")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_rejects_invalid_data_type(self, mock_get_db, mock_audit):
        self._mock_db(mock_get_db)
        res = self.client.post("/api/v1/operator/clients/tenant-1/clear/not-a-type")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_404_when_tenant_not_found(self, mock_get_db, mock_audit):
        self._mock_db(mock_get_db, tenant_found=False)
        res = self.client.post("/api/v1/operator/clients/tenant-1/clear/leads")
        self.assertEqual(res.status_code, 404)

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_leads_clears_broadcast_history_blob(self, mock_get_db, mock_audit):
        """Regression: this is the one behavior wipe_leads had that clear_data
        originally didn't -- broadcast_history is a JSON blob in app_settings,
        not a row-per-broadcast table, so it needs its own delete call."""
        db, tables = self._mock_db(mock_get_db)

        res = self.client.post("/api/v1/operator/clients/tenant-1/clear/leads")
        self.assertEqual(res.status_code, 200)

        app_settings_tbl = tables["app_settings"]
        app_settings_tbl.delete.return_value.eq.assert_any_call("tenant_id", "tenant-1")
        app_settings_tbl.delete.return_value.eq.return_value.eq.assert_any_call("key", "broadcast_history")

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_leads_clears_all_dependent_tables(self, mock_get_db, mock_audit):
        db, tables = self._mock_db(mock_get_db)

        self.client.post("/api/v1/operator/clients/tenant-1/clear/leads")

        for name in ("messages", "lead_notes", "chat_handovers", "follow_up_jobs",
                     "broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts",
                     "broadcast_tags", "scheduled_broadcasts", "leads"):
            self.assertIn(name, tables, f"expected {name} to be touched")
            tables[name].delete.return_value.eq.assert_any_call("tenant_id", "tenant-1")

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_non_leads_type_only_touches_its_own_tables(self, mock_get_db, mock_audit):
        db, tables = self._mock_db(mock_get_db)

        res = self.client.post("/api/v1/operator/clients/tenant-1/clear/call_logs")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data_type"], "call_logs")
        self.assertIn("call_logs", tables)
        # leads-only cleanup (e.g. broadcast_history) must not fire for other types
        self.assertNotIn("app_settings", tables)

    @patch("app.routes.operator.record_audit_event")
    @patch("app.routes.operator.get_supabase")
    def test_clear_data_records_audit_event(self, mock_get_db, mock_audit):
        self._mock_db(mock_get_db)
        self.client.post("/api/v1/operator/clients/tenant-1/clear/leads")
        self.assertTrue(mock_audit.called)
        _, kwargs = mock_audit.call_args
        self.assertEqual(kwargs["action"], "operator.data_cleared:leads")
        self.assertEqual(kwargs["target_id"], "tenant-1")


if __name__ == "__main__":
    unittest.main()
