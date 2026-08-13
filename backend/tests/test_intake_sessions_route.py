import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class IntakeSessionsListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _db_returning(self, rows_data):
        db = MagicMock()
        rows = MagicMock()
        rows.data = rows_data
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = rows
        return db

    @patch("app.routes.intake.get_supabase")
    def test_status_all_returns_the_two_visible_statuses(self, mock_get_db):
        db = self._db_returning([])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/intake/sessions?status=all")

        self.assertEqual(res.status_code, 200)
        db.table.return_value.select.return_value.eq.return_value.in_.assert_called_with(
            "status", ["awaiting_payment", "paid"]
        )

    @patch("app.routes.intake.get_supabase")
    def test_rejects_an_unknown_status(self, mock_get_db):
        res = self.client.get("/api/v1/intake/sessions?status=collecting")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_returns_a_next_cursor_when_the_page_is_full(self, mock_get_db):
        rows = [
            {"id": f"s-{i}", "created_at": f"2026-08-{i + 1:02d}T00:00:00Z", "status": "paid"}
            for i in range(50)
        ]
        mock_get_db.return_value = self._db_returning(rows)

        res = self.client.get("/api/v1/intake/sessions?status=all&limit=50")

        self.assertEqual(res.json()["next_cursor"], "2026-08-50T00:00:00Z|s-49")

    @patch("app.routes.intake.get_supabase")
    def test_no_next_cursor_on_a_short_page(self, mock_get_db):
        mock_get_db.return_value = self._db_returning([
            {"id": "s-1", "created_at": "2026-08-01T00:00:00Z", "status": "paid"}
        ])

        res = self.client.get("/api/v1/intake/sessions?status=all&limit=50")

        self.assertIsNone(res.json()["next_cursor"])

    @patch("app.routes.intake.get_supabase")
    def test_rejects_a_malformed_cursor(self, mock_get_db):
        res = self.client.get("/api/v1/intake/sessions?status=all&cursor=garbage")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_filters_by_a_single_status(self, mock_get_db):
        db = self._db_returning([])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/intake/sessions?status=paid")

        self.assertEqual(res.status_code, 200)
        db.table.return_value.select.return_value.eq.return_value.in_.assert_called_with("status", ["paid"])

    @patch("app.routes.intake.get_supabase")
    def test_empty_result_returns_empty_list_not_error(self, mock_get_db):
        mock_get_db.return_value = self._db_returning([])

        res = self.client.get("/api/v1/intake/sessions?status=paid")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"data": [], "next_cursor": None})


if __name__ == "__main__":
    unittest.main()


class IntakeSessionsFilterInjectionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.intake.get_supabase")
    def test_rejects_a_search_query_containing_postgrest_operators(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/intake/sessions?status=all&q=" + "a),status.eq.paid,phone.ilike.*")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_accepts_an_ordinary_name_search(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = []
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.or_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/intake/sessions?status=all&q=Cheran")

        self.assertEqual(res.status_code, 200)

    @patch("app.routes.intake.get_supabase")
    def test_rejects_a_cursor_with_a_non_timestamp_created_at(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get(
            "/api/v1/intake/sessions?status=all&cursor="
            + "2026),status.eq.paid,and(1.eq.1|11111111-1111-1111-1111-111111111111"
        )
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_rejects_a_cursor_with_a_non_uuid_id(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get(
            "/api/v1/intake/sessions?status=all&cursor=2026-08-01T00:00:00Z|not-a-uuid"
        )
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.intake.get_supabase")
    def test_accepts_a_well_formed_cursor(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = []
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.or_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get(
            "/api/v1/intake/sessions?status=all&cursor=2026-08-01T00:00:00Z|11111111-1111-1111-1111-111111111111"
        )

        self.assertEqual(res.status_code, 200)
