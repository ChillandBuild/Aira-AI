"""Tests for optional start/end custom ranges on /messaging and /inbound.
/overview is deliberately excluded -- see the plan's Global Constraints."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes.analytics import _resolve_window


class ResolveWindowTests(unittest.TestCase):
    def test_custom_start_end_builds_a_half_open_utc_window(self):
        start_dt, end_dt, days = _resolve_window("7d", "2026-07-10", "2026-07-12")
        self.assertEqual(start_dt.isoformat(), "2026-07-10T00:00:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-07-13T00:00:00+00:00")
        self.assertEqual(days, ["2026-07-10", "2026-07-11", "2026-07-12"])

    def test_end_before_start_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "2026-07-12", "2026-07-10")

    def test_malformed_date_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "not-a-date", "2026-07-12")

    def test_missing_start_end_falls_back_to_the_preset(self):
        start_dt, end_dt, days = _resolve_window("today", None, None)
        self.assertEqual(len(days), 1)
        self.assertIsNotNone(end_dt)

    def test_ist_custom_dates_build_the_same_bounds_as_compare(self):
        start_dt, end_dt, days = _resolve_window(
            "7d", "2026-07-10", "2026-07-12", "Asia/Kolkata"
        )

        self.assertEqual(start_dt.isoformat(), "2026-07-09T18:30:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-07-12T18:30:00+00:00")
        self.assertEqual(days, ["2026-07-10", "2026-07-11", "2026-07-12"])

    @patch("app.routes.analytics.datetime")
    def test_ist_7d_preset_is_seven_calendar_days_ending_today(self, mock_datetime):
        mock_datetime.now.return_value = datetime(2026, 7, 31, tzinfo=timezone.utc)
        mock_datetime.combine.side_effect = datetime.combine
        mock_datetime.min = datetime.min

        start_dt, end_dt, days = _resolve_window(
            "7d", None, None, "Asia/Kolkata"
        )

        self.assertEqual(start_dt.isoformat(), "2026-07-24T18:30:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-07-31T18:30:00+00:00")
        self.assertEqual(days[0], "2026-07-25")
        self.assertEqual(days[-1], "2026-07-31")
        self.assertEqual(len(days), 7)


class MessagingCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_passes_exact_bounds_to_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        first_call_params = db.rpc.call_args_list[0].args[1]
        self.assertEqual(first_call_params["p_start"], "2026-07-10T00:00:00+00:00")
        self.assertEqual(first_call_params["p_end"], "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_ist_range_uses_ist_bounds_and_daily_rpc_buckets(self, mock_get_db):
        db = MagicMock()

        def rpc(name, params):
            result = MagicMock()
            result.execute.return_value = MagicMock(
                data=[
                    {
                        "day": "2026-07-10",
                        "inbound": 2,
                        "outbound": 1,
                        "ai": 1,
                        "human": 0,
                    }
                ]
                if name == "analytics_daily_messages"
                else []
            )
            return result

        db.rpc.side_effect = rpc
        today_query = db.table.return_value.select.return_value.eq.return_value.gte
        today_query.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get(
            "/api/v1/analytics/messaging?start=2026-07-10&end=2026-07-10"
            "&timezone=Asia%2FKolkata"
        )

        self.assertEqual(res.status_code, 200)
        daily_params = next(
            call.args[1] for call in db.rpc.call_args_list
            if call.args[0] == "analytics_daily_messages"
        )
        self.assertEqual(daily_params["p_start"], "2026-07-09T18:30:00+00:00")
        self.assertEqual(daily_params["p_end"], "2026-07-10T18:30:00+00:00")
        self.assertEqual(daily_params["p_timezone"], "Asia/Kolkata")
        self.assertEqual(
            res.json()["daily_messages"],
            [{"day": "2026-07-10", "inbound": 2, "outbound": 1}],
        )


class InboundCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_bounds_the_leads_query_on_both_ends(self, mock_get_db):
        db = MagicMock()
        gte_mock = db.table.return_value.select.return_value.eq.return_value.in_.return_value.is_.return_value.gte
        gte_mock.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        gte_mock.assert_called_with("created_at", "2026-07-10T00:00:00+00:00")
        gte_mock.return_value.lt.assert_called_with("created_at", "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_ist_range_uses_ist_bounds_and_buckets_leads_by_ist_day(self, mock_get_db):
        db = MagicMock()
        gte_mock = (
            db.table.return_value.select.return_value.eq.return_value.in_.return_value.is_.return_value.gte
        )
        gte_mock.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "lead-1",
                    "source": "whatsapp",
                    "ad_campaign_id": None,
                    "segment": "A",
                    "created_at": "2026-07-09T20:00:00+00:00",
                }
            ]
        )
        mock_get_db.return_value = db

        res = self.client.get(
            "/api/v1/analytics/inbound?start=2026-07-10&end=2026-07-10"
            "&timezone=Asia%2FKolkata"
        )

        self.assertEqual(res.status_code, 200)
        gte_mock.assert_called_with("created_at", "2026-07-09T18:30:00+00:00")
        gte_mock.return_value.lt.assert_called_with(
            "created_at", "2026-07-10T18:30:00+00:00"
        )
        self.assertEqual(
            res.json()["daily"],
            [{"day": "2026-07-10", "organic": 1, "ad": 0}],
        )


if __name__ == "__main__":
    unittest.main()
