"""Tests for GET /api/v1/analytics/overview -- the tenant home dashboard's
data source. Covers the prior-window trend fields (D6 of the 2026-07-28
dashboard redesign spec): daily_leads_trend_pct, converted_7d_trend_pct,
new_hot_leads_7d / new_hot_leads_7d_trend_pct."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class AnalyticsOverviewTrendTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, leads_rows, prior_leads_rows, msgs_rows,
                 stage_events_rows, prior_stage_events_rows, handover_count=0):
        db = MagicMock()

        leads_tbl = MagicMock()
        leads_chain = leads_tbl.select.return_value.eq.return_value.is_.return_value
        leads_chain.range.return_value.execute.return_value = MagicMock(data=leads_rows)
        # prior-window leads fetch adds .gte().lt()
        leads_chain.gte.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=prior_leads_rows)

        msgs_tbl = MagicMock()
        msgs_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=msgs_rows)

        events_tbl = MagicMock()
        events_chain = events_tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
        events_chain.execute.return_value = MagicMock(data=stage_events_rows)
        # Prior-window fetch is select->eq->eq->gte->lt->execute (a single .gte()
        # call, not two) -- .lt() is chained directly off events_chain, not off
        # events_chain.gte again.
        events_chain.lt.return_value.execute.return_value = MagicMock(data=prior_stage_events_rows)

        def table(name):
            return {"leads": leads_tbl, "messages": msgs_tbl, "lead_stage_events": events_tbl}[name]

        db.table.side_effect = table
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_daily_leads_trend_pct_none_when_no_prior_baseline(self, mock_get_db):
        self._mock_db(mock_get_db, leads_rows=[], prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["daily_leads_trend_pct"])
        self.assertIsNone(body["converted_7d_trend_pct"])
        self.assertIsNone(body["new_hot_leads_7d_trend_pct"])

    @patch("app.routes.analytics.get_supabase")
    def test_ad_attributed_leads_counts_leads_with_ad_campaign_id(self, mock_get_db):
        current_leads = [
            {"id": "l1", "created_at": "2026-07-20T10:00:00+00:00", "segment": "C",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": "camp-1"},
            {"id": "l2", "created_at": "2026-07-20T10:00:00+00:00", "segment": "C",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": None},
        ]
        self._mock_db(mock_get_db, leads_rows=current_leads, prior_leads_rows=[],
                       msgs_rows=[], stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        self.assertEqual(body["ad_attributed_leads"], 1)

    @patch("app.routes.analytics.get_supabase")
    def test_daily_leads_trend_pct_computed_against_prior_window(self, mock_get_db):
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc).date().isoformat()
        prior_day = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()

        current_leads = [{"id": f"l{i}", "created_at": f"{today}T10:00:00+00:00", "segment": "C",
                           "source": "whatsapp", "converted_at": None} for i in range(3)]
        prior_leads = [{"id": f"p{i}", "created_at": f"{prior_day}T10:00:00+00:00", "segment": "C",
                         "source": "whatsapp", "converted_at": None} for i in range(2)]

        self._mock_db(mock_get_db, leads_rows=current_leads, prior_leads_rows=prior_leads,
                       msgs_rows=[], stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        # 3 current vs 2 prior -> +50%
        self.assertEqual(body["daily_leads_trend_pct"], 50)

    @patch("app.routes.analytics.get_supabase")
    def test_converted_7d_trend_uses_full_lead_population_not_just_prior_created(self, mock_get_db):
        """Regression: prior_converted_7d must scan the full leads_rows
        population bounded to the prior window, not leads *created* in the
        prior window (a lead can be created weeks earlier and convert this
        week) -- and must not double-count conversions that already landed
        in the current window's own converted_7d."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        prior_window_conversion = now - timedelta(days=10)  # inside prior window (7d range -> [-14d, -7d))
        current_window_conversion = now - timedelta(days=2)  # inside current window, must NOT count as prior

        leads_rows = [
            # created 30 days ago (outside both windows) but converted inside
            # the PRIOR window -- must count.
            {"id": "l1", "created_at": (now - timedelta(days=30)).isoformat(),
             "converted_at": prior_window_conversion.isoformat(), "segment": "A", "source": "whatsapp"},
            # created 30 days ago, converted inside the CURRENT window --
            # already counted in converted_7d, must NOT also land in prior_converted_7d.
            {"id": "l2", "created_at": (now - timedelta(days=30)).isoformat(),
             "converted_at": current_window_conversion.isoformat(), "segment": "A", "source": "whatsapp"},
        ]
        self._mock_db(mock_get_db, leads_rows=leads_rows, prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        self.assertEqual(body["converted_7d"], 1)  # only l2
        # prior=1 (l1), current=1 (l2) -> 0% change
        self.assertEqual(body["converted_7d_trend_pct"], 0)

    @patch("app.routes.analytics.get_supabase")
    def test_new_hot_leads_7d_counted_from_lead_stage_events(self, mock_get_db):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        stage_events = [
            {"lead_id": "l1", "to_segment": "A", "created_at": f"{today}T09:00:00+00:00"},
            {"lead_id": "l2", "to_segment": "A", "created_at": f"{today}T11:00:00+00:00"},
        ]
        self._mock_db(mock_get_db, leads_rows=[], prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=stage_events, prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        self.assertEqual(body["new_hot_leads_7d"], 2)
        self.assertIsInstance(body["new_hot_leads_7d_daily"], list)
        self.assertIsNone(body["new_hot_leads_7d_trend_pct"])  # empty prior window

    @patch("app.routes.analytics.get_supabase")
    def test_channel_breakdown_today_and_ad_attributed_today_only_count_todays_leads(self, mock_get_db):
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc).date().isoformat()
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()

        leads_rows = [
            {"id": "l1", "created_at": f"{today}T09:00:00+00:00", "segment": "A",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": "camp-1"},
            {"id": "l2", "created_at": f"{today}T10:00:00+00:00", "segment": "B",
             "source": "instagram", "converted_at": None, "ad_campaign_id": None},
            {"id": "l3", "created_at": f"{yesterday}T10:00:00+00:00", "segment": "C",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": "camp-2"},
        ]
        self._mock_db(mock_get_db, leads_rows=leads_rows, prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        # All 3 leads count toward the all-time fields.
        self.assertEqual(body["channel_breakdown"]["whatsapp"], 2)
        self.assertEqual(body["ad_attributed_leads"], 2)
        # Only l1/l2 (today) count toward the today-scoped fields; yesterday's
        # l3 (whatsapp, ad-attributed) must not leak in.
        self.assertEqual(body["channel_breakdown_today"]["whatsapp"], 1)
        self.assertEqual(body["channel_breakdown_today"]["instagram"], 1)
        self.assertEqual(body["ad_attributed_leads_today"], 1)


if __name__ == "__main__":
    unittest.main()
