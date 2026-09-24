"""Routes around the TeleCMI call score: outcome safety gates, flag review, retry,
transcript masking and the admin's scoring-criteria setting."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CALL_ID = "11111111-2222-3333-4444-555555555555"


def _log_db(row):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value
    chain.execute.return_value = MagicMock(data=row)
    return db


class _Base(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        self.as_role("caller", caller_id="caller-1")

    def tearDown(self):
        app.dependency_overrides.clear()

    def as_role(self, role, caller_id=None, permissions=()):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": role, "user_id": "user-1",
            "caller_id": caller_id, "permissions": list(permissions),
        }


class OutcomeGateTests(_Base):
    def _mark(self, row, body):
        db = _log_db(row)
        with patch("app.routes.calls.get_supabase", return_value=db), \
             patch("app.routes.calls.finalize_call_score", return_value={"score": 8.3, "score_status": "scored"}) as fin:
            res = self.client.patch(f"/api/v1/calls/{CALL_ID}/outcome", json=body)
        return res, db, fin

    def test_never_connected_telecmi_call_cannot_be_marked_converted(self):
        row = {"provider": "telecmi", "status": "no_answer", "duration_seconds": 0, "lead_id": None, "caller_id": "caller-1"}
        res, db, _ = self._mark(row, {"outcome": "converted"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("never connected", res.json()["detail"])
        db.table.return_value.update.assert_not_called()

    def test_zero_second_completed_call_is_also_blocked(self):
        row = {"provider": "telecmi", "status": "completed", "duration_seconds": 0, "lead_id": None, "caller_id": "caller-1"}
        res, _, _ = self._mark(row, {"outcome": "interested"})
        self.assertEqual(res.status_code, 400)

    def test_never_connected_call_can_still_be_marked_no_answer(self):
        row = {"provider": "telecmi", "status": "no_answer", "duration_seconds": 0, "lead_id": None, "caller_id": "caller-1"}
        res, _, fin = self._mark(row, {"outcome": "no_answer"})
        self.assertEqual(res.status_code, 200)
        fin.assert_called_once()

    def test_flagged_call_outcome_is_locked(self):
        row = {"provider": "telecmi", "status": "completed", "duration_seconds": 250, "flag_status": "open", "lead_id": None}
        res, _, _ = self._mark(row, {"outcome": "interested"})
        self.assertEqual(res.status_code, 409)

    def test_typed_duration_never_overrides_telecmi_talk_time(self):
        """Otherwise a 4-minute call could be typed down to 10s to dodge scoring."""
        row = {"provider": "telecmi", "status": "completed", "duration_seconds": 240, "lead_id": None, "caller_id": "caller-1"}
        res, db, _ = self._mark(row, {"outcome": "interested", "duration_seconds": 10})
        self.assertEqual(res.status_code, 200)
        written = db.table.return_value.update.call_args.args[0]
        self.assertNotIn("duration_seconds", written)
        self.assertNotIn("score", written, "the score is computed by the scorer, never written here")

    def test_sim_calls_keep_their_typed_duration(self):
        row = {"provider": "sim_basic", "status": "sim_started", "duration_seconds": None, "lead_id": None, "caller_id": "caller-1"}
        res, db, _ = self._mark(row, {"outcome": "interested", "duration_seconds": 95})
        self.assertEqual(db.table.return_value.update.call_args.args[0]["duration_seconds"], 95)

    def test_response_carries_the_new_score(self):
        row = {"provider": "telecmi", "status": "completed", "duration_seconds": 240, "lead_id": None, "caller_id": "caller-1"}
        res, _, _ = self._mark(row, {"outcome": "interested"})
        self.assertEqual((res.json()["score"], res.json()["score_status"]), (8.3, "scored"))
        self.assertNotIn("caller_overall_score", res.json())


class FlagReviewTests(_Base):
    def test_telecaller_without_team_manage_cannot_resolve_a_flag(self):
        res = self.client.post(f"/api/v1/calls/{CALL_ID}/flag", json={"action": "confirm"})
        self.assertEqual(res.status_code, 403)

    def _resolve(self, action, updated_rows):
        self.as_role("owner")
        db = MagicMock()
        update_chain = db.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value
        update_chain.execute.return_value = MagicMock(data=updated_rows)
        card = db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value
        card.execute.return_value = MagicMock(data={"id": CALL_ID, "transcript": "Telecaller: hi\nCustomer: a\nCustomer: bye"})
        with patch("app.routes.calls.get_supabase", return_value=db), \
             patch("app.routes.calls.finalize_call_score") as fin, \
             patch("app.services.notify.notify_user") as notify:
            res = self.client.post(f"/api/v1/calls/{CALL_ID}/flag", json={"action": action})
        return res, db, fin, notify

    def test_dismiss_rescores_and_masks_the_returned_card(self):
        res, db, fin, _ = self._resolve("dismiss", [{"id": CALL_ID, "caller_id": None}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(db.table.return_value.update.call_args.args[0]["flag_status"], "dismissed")
        fin.assert_called_once()
        body = res.json()
        self.assertNotIn("transcript", body)
        self.assertEqual(body["transcript_preview"], {"first": "Telecaller: hi", "last": "Customer: bye", "hidden_lines": 1})

    def test_confirm_records_who_resolved_it(self):
        res, db, _, _ = self._resolve("confirm", [{"id": CALL_ID, "caller_id": None}])
        written = db.table.return_value.update.call_args.args[0]
        self.assertEqual((written["flag_status"], written["flag_resolved_by"]), ("confirmed", "user-1"))

    def test_no_open_flag_is_a_404(self):
        res, _, fin, _ = self._resolve("confirm", [])
        self.assertEqual(res.status_code, 404)
        fin.assert_not_called()

    def test_flag_list_needs_analytics_view(self):
        self.assertEqual(self.client.get("/api/v1/calls/flagged").status_code, 403)

    def test_flag_list_is_masked_and_counts_open_flags(self):
        self.as_role("owner")
        db = MagicMock()
        rows = MagicMock(data=[{"id": CALL_ID, "transcript": "Telecaller: hello"}], count=1)
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = rows
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(count=4)
        with patch("app.routes.calls.get_supabase", return_value=db):
            res = self.client.get("/api/v1/calls/flagged")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["open_count"], 4)
        self.assertEqual(body["data"][0]["transcript_preview"]["first"], "Telecaller: hello")
        self.assertNotIn("transcript", body["data"][0])


class RetryTests(_Base):
    def test_retry_queues_a_failed_call(self):
        with patch("app.routes.calls.get_supabase"), \
             patch("app.routes.calls.retry_call_ai", return_value=True), \
             patch("app.routes.calls.finalize_call_score"), \
             patch("app.routes.calls.run_call_ai") as run:
            res = self.client.post(f"/api/v1/calls/{CALL_ID}/retry-ai")
        self.assertEqual(res.status_code, 200)
        run.assert_called_once_with(CALL_ID)

    def test_retry_without_a_failure_is_a_404(self):
        with patch("app.routes.calls.get_supabase"), patch("app.routes.calls.retry_call_ai", return_value=False):
            self.assertEqual(self.client.post(f"/api/v1/calls/{CALL_ID}/retry-ai").status_code, 404)


class RecentMaskingTests(_Base):
    def test_recent_calls_never_include_the_full_transcript(self):
        db = MagicMock()
        base = db.table.return_value.select.return_value.eq.return_value
        base.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "c1", "transcript": "Telecaller: one\nCustomer: two\nTelecaller: three\nCustomer: four"}]
        )
        with patch("app.routes.calls.get_supabase", return_value=db):
            res = self.client.get("/api/v1/calls/recent")
        row = res.json()["data"][0]
        self.assertNotIn("transcript", row)
        self.assertEqual(row["transcript_preview"], {"first": "Telecaller: one", "last": "Customer: four", "hidden_lines": 2})


class CriteriaSettingTests(_Base):
    def _patch(self, body):
        self.as_role("owner")
        saved = {}
        with patch("app.routes.app_settings.get_telecalling_config", return_value={"enabled": True, "eval_daily_cap": 50}), \
             patch("app.routes.app_settings.save_telecalling_config", side_effect=lambda t, c: saved.update(c)):
            res = self.client.patch("/api/v1/settings/telecalling-config", json=body)
        return res, saved

    def test_at_least_one_criterion_must_stay_selected(self):
        res, saved = self._patch({"score_criteria": []})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(saved, {})

    def test_unknown_criterion_is_rejected(self):
        self.assertEqual(self._patch({"score_criteria": ["charisma"]})[0].status_code, 400)

    def test_criteria_are_saved_in_canonical_order_and_the_old_cap_is_dropped(self):
        res, saved = self._patch({"score_criteria": ["tone", "greeting_quality"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(saved["score_criteria"], ["greeting_quality", "tone"])
        self.assertNotIn("eval_daily_cap", saved)


class WinnersRouteTests(_Base):
    def test_daily_and_monthly_winners_use_the_70_30_formula_and_owner_is_excluded(self):
        self.as_role("owner")
        stats = {
            "A": {"total_calls": 40, "scored_calls": 25, "avg_score": 8.0},
            "B": {"total_calls": 10, "scored_calls": 5, "avg_score": 9.0},
        }
        seen_ids = []

        def fake_stats(db, tenant_id, start, end, caller_ids=None):
            seen_ids.append(caller_ids)
            return stats

        with patch("app.routes.callers.get_supabase"),              patch("app.routes.callers._team_caller_ids", return_value={"A": "Priya", "B": "Ravi"}),              patch("app.routes.callers.period_stats", side_effect=fake_stats):
            res = self.client.get("/api/v1/callers/winners")
        body = res.json()
        self.assertEqual(body["daily"]["name"], "Priya")
        self.assertEqual(body["daily"]["points"], 8.6)
        self.assertEqual(body["monthly"]["caller_id"], "A")
        self.assertEqual(body["monthly"]["min_scored_calls"], 20)
        self.assertEqual(seen_ids, [["A", "B"], ["A", "B"]])

    def test_no_telecallers_means_no_winners(self):
        self.as_role("owner")
        with patch("app.routes.callers.get_supabase"), patch("app.routes.callers._team_caller_ids", return_value={}):
            self.assertEqual(self.client.get("/api/v1/callers/winners").json(), {"daily": None, "monthly": None})


if __name__ == "__main__":
    unittest.main()
