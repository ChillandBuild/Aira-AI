"""PATCH /calls/{id}/outcome (wrap-up v2) and GET /calls/wrapup-context."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import calls
from app.services import call_wrapup as cw
from app.services.deals import DealError
from tests.fake_supabase import FakeSupabase

CALL_ID = "11111111-2222-3333-4444-555555555555"
LEAD_ID = "99999999-8888-7777-6666-555555555555"
WARM = {"manual_status": "connected", "outcome": "interested_needs_time", "notes": "wants the brochure",
        "next_action_at": "2030-01-06T10:00:00+05:30"}
CLOUD = {"provider": "telecmi", "status": "completed", "duration_seconds": 240, "lead_id": None, "caller_id": "caller-1"}
SIM = {"provider": "sim_basic", "status": "sim_started", "duration_seconds": None, "lead_id": None, "caller_id": "caller-1"}


def _log_db(row):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value
    chain.execute.return_value = MagicMock(data=row)
    return db


class _Base(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "caller", "user_id": "user-1", "caller_id": "caller-1",
            "permissions": ["telecalling.dialer"],
        }

    def tearDown(self):
        app.dependency_overrides.clear()


class SaveWrapupTests(_Base):
    def _save(self, row, body, apply=None):
        apply = apply or AsyncMock(return_value={"call_status": "warm", "next_action_at": "2030-01-06T04:30:00+00:00", "deal_id": None})
        crm_task = AsyncMock()
        with patch("app.routes.calls.get_supabase", return_value=_log_db(row)), \
             patch("app.routes.calls.apply_wrapup", apply), \
             patch("app.routes.calls.mark_crm_update_task", crm_task), \
             patch("app.routes.calls.finalize_call_score", return_value={"score": 72.5, "score_status": "provisional"}):
            res = self.client.patch(f"/api/v1/calls/{CALL_ID}/outcome", json=body)
        return res, apply, crm_task

    def test_never_connected_cloud_call_cannot_be_marked_connected(self):
        res, apply, _ = self._save({**CLOUD, "status": "no_answer", "duration_seconds": 0}, WARM)
        self.assertEqual(res.status_code, 400)
        self.assertIn("never connected", res.json()["detail"])
        apply.assert_not_awaited()

    def test_zero_second_completed_call_is_blocked_too(self):
        res, _, _ = self._save({**CLOUD, "duration_seconds": 0}, WARM)
        self.assertEqual(res.status_code, 400)

    def test_never_connected_call_saves_not_picked(self):
        res, apply, _ = self._save({**CLOUD, "status": "no_answer", "duration_seconds": 0}, {"manual_status": "not_picked"})
        self.assertEqual(res.status_code, 200)
        wrapup = apply.await_args.kwargs["wrapup"]
        self.assertEqual((wrapup["manual_status"], wrapup["outcome"], wrapup["next_action_at"]), ("not_picked", None, None))

    def test_telecmi_talk_time_is_never_overridden(self):
        _, apply, _ = self._save(CLOUD, {**WARM, "duration_seconds": 10})
        self.assertEqual(apply.await_args.kwargs["log_extra"], {})

    def test_sim_keeps_typed_timing(self):
        body = {**WARM, "duration_seconds": 95, "manual_started_at": "2026-09-27T08:00:00+00:00",
                "manual_ended_at": "2026-09-27T08:01:35+00:00"}
        _, apply, _ = self._save(SIM, body)
        self.assertEqual(apply.await_args.kwargs["log_extra"], {
            "duration_seconds": 95, "manual_started_at": "2026-09-27T08:00:00+00:00",
            "manual_ended_at": "2026-09-27T08:01:35+00:00",
        })

    def test_naive_time_is_read_as_ist(self):
        _, apply, _ = self._save(CLOUD, {**WARM, "next_action_at": "2030-01-06T10:00:00"})
        self.assertEqual(apply.await_args.kwargs["wrapup"]["next_action_at"], datetime(2030, 1, 6, 4, 30, tzinfo=timezone.utc))

    def test_response_carries_status_reminder_and_score(self):
        res, _, _ = self._save(CLOUD, WARM)
        body = res.json()
        self.assertEqual((body["call_status"], body["next_action_at"], body["score"], body["score_status"]),
                         ("warm", "2030-01-06T04:30:00+00:00", 72.5, "provisional"))

    def test_rule_errors_are_400s(self):
        res, _, _ = self._save(CLOUD, {"manual_status": "connected", "outcome": "interested_booked", "next_action_at": "2030-01-06T10:00:00+05:30"})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "Add a short note for this result."))

    def test_deal_errors_are_400s(self):
        apply = AsyncMock(side_effect=DealError("No price for Pen"))
        res, _, _ = self._save(CLOUD, {"manual_status": "connected", "outcome": "converted", "notes": "sold",
                                       "products": [{"catalog_item_id": "pen", "qty": 1}]}, apply=apply)
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "No price for Pen"))

    def test_old_payload_shape_is_rejected(self):
        res, _, _ = self._save(CLOUD, {"outcome": "interested"})
        self.assertEqual(res.status_code, 422)

    def test_unknown_call_is_404(self):
        res, _, _ = self._save(None, WARM)
        self.assertEqual(res.status_code, 404)

    def test_cloud_wrapup_queues_the_crm_check(self):
        _, _, crm_task = self._save(CLOUD, WARM)
        crm_task.assert_awaited_once_with(CALL_ID)

    def test_sim_wrapup_does_not_queue_the_crm_check(self):
        _, _, crm_task = self._save(SIM, WARM)
        crm_task.assert_not_awaited()


class LiteralContractTests(unittest.TestCase):
    def test_route_literals_match_the_rules_module(self):
        self.assertEqual(set(get_args(calls.ConnectValue)), set(cw.CONNECTS))
        self.assertEqual(set(get_args(calls.OutcomeValue)), set(cw.OUTCOMES))
        self.assertEqual(set(get_args(calls.ReasonValue)), set(cw.REASONS))
        self.assertEqual(set(get_args(calls.LanguageValue)), set(cw.LANGUAGES))


class WrapupContextTests(_Base):
    def setUp(self):
        super().setUp()
        self.db = FakeSupabase()
        self.db.add("call_logs", id=CALL_ID, tenant_id="tenant-1", provider="telecmi", status="no_answer",
                    duration_seconds=0, lead_id=LEAD_ID, manual_status=None, created_at="2026-09-27T08:00:00+00:00")
        for created_at in ("2026-09-27T06:00:00+00:00", "2026-09-27T05:00:00+00:00"):
            self.db.add("call_logs", tenant_id="tenant-1", lead_id=LEAD_ID, manual_status="busy", status="completed", created_at=created_at)

    def _get(self, qs):
        with patch("app.routes.calls.get_supabase", return_value=self.db):
            return self.client.get(f"/api/v1/calls/wrapup-context?{qs}")

    def test_cloud_missed_call_is_prefilled_not_picked(self):
        body = self._get(f"call_log_id={CALL_ID}").json()
        self.assertEqual((body["connect_prefill"], body["never_connected"], body["failed_before"]), ("not_picked", True, 2))
        # third failure in a row: every suggestion is tomorrow 10:00 IST
        self.assertEqual(len(set(body["retry_suggestions"].values())), 1)

    def test_lead_only_context_for_a_sim_call_not_logged_yet(self):
        body = self._get(f"lead_id={LEAD_ID}").json()
        self.assertEqual((body["connect_prefill"], body["failed_before"]), (None, 0))

    def test_another_tenants_call_is_404(self):
        self.db.rows("call_logs")[0]["tenant_id"] = "other"
        self.assertEqual(self._get(f"call_log_id={CALL_ID}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
