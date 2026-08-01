"""Telecaller user creation via the Roles page (POST /api/v1/rbac/users) is
capped at 1 free seat per purchased calling module (SIM Basic/TeleCMI), or
the `telecaller_seats` purchased quantity when it's higher -- that quantity
is the tenant's TOTAL desired seats (the cart stepper starts at 1, the free
seat), not an add-on stacked on top of the baseline."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

TELECALLER_ROLE = {
    "id": "role-telecaller",
    "tenant_id": "tenant-1",
    "name": "Telecaller",
    "slug": "telecaller",
    "permissions": ["telecalling.dialer"],
}


def _mock_db(purchased_quantity, active_count, role=TELECALLER_ROLE, owner_user_id=None, has_calling_module=False):
    db = MagicMock()

    roles_tbl = MagicMock()
    roles_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[role] if role else []
    )

    # `_telecaller_seat_limit` reads `tenant_subscription_items` two different
    # ways: `resolve_entitlements` (select(...).eq(tenant_id).execute(), no
    # feature_key filter -- used to detect the free calling-module baseline)
    # and `get_purchased_quantity` (select(...).eq(tenant_id).eq(feature_key)
    # .execute() -- the additionally-purchased top-up quantity). Both hit the
    # same table mock at different points in the chain, so no conflict.
    items_tbl = MagicMock()
    entitlement_items = []
    if has_calling_module:
        entitlement_items.append({"feature_key": "telecalling_sim", "quantity": 1})
    if purchased_quantity:
        entitlement_items.append({"feature_key": "telecaller_seats", "quantity": purchased_quantity})
    items_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=entitlement_items)
    items_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"quantity": purchased_quantity}] if purchased_quantity else []
    )

    catalog_tbl = MagicMock()
    catalog_tbl.select.return_value.execute.return_value = MagicMock(data=[])

    # `_active_telecaller_count` first looks up the owner's user_id (to
    # exclude their free seeded caller row from the seat count), then
    # queries `callers` -- with a `.neq(owner_user_id)` in the chain only
    # when an owner was found.
    callers_tbl = MagicMock()
    base_chain = callers_tbl.select.return_value.eq.return_value.eq.return_value
    if owner_user_id:
        base_chain.neq.return_value.execute.return_value = MagicMock(count=active_count)
    else:
        base_chain.execute.return_value = MagicMock(count=active_count)
    base_chain.limit.return_value.execute.return_value = MagicMock(data=[])

    tenant_users_tbl = MagicMock()
    tenant_users_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"user_id": owner_user_id}] if owner_user_id else []
    )

    def table(name):
        return {
            "tenant_roles": roles_tbl,
            "tenant_subscription_items": items_tbl,
            "feature_catalog": catalog_tbl,
            "callers": callers_tbl,
            "tenant_users": tenant_users_tbl,
        }[name]

    db.table.side_effect = table
    return db


class RbacSeatEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_blocked_when_at_seat_limit(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=2, active_count=2)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("seat limit reached", res.json()["detail"].lower())

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_allowed_when_under_seat_limit(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=4, active_count=2)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["created"])

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_owner_seeded_caller_row_does_not_count_against_seats(self, mock_get_db, mock_cfg):
        # create_client seeds a free `callers` row for the tenant owner (so
        # owners can also take calls). With 1 purchased seat and only the
        # owner's own row active (0 real telecallers), creation must be
        # allowed -- the owner's row must not eat the one purchased seat.
        mock_get_db.return_value = _mock_db(purchased_quantity=1, active_count=0, owner_user_id="owner-1")

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_blocked_when_nothing_purchased(self, mock_get_db, mock_cfg):
        mock_get_db.return_value = _mock_db(purchased_quantity=0, active_count=0)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("seat limit reached", res.json()["detail"].lower())

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_calling_module_grants_one_free_seat_with_no_topup(self, mock_get_db, mock_cfg):
        # Buying SIM Basic/TeleCMI includes 1 free telecaller seat -- no
        # telecaller_seats top-up purchased at all, still 1 seat allowed.
        mock_get_db.return_value = _mock_db(purchased_quantity=0, active_count=0, has_calling_module=True)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_calling_module_free_seat_blocked_after_first_use(self, mock_get_db, mock_cfg):
        # The 1 free seat from the calling module is already used (1 active
        # telecaller, 0 additionally purchased) -- a 2nd must be blocked.
        mock_get_db.return_value = _mock_db(purchased_quantity=0, active_count=1, has_calling_module=True)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("(1/1)", res.json()["detail"])

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_calling_module_free_seat_plus_topup(self, mock_get_db, mock_cfg):
        # Cart stepper set to 2 (total desired seats, the free one included)
        # -- 2 total, not the free seat plus 2 more on top.
        mock_get_db.return_value = _mock_db(purchased_quantity=2, active_count=1, has_calling_module=True)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 200)

    @patch("app.routes.rbac.get_telecalling_config", return_value={"calling_provider": "telecmi"})
    @patch("app.routes.rbac.get_supabase")
    def test_purchased_total_never_stacks_on_free_baseline(self, mock_get_db, mock_cfg):
        # Cart stepper set to 2 with the calling module's free seat also
        # active must cap at 2 total, not 1 (free) + 2 (purchased) = 3.
        mock_get_db.return_value = _mock_db(purchased_quantity=2, active_count=2, has_calling_module=True)

        res = self.client.post("/api/v1/rbac/users", json={
            "full_name": "New Caller", "email": "new@example.com",
            "role_id": "role-telecaller", "temporary_password": "Password123!",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("(2/2)", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
