"""POST /api/v1/numbers/sync-from-meta discovers every number on the tenant's
Meta WABA, inserting ones we don't have yet (always as standby/warming --
never auto-primary) and refreshing quality/tier on ones we do."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


def _mock_numbers_db(initial_rows):
    """Minimal Supabase mock for phone_numbers + incidents, backed by a
    mutable in-memory list so inserts/updates during a sync are reflected in
    later reads within the same test."""
    db = MagicMock()
    state = {"rows": [dict(r) for r in initial_rows]}
    next_id = {"n": 1}

    numbers_tbl = MagicMock()

    select_node = MagicMock()
    select_node.execute.side_effect = lambda: MagicMock(data=list(state["rows"]))
    select_node.order.return_value.order.return_value.execute.side_effect = (
        lambda: MagicMock(data=list(state["rows"]))
    )
    numbers_tbl.select.return_value.eq.return_value = select_node

    def do_insert(payload):
        row = dict(payload)
        row.setdefault("id", f"new-{next_id['n']}")
        row.setdefault("created_at", f"2026-02-{next_id['n']:02d}T00:00:00Z")
        row.setdefault("quality_rating", "green")
        row.setdefault("messaging_tier", 1000)
        next_id["n"] += 1
        state["rows"].append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[row])
        return m
    numbers_tbl.insert.side_effect = do_insert

    def do_update(payload):
        m = MagicMock()

        def eq_id(_field, value):
            m2 = MagicMock()

            def eq_tenant(_field2, _value2):
                m3 = MagicMock()

                def execute():
                    matched = [r for r in state["rows"] if r["id"] == value]
                    for r in matched:
                        r.update(payload)
                    return MagicMock(data=matched)
                m3.execute.side_effect = execute
                return m3
            m2.eq.side_effect = eq_tenant
            return m2
        m.eq.side_effect = eq_id
        return m
    numbers_tbl.update.side_effect = do_update

    incidents_tbl = MagicMock()
    incidents_tbl.insert.return_value.execute.return_value = MagicMock(data=[])

    def table(name):
        return {"phone_numbers": numbers_tbl, "incidents": incidents_tbl}[name]
    db.table.side_effect = table
    db._state = state
    return db


class SyncFromMetaTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_missing_waba_id_returns_400(self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked):
        mock_get_db.return_value = _mock_numbers_db([])
        mock_get_setting.return_value = None

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 400)
        mock_list.assert_not_called()

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_fresh_tenant_imports_all_as_standby_and_locked(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        db = _mock_numbers_db([])
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+91 98765-00001", "verified_name": "Number 1",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
            {"id": "meta-2", "display_phone_number": "+91 98765-00002", "verified_name": "Number 2",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
            {"id": "meta-3", "display_phone_number": "+91 98765-00003", "verified_name": "Number 3",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()  # no primary yet -- everything locked

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["synced"], 3)
        self.assertEqual(body["failed"], 0)
        self.assertEqual(len(body["data"]), 3)
        for row in body["data"]:
            self.assertEqual(row["role"], "standby")
            self.assertEqual(row["status"], "warming")
            self.assertTrue(row["locked"])
        numbers = {r["number"] for r in db._state["rows"]}
        self.assertEqual(numbers, {"+919876500001", "+919876500002", "+919876500003"})

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_matches_existing_row_by_meta_id_and_refreshes_quality(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        existing = [{
            "id": "row-1", "number": "+919876500001", "display_name": "Number 1",
            "role": "primary", "status": "active", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 14, "meta_phone_number_id": "meta-1",
            "created_at": "2026-01-01T00:00:00Z", "last_reset_at": "2026-01-01T00:00:00Z",
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+919876500001", "verified_name": "Number 1",
             "quality_rating": "YELLOW", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = {"row-1"}

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["synced"], 1)
        updated_row = next(r for r in db._state["rows"] if r["id"] == "row-1")
        self.assertEqual(updated_row["quality_rating"], "yellow")
        self.assertEqual(len(db._state["rows"]), 1)  # no duplicate inserted

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_matches_existing_row_by_normalized_number_and_backfills_meta_id(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        existing = [{
            "id": "row-1", "number": "+919876500001", "display_name": "Manually Added",
            "role": "standby", "status": "warming", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 0, "meta_phone_number_id": None,
            "created_at": "2026-01-01T00:00:00Z", "last_reset_at": None,
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-1", "display_phone_number": "+91 98765 00001", "verified_name": "Number 1",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(db._state["rows"]), 1)  # matched, not duplicated
        self.assertEqual(db._state["rows"][0]["meta_phone_number_id"], "meta-1")

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_locked_existing_row_never_promoted_to_active_by_warmup(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        from datetime import datetime, timedelta, timezone
        old_reset = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        existing = [{
            "id": "row-2", "number": "+919876500002", "display_name": "Second Number",
            "role": "standby", "status": "warming", "quality_rating": "green",
            "messaging_tier": 1000, "warm_up_day": 1, "meta_phone_number_id": "meta-2",
            "created_at": "2026-01-02T00:00:00Z", "last_reset_at": old_reset,
        }]
        db = _mock_numbers_db(existing)
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": "meta-2", "display_phone_number": "+919876500002", "verified_name": "Second Number",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()  # row-2 is locked (not primary, over quota)

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        updated_row = next(r for r in db._state["rows"] if r["id"] == "row-2")
        self.assertGreaterEqual(updated_row["warm_up_day"], 14)  # still accrues warm-up day
        self.assertEqual(updated_row["status"], "warming")  # but never promoted to active

    @patch("app.routes.numbers.get_unlocked_number_ids")
    @patch("app.routes.numbers.numbers_pool_limit")
    @patch("app.routes.numbers.list_waba_phone_numbers", new_callable=AsyncMock)
    @patch("app.routes.numbers.get_setting")
    @patch("app.routes.numbers.get_supabase")
    def test_one_bad_number_does_not_abort_the_whole_sync(
        self, mock_get_db, mock_get_setting, mock_list, mock_limit, mock_unlocked
    ):
        db = _mock_numbers_db([])
        mock_get_db.return_value = db
        mock_get_setting.return_value = "waba-1"
        mock_list.return_value = [
            {"id": None, "display_phone_number": "bad"},  # no usable id -- should be skipped/counted as failed
            {"id": "meta-9", "display_phone_number": "+919876509999", "verified_name": "Good Number",
             "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1000"},
        ]
        mock_limit.return_value = 1
        mock_unlocked.return_value = set()

        res = self.client.post("/api/v1/numbers/sync-from-meta")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["synced"], 1)
        self.assertEqual(body["failed"], 1)


if __name__ == "__main__":
    unittest.main()
