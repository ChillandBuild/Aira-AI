"""delete_user (DELETE /api/v1/rbac/users/{user_id}) must hard-delete the
callers row (not just deactivate it) so it doesn't linger as an orphan once
the auth account and tenant_users row are gone -- and must null out any
chat_handovers.assigned_to reference first, since that FK has no cascade
(ON DELETE NO ACTION) and would otherwise block the delete."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CTX = {
    "tenant_id": "tenant-1",
    "role": "owner",
    "user_id": "owner-1",
    "caller_id": None,
    "permissions": ["roles.manage"],
}


def _mock_db(member_role="caller", caller_row=None):
    db = MagicMock()

    tenant_users_tbl = MagicMock()
    tenant_users_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"role": member_role}]
    )
    tenant_users_tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"user_id": "user-1"}])

    callers_tbl = MagicMock()
    callers_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[caller_row] if caller_row else []
    )
    callers_tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "caller-1"}])

    handovers_tbl = MagicMock()
    handovers_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    audit_tbl = MagicMock()
    audit_tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-1"}])

    def table(name):
        return {
            "tenant_users": tenant_users_tbl,
            "callers": callers_tbl,
            "chat_handovers": handovers_tbl,
            "app_audit_logs": audit_tbl,
        }[name]

    db.table.side_effect = table
    db.auth.admin.delete_user = MagicMock()
    return db, callers_tbl, handovers_tbl, audit_tbl


class TestDeleteUserHardDelete(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "owner-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: CTX

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.rbac.get_supabase")
    def test_hard_deletes_callers_row_and_nulls_handovers(self, mock_get_supabase):
        caller_row = {"id": "caller-1", "name": "Test Caller", "phone": None, "active": True,
                      "telecmi_agent_id": None, "telecmi_agent_password": None}
        db, callers_tbl, handovers_tbl, audit_tbl = _mock_db(caller_row=caller_row)
        mock_get_supabase.return_value = db

        client = TestClient(app)
        resp = client.delete("/api/v1/rbac/users/user-1")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"deleted": True})
        # chat_handovers nulled before the caller row is dropped
        handovers_tbl.update.assert_called_once_with({"assigned_to": None})
        # callers row is actually deleted, not deactivated
        callers_tbl.delete.assert_called_once()
        callers_tbl.update.assert_not_called()
        # audit event recorded
        audit_tbl.insert.assert_called_once()
        inserted = audit_tbl.insert.call_args[0][0]
        self.assertEqual(inserted["action"], "team.member_deleted")
        self.assertEqual(inserted["target_type"], "tenant_user")
        self.assertEqual(inserted["target_id"], "user-1")


if __name__ == "__main__":
    unittest.main()
