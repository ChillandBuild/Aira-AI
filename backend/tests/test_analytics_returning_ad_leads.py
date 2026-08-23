"""Returning-ad-lead counting and the IST calendar-day fixes that went with it.

"New Leads Today" counted leads by created_at only, so a lead from months ago
who clicked a fresh ad today appeared in no lead count at all. The overview now
also returns `returning_ad_leads_daily`, and several endpoints that claimed to
report "today" were anchored to UTC midnight for an IST tenant.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes.analytics import IST_OFFSET, _today_start


def _ist_today() -> str:
    return (datetime.now(timezone.utc) + IST_OFFSET).date().isoformat()


class ReturningAdLeadsOverviewTests(unittest.TestCase):
    """GET /analytics/overview exposes the returning-ad-lead series."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, returning_rows, leads_rows=None):
        db = MagicMock()

        leads_tbl = MagicMock()
        leads_chain = leads_tbl.select.return_value.eq.return_value.is_.return_value
        leads_chain.range.return_value.execute.return_value = MagicMock(data=leads_rows or [])
        leads_chain.gte.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])

        msgs_tbl = MagicMock()
        msgs_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])

        db.table.side_effect = lambda name: {"leads": leads_tbl, "messages": msgs_tbl}[name]

        self.rpc_calls = {}

        def rpc(name, params=None):
            self.rpc_calls[name] = params
            result = MagicMock()
            data = returning_rows if name == "analytics_daily_returning_ad_leads" else []
            result.execute.return_value = MagicMock(data=data)
            return result

        db.rpc.side_effect = rpc
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_returning_series_is_returned_for_every_day_in_the_window(self, mock_get_db):
        self._mock_db(mock_get_db, returning_rows=[])

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()

        series = body["returning_ad_leads_daily"]
        self.assertEqual(len(series), 7)
        self.assertEqual([d["count"] for d in series], [0] * 7)
        self.assertEqual(series[-1]["day"], _ist_today())

    @patch("app.routes.analytics.get_supabase")
    def test_returning_count_lands_on_its_ist_day(self, mock_get_db):
        today = _ist_today()
        self._mock_db(
            mock_get_db,
            returning_rows=[{"day": today, "returning_leads": 3}],
        )

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()

        by_day = {d["day"]: d["count"] for d in body["returning_ad_leads_daily"]}
        self.assertEqual(by_day[today], 3)

    @patch("app.routes.analytics.get_supabase")
    def test_days_outside_the_window_are_discarded_not_appended(self, mock_get_db):
        stale = (datetime.now(timezone.utc) + IST_OFFSET - timedelta(days=40)).date().isoformat()
        self._mock_db(mock_get_db, returning_rows=[{"day": stale, "returning_leads": 9}])

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()

        series = body["returning_ad_leads_daily"]
        self.assertEqual(len(series), 7)
        self.assertNotIn(stale, [d["day"] for d in series])

    @patch("app.routes.analytics.get_supabase")
    def test_rpc_window_starts_at_ist_midnight_of_the_oldest_day(self, mock_get_db):
        """A rolling "now - 7 days" start would clip the oldest bucket to a
        partial day, so the series is anchored to the IST day list instead."""
        self._mock_db(mock_get_db, returning_rows=[])

        self.client.get("/api/v1/analytics/overview?range=7d")

        params = self.rpc_calls["analytics_daily_returning_ad_leads"]
        self.assertEqual(params["p_timezone"], "Asia/Kolkata")
        start = datetime.fromisoformat(params["p_start"])
        oldest_ist_day = (datetime.now(timezone.utc) + IST_OFFSET).date() - timedelta(days=6)
        self.assertEqual((start + IST_OFFSET).date(), oldest_ist_day)
        self.assertEqual((start + IST_OFFSET).time(), datetime.min.time())

    @patch("app.routes.analytics.get_supabase")
    def test_fresh_lead_count_is_untouched_by_the_new_series(self, mock_get_db):
        """Fresh and Returned are added together in the card, so double
        counting here would inflate the headline number."""
        now = datetime.now(timezone.utc)
        self._mock_db(
            mock_get_db,
            returning_rows=[{"day": _ist_today(), "returning_leads": 5}],
            leads_rows=[
                {"id": "l1", "created_at": now.isoformat(), "segment": "C",
                 "source": "whatsapp", "converted_at": None, "ad_campaign_id": None},
            ],
        )

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()

        self.assertEqual(body["daily_leads"][-1]["count"], 1)
        self.assertEqual(body["returning_ad_leads_daily"][-1]["count"], 5)


class IstCalendarDayTests(unittest.TestCase):
    """Endpoints that report "today" for an IST tenant must not use UTC
    midnight -- that filed 00:00-05:30 IST under the previous day."""

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_today_start_is_ist_midnight(self):
        start = datetime.fromisoformat(_today_start())
        local = start + IST_OFFSET
        self.assertEqual(local.time(), datetime.min.time())
        self.assertEqual(local.date().isoformat(), _ist_today())

    @staticmethod
    def _bounds(db, method):
        """Every timestamp passed to .gte()/.lt() anywhere in the query chain.

        A single MagicMock backs all tables, so call_args only holds whichever
        query was built last -- collect them all and assert membership instead.
        """
        found = []
        for name, args, _ in db.mock_calls:
            if name.split(".")[-1] == method and len(args) == 2:
                try:
                    found.append(datetime.fromisoformat(args[1]))
                except (TypeError, ValueError):
                    continue
        return found

    @staticmethod
    def _ist_naive(dt):
        return (dt + IST_OFFSET).replace(tzinfo=None).isoformat()

    @patch("app.routes.analytics.get_supabase")
    def test_caller_timeline_day_window_is_an_ist_day(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        res = self.client.get(
            "/api/v1/analytics/caller-timeline"
            "?caller_id=11111111-1111-1111-1111-111111111111&date=2026-08-20"
        )
        self.assertEqual(res.status_code, 200)

        starts = [self._ist_naive(d) for d in self._bounds(db, "gte")]
        ends = [self._ist_naive(d) for d in self._bounds(db, "lt")]
        self.assertIn("2026-08-20T00:00:00", starts)
        self.assertIn("2026-08-21T00:00:00", ends)

    @patch("app.routes.analytics.get_supabase")
    def test_telecalling_custom_range_uses_ist_day_bounds(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/telecalling?from=2026-08-01&to=2026-08-07")
        self.assertEqual(res.status_code, 200)

        starts = [self._ist_naive(d) for d in self._bounds(db, "gte")]
        ends = [self._ist_naive(d) for d in self._bounds(db, "lt")]
        # Inclusive 1 Aug through 7 Aug in IST -- not 1 Aug 05:30 to 8 Aug
        # 05:30, which is what UTC-midnight bounds produced.
        self.assertIn("2026-08-01T00:00:00", starts)
        self.assertIn("2026-08-08T00:00:00", ends)


if __name__ == "__main__":
    unittest.main()
