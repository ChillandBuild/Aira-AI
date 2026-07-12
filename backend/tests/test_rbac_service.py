import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import rbac


class RbacServiceTests(unittest.TestCase):
    def test_default_role_create_race_reselects_existing_role(self):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.side_effect = Exception("duplicate key value")
        existing_role = {
            "id": "role-1",
            "tenant_id": "tenant-1",
            "name": "Telecaller",
            "slug": "telecaller",
            "permissions": "{dashboard.view,telecalling.dialer}",
        }

        with patch("app.services.rbac._select_default_role", side_effect=[None, existing_role]):
            role = rbac.ensure_default_roles(db, "tenant-1")

        self.assertEqual(role["id"], "role-1")
        self.assertIn("telecalling.dialer", role["permissions"])

    def test_normalize_permissions_accepts_postgres_array_string(self):
        permissions = rbac.normalize_permissions("{dashboard.view,telecalling.dialer,unknown.permission}")
        self.assertEqual(permissions, ["dashboard.view", "telecalling.dialer"])

    def test_telecaller_role_detects_custom_name(self):
        role = {"name": "Senior Telecaller", "slug": None, "permissions": ["dashboard.view"]}
        self.assertTrue(rbac.is_telecaller_role(role))


if __name__ == "__main__":
    unittest.main()
