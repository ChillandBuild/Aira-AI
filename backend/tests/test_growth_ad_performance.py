"""Tests for build_ad_performance's today/7d-windowed fields (2026-08-01) --
the dashboard home 'Ad Spend' card. Rates are windowed to 7 days rather than
campaign lifetime so a single day's tiny lead count can't swing them wildly;
see decisions/log.md 2026-08-01."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.growth import build_ad_performance


class BuildAdPerformanceTests(unittest.TestCase):
    def _mock_db(self, campaigns, leads, events=None):
        db = MagicMock()
        campaigns_chain = db.table.return_value.select.return_value.eq.return_value.order.return_value
        campaigns_chain.execute.return_value = MagicMock(data=campaigns)

        leads_chain = db.table.return_value.select.return_value.eq.return_value
        leads_chain.execute.return_value = MagicMock(data=leads)

        events_chain = db.table.return_value.select.return_value.in_.return_value.eq.return_value.order.return_value
        events_chain.execute.return_value = MagicMock(data=events or [])

        return db

    def test_no_campaigns_returns_zeroed_today_and_7d_fields(self):
        db = self._mock_db(campaigns=[], leads=[])
        result = build_ad_performance(tenant_id="tenant-1", db=db)
        self.assertEqual(result["totals"]["tracked_leads_today"], 0)
        self.assertEqual(result["totals"]["conversion_rate_7d"], 0)
        self.assertEqual(result["totals"]["progressive_rate_7d"], 0)

    def test_tracked_leads_today_only_counts_leads_created_today(self):
        now = datetime.now(timezone.utc)
        # Stamp both leads from `now` rather than building "{utc_date}T09:00:00+00:00".
        # build_ad_performance buckets by IST calendar date (growth.py's IST_OFFSET),
        # so between 18:30 and 00:00 UTC the UTC date is already a day behind IST and
        # a "today" fixture built that way lands on the previous IST day.
        today_ts = now.isoformat()
        old_ts = (now - timedelta(days=30)).isoformat()

        campaigns = [{"id": "camp-1", "platform": "facebook", "campaign_name": "C1",
                      "external_campaign_id": "ext-1", "spend_inr": 100}]
        leads = [
            {"id": "l1", "ad_campaign_id": "camp-1", "segment": "C",
             "converted_at": None, "created_at": today_ts,
             "ad_name": None, "ad_set_name": None},
            {"id": "l2", "ad_campaign_id": "camp-1", "segment": "C",
             "converted_at": None, "created_at": old_ts,
             "ad_name": None, "ad_set_name": None},
        ]
        db = self._mock_db(campaigns=campaigns, leads=leads)
        result = build_ad_performance(tenant_id="tenant-1", db=db)

        self.assertEqual(result["totals"]["tracked_leads"], 2)
        self.assertEqual(result["totals"]["tracked_leads_today"], 1)

    def test_conversion_rate_7d_excludes_leads_outside_the_window(self):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=2)
        stale = now - timedelta(days=30)

        campaigns = [{"id": "camp-1", "platform": "facebook", "campaign_name": "C1",
                      "external_campaign_id": "ext-1", "spend_inr": 100}]
        leads = [
            # Inside the 7d window, converted -- counts toward the rate.
            {"id": "l1", "ad_campaign_id": "camp-1", "segment": "A",
             "converted_at": recent.isoformat(), "created_at": recent.isoformat(),
             "ad_name": None, "ad_set_name": None},
            # Outside the 7d window -- must not dilute the rate's denominator.
            {"id": "l2", "ad_campaign_id": "camp-1", "segment": "D",
             "converted_at": None, "created_at": stale.isoformat(),
             "ad_name": None, "ad_set_name": None},
        ]
        db = self._mock_db(campaigns=campaigns, leads=leads)
        result = build_ad_performance(tenant_id="tenant-1", db=db)

        self.assertEqual(result["totals"]["conversion_rate_7d"], 1.0)


if __name__ == "__main__":
    unittest.main()
