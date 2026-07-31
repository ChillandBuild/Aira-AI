"""Tests for GET /api/v1/analytics/compare -- period comparison endpoint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class AnalyticsCompareTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, summaries, daily_leads, daily_messages,
                 money=None, movement=None, response=None, heatmap=None):
        """Each list is per-period: index 0 = current, 1 = previous."""
        money = money if money is not None else [[], []]
        movement = movement if movement is not None else [[], []]
        response = response if response is not None else [[], []]
        heatmap = heatmap if heatmap is not None else [[], []]
        db = MagicMock()

        queues = {
            "analytics_period_summary": summaries,
            "analytics_daily_leads": daily_leads,
            "analytics_daily_messages": daily_messages,
            "analytics_period_money": money,
            "analytics_segment_movement": movement,
            "analytics_response_times": response,
            "analytics_lead_arrival_heatmap": heatmap,
        }

        def rpc(name, params):
            if name not in queues:
                raise AssertionError(f"unexpected rpc {name}")
            result = MagicMock()
            result.execute.return_value = MagicMock(data=queues[name].pop(0))
            return result

        db.rpc.side_effect = rpc
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_compare_returns_both_periods_with_deltas(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[
                [{"new_leads": 20, "inbound_leads": 20, "outbound_leads": 0, "hot": 4,
                  "warm": 6, "cold": 9, "disqualified": 1, "avg_score": 6.0,
                  "messages_in": 100, "messages_out": 120, "ai_replies": 118,
                  "human_replies": 2, "converted": 0}],
                [{"new_leads": 10, "inbound_leads": 10, "outbound_leads": 0, "hot": 2,
                  "warm": 3, "cold": 5, "disqualified": 0, "avg_score": 5.0,
                  "messages_in": 50, "messages_out": 60, "ai_replies": 60,
                  "human_replies": 0, "converted": 0}],
            ],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16&comparison=previous")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["current"]["start"], "2026-07-15")
        self.assertEqual(body["previous"]["start"], "2026-07-13")
        self.assertEqual(body["metrics"]["new_leads"]["current"], 20)
        self.assertEqual(body["metrics"]["new_leads"]["previous"], 10)
        self.assertEqual(body["metrics"]["new_leads"]["delta_pct"], 100)

    @patch("app.routes.analytics.get_supabase")
    def test_comparison_off_returns_only_current_period_data(self, mock_get_db):
        db = self._mock_db(
            mock_get_db,
            summaries=[[{"new_leads": 20}]],
            daily_leads=[[]],
            daily_messages=[[]],
        )

        res = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-10&end=2026-07-12"
            "&comparison=off"
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["previous"])
        self.assertEqual(body["metrics"], {})
        self.assertEqual(body["money_metrics"], {})
        self.assertEqual(body["response_metrics"], {})
        self.assertEqual(body["movement_metrics"], {})
        self.assertEqual(body["series"], {})
        self.assertEqual(db.rpc.call_count, 7)

    @patch("app.routes.analytics.get_supabase")
    def test_custom_comparison_uses_only_supplied_comparison_dates(self, mock_get_db):
        db = self._mock_db(
            mock_get_db,
            summaries=[[{"new_leads": 20}], [{"new_leads": 10}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )

        res = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-10&end=2026-07-12"
            "&comparison=custom&comparison_start=2026-06-01&comparison_end=2026-06-05"
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["previous"]["start"], "2026-06-01")
        self.assertEqual(res.json()["previous"]["end"], "2026-06-05")
        summary_params = [
            call.args[1]
            for call in db.rpc.call_args_list
            if call.args[0] == "analytics_period_summary"
        ]
        self.assertCountEqual(
            summary_params,
            [
                {
                    "p_tenant_id": "tenant-1",
                    "p_start": "2026-07-09T18:30:00+00:00",
                    "p_end": "2026-07-12T18:30:00+00:00",
                },
                {
                    "p_tenant_id": "tenant-1",
                    "p_start": "2026-05-31T18:30:00+00:00",
                    "p_end": "2026-06-05T18:30:00+00:00",
                },
            ],
        )

    @patch("app.routes.analytics.get_supabase")
    def test_custom_comparison_requires_a_complete_valid_range(self, mock_get_db):
        mock_get_db.return_value = MagicMock()

        incomplete = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-10&end=2026-07-12"
            "&comparison=custom&comparison_start=2026-06-01"
        )
        reversed_range = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-10&end=2026-07-12"
            "&comparison=custom&comparison_start=2026-06-05&comparison_end=2026-06-01"
        )

        self.assertEqual(incomplete.status_code, 400)
        self.assertEqual(reversed_range.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_series_is_zero_filled_for_every_day_in_range(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[
                [{"day": "2026-07-16", "inbound": 5, "outbound": 0,
                  "hot": 1, "warm": 2, "cold": 2, "disqualified": 0}],
                [],
            ],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16&comparison=previous")
        series = res.json()["series"]["leads_inbound"]
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["current"], 0)
        self.assertEqual(series[1]["current"], 5)

    @patch("app.routes.analytics.get_supabase")
    def test_money_block_carries_cost_per_lead_and_its_delta(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
            money=[
                [{"spend": 1000, "impressions": 100, "clicks": 10,
                  "ad_leads": 20, "ad_hot_leads": 4,
                  "cost_per_lead": 50, "cost_per_hot_lead": 250}],
                [{"spend": 800, "impressions": 80, "clicks": 8,
                  "ad_leads": 8, "ad_hot_leads": 2,
                  "cost_per_lead": 100, "cost_per_hot_lead": 400}],
            ],
        )
        body = self.client.get("/api/v1/analytics/compare?preset=custom"
                               "&start=2026-07-15&end=2026-07-16&comparison=previous").json()
        self.assertEqual(body["current"]["money"]["cost_per_lead"], 50)
        # Cost halved: that is a -50% change, and cheaper is better.
        self.assertEqual(body["money_metrics"]["cost_per_lead"]["delta_pct"], -50)

    @patch("app.routes.analytics.get_supabase")
    def test_movement_block_classifies_promotions_and_demotions(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
            movement=[
                [{"from_segment": "C", "to_segment": "A", "total": 10},
                 {"from_segment": "A", "to_segment": "C", "total": 3}],
                [],
            ],
        )
        body = self.client.get("/api/v1/analytics/compare?preset=custom"
                               "&start=2026-07-15&end=2026-07-16&comparison=previous").json()
        movement = body["current"]["movement"]
        self.assertEqual(movement["promoted"], 10)
        self.assertEqual(movement["promoted_to_hot"], 10)
        self.assertEqual(movement["demoted"], 3)

    @patch("app.routes.analytics.get_supabase")
    def test_response_block_carries_percentiles(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
            response=[
                [{"inbound_total": 100, "answered": 100,
                  "p50_seconds": 10.4, "p90_seconds": 22.9}],
                [{"inbound_total": 50, "answered": 48,
                  "p50_seconds": 20.0, "p90_seconds": 60.0}],
            ],
        )
        body = self.client.get("/api/v1/analytics/compare?preset=custom"
                               "&start=2026-07-15&end=2026-07-16&comparison=previous").json()
        self.assertEqual(body["current"]["response"]["p50_seconds"], 10.4)
        self.assertEqual(body["response_metrics"]["p50_seconds"]["delta_pct"], -48)

    @patch("app.routes.analytics.get_supabase")
    def test_missing_optional_blocks_do_not_break_the_response(self, mock_get_db):
        """A tenant with no ad spend and no segment events must still get 200."""
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16&comparison=previous")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["current"]["money"], {})
        self.assertEqual(body["current"]["movement"]["promoted"], 0)
        self.assertEqual(body["money_metrics"]["spend"]["current"], 0)

    @patch("app.routes.analytics.get_supabase")
    def test_export_returns_csv_with_a_header_row(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare/export?preset=custom"
                              "&start=2026-07-15&end=2026-07-16&comparison=previous")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        body = res.content.decode()
        self.assertIn("day_index,current_date,current_leads_inbound", body)
        self.assertEqual(len(body.strip().splitlines()), 3)  # header + 2 days

    @patch("app.routes.analytics.get_supabase")
    def test_export_rejects_comparison_off(self, mock_get_db):
        mock_get_db.return_value = MagicMock()

        res = self.client.get(
            "/api/v1/analytics/compare/export?preset=custom&start=2026-07-15&end=2026-07-16"
            "&comparison=off"
        )

        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_unknown_preset_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=forever")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_engagement_rate_flows_through_to_the_metrics_block(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[
                [{"new_leads": 20, "engagement_rate": 65}],
                [{"new_leads": 10, "engagement_rate": 50}],
            ],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16&comparison=previous"
        ).json()
        self.assertEqual(body["metrics"]["engagement_rate"]["current"], 65)
        self.assertEqual(body["metrics"]["engagement_rate"]["previous"], 50)
        self.assertEqual(body["metrics"]["engagement_rate"]["delta_pct"], 30)

    @patch("app.routes.analytics.get_supabase")
    def test_daily_segment_mix_is_returned_for_the_current_period(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[
                [{"day": "2026-07-16", "inbound": 3, "outbound": 0,
                  "hot": 1, "warm": 1, "cold": 1, "disqualified": 0}],
                [],
            ],
            daily_messages=[[], []],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16&comparison=previous"
        ).json()
        mix = body["current"]["daily_segment_mix"]
        self.assertEqual(len(mix), 2)
        self.assertEqual(mix[1], {"day": "2026-07-16", "hot": 1, "warm": 1, "cold": 1, "disqualified": 0})
        self.assertEqual(mix[0], {"day": "2026-07-15", "hot": 0, "warm": 0, "cold": 0, "disqualified": 0})

    @patch("app.routes.analytics.get_supabase")
    def test_heatmap_is_returned_for_the_current_period(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
            heatmap=[
                [{"dow": 1, "hour": 10, "total": 4}],
                [],
            ],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16"
        ).json()
        self.assertEqual(body["current"]["heatmap"], [{"dow": 1, "hour": 10, "total": 4}])

if __name__ == "__main__":
    unittest.main()
