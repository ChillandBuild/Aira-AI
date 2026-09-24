"""Behavioural tests for the TeleCMI CHUB two-leg CDR webhook.

The payloads below are the sample CDRs from the CHUB docs verbatim
(https://doc.telecmi.com/chub/docs/outgoing-answered and /outgoing-missed),
with only `extra_params` swapped to carry our call_log_id the way
initiate_click2call actually sends it.

The point of these tests is that CHUB delivers TWO CDRs per outbound
click2call — leg 'a' (agent) and leg 'b' (customer) — sharing one request_id.
Leg B is authoritative; leg A must never decide the call's status, duration,
or billing.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

CALL_LOG_ID = "11111111-2222-3333-4444-555555555555"
TENANT_ID = "tenant-1"
WEBHOOK_SECRET = "test-webhook-secret"

# Docs sample, leg A: `to` is the AGENT's number and answeredsec (15) counts
# from when the agent picked up — it includes the customer's ring time.
LEG_A_ANSWERED = {
    "virtual_number": "440000000000",
    "call_id": "c4504776-d91e-123b-29a7-56000429abc3",
    "custom": '{"crm":"true"}',
    "leg": "a",
    "type": "cdr",
    "appid": 2222223,
    "to": 442000000000,
    "cmiuuid": "10ee0eb6-c417-4f5a-b122-bffe28f96eae",
    "status": "answered",
    "user": "202_2222223",
    "time": 1650630551178,
    "direction": "outbound",
    "answeredsec": 15,
    "hangup_reason": "recv_bye",
    "request_id": "c0Sq3mbykoHgVgLfyWTr6cV6HB5Z0Fk4AXpZFkOClSr",
    "extra_params": '{"call_log_id":"%s"}' % CALL_LOG_ID,
}

# Docs sample, leg B: the customer leg. answeredsec (6) is the real talk time,
# and this is the only leg carrying record/filename.
LEG_B_ANSWERED = {
    **LEG_A_ANSWERED,
    "leg": "b",
    "to": 919342012824,
    "cmiuuid": "0da4f02e-6ece-42e4-989b-1e6766b5a81e",
    "answeredsec": 6,
    "hangup_reason": "sent_bye",
    "record": True,
    "filename": "16506305548176941220057791_2222223.mp3",
}

# Docs sample: agent never picked up, so the customer was never dialled.
LEG_A_MISSED = {
    **LEG_A_ANSWERED,
    "status": "missed",
    "hangup_reason": "recv_cancel",
    "answeredsec": None,
}


class _Result:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    """Records the chained PostgREST-style calls the route makes."""

    def __init__(self, recorder, table):
        self.rec = recorder
        self.table_name = table
        self.op = None
        self.payload = None
        self.filters = {}

    def select(self, *a, **k):
        self.op = "select"
        self.count_mode = k.get("count")
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def in_(self, col, vals):
        self.filters[f"in:{col}"] = vals
        return self

    def gte(self, col, val):
        self.filters[f"gte:{col}"] = val
        return self

    def maybe_single(self):
        return self

    def execute(self):
        self.rec.ops.append(
            {"table": self.table_name, "op": self.op, "payload": self.payload, "filters": self.filters}
        )
        if self.op == "select":
            return _Result(self.rec.select_data.get(self.table_name), count=0)
        if self.op == "insert":
            return _Result([{"id": "new-lead-id"}])
        return _Result([])


class FakeDB:
    def __init__(self, call_log_row, lead_row=None):
        self.ops = []
        self.select_data = {"call_logs": call_log_row, "leads": lead_row, "callers": None}

    def table(self, name):
        return _Query(self, name)

    def updates_to(self, table):
        return [o["payload"] for o in self.ops if o["table"] == table and o["op"] == "update"]


def _call_log(**overrides):
    row = {
        "id": CALL_LOG_ID,
        "caller_id": "caller-1",
        "lead_id": "lead-1",
        "tenant_id": TENANT_ID,
        "status": "initiated",
        "duration_seconds": None,
    }
    row.update(overrides)
    return row


class TeleCmiCdrLegTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.metered = []
        self.queued = []
        self.runs = []
        self.finalized = []

        # Key-aware, so `telecmi_recording_base_url` stays unset (the default
        # documented endpoint applies) instead of every key returning one value.
        settings_map = {
            "telecmi_webhook_secret": WEBHOOK_SECRET,
            "telecmi_app_id": "33337312",
            "telecmi_secret": "app-secret-xyz",
            "telecmi_recording_base_url": None,
        }

        patches = [
            patch("app.routes.calls.get_setting", side_effect=lambda key, **kw: settings_map.get(key)),
            patch("app.routes.calls.meter", side_effect=lambda db, t, k, q: self.metered.append((t, k, q))),
            patch("app.routes.calls.finalize_call_score", side_effect=lambda db, cid: self.finalized.append(cid)),
            patch("app.routes.calls.get_telecalling_config", return_value={"targets": {}}),
            patch(
                "app.routes.calls.queue_call_ai",
                side_effect=lambda db, cid, filename: self.queued.append((cid, filename)),
            ),
            patch(
                "app.routes.calls.run_call_ai",
                side_effect=lambda cid, appid=None: self.runs.append((cid, appid)),
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _post(self, cdr, db):
        with patch("app.routes.calls.get_supabase", return_value=db):
            return self.client.post(
                f"/api/v1/calls/telecmi-cdr/{TENANT_ID}",
                params={"webhook_secret": WEBHOOK_SECRET},
                json=cdr,
            )

    # ── leg A must not decide the call ────────────────────────────────

    def test_leg_a_answered_does_not_complete_the_call(self):
        """The agent answering is not the customer answering."""
        db = FakeDB(_call_log())
        res = self._post(LEG_A_ANSWERED, db)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(db.updates_to("call_logs"), [], "leg A answered must write nothing")
        self.assertEqual(self.metered, [], "leg A must never be billed")

    def test_leg_a_missed_marks_agent_no_answer(self):
        """Agent never picked up — this is the real 'user missed' signal."""
        db = FakeDB(_call_log())
        self._post(LEG_A_MISSED, db)
        self.assertEqual(db.updates_to("call_logs"), [{"status": "no_answer", "outcome": "no_answer"}])
        self.assertEqual(self.metered, [])

    def test_leg_a_missed_cannot_clobber_a_completed_call(self):
        """Out-of-order delivery must not undo a finished call."""
        db = FakeDB(_call_log(status="completed", duration_seconds=6))
        self._post(LEG_A_MISSED, db)
        self.assertEqual(db.updates_to("call_logs"), [])

    # ── leg B is authoritative ────────────────────────────────────────

    def test_leg_b_answered_sets_status_and_real_talk_time(self):
        db = FakeDB(_call_log())
        self._post(LEG_B_ANSWERED, db)
        status_update = db.updates_to("call_logs")[0]
        self.assertEqual(status_update["status"], "completed")
        # 6 is leg B's answeredsec. 15 would be leg A's, which wrongly includes
        # the customer's ring time.
        self.assertEqual(status_update["duration_seconds"], 6)

    def test_leg_b_meters_exactly_one_minute(self):
        db = FakeDB(_call_log())
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.metered, [(TENANT_ID, "call_minute", 1)])

    def test_both_legs_together_bill_only_once(self):
        """The double-billing regression: two CDRs, one call, one charge."""
        db = FakeDB(_call_log())
        self._post(LEG_A_ANSWERED, db)
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.metered, [(TENANT_ID, "call_minute", 1)])

    def test_redelivered_cdr_is_not_billed_again(self):
        """TeleCMI retries; an already-metered call must not pay twice."""
        db = FakeDB(_call_log(duration_seconds=6))
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.metered, [])

    # ── recording ─────────────────────────────────────────────────────

    def test_leg_b_recording_is_queued_and_processing_starts(self):
        """The filename is stored so a restart can resume; processing starts at once."""
        db = FakeDB(_call_log())
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.queued, [(CALL_LOG_ID, "16506305548176941220057791_2222223.mp3")])
        self.assertEqual(self.runs, [(CALL_LOG_ID, "2222223")])

    def test_recording_is_queued_after_the_talk_time_is_stored(self):
        """The pipeline reads duration_seconds to decide whether to score."""
        db = FakeDB(_call_log())
        order = []
        with patch(
            "app.routes.calls.queue_call_ai",
            side_effect=lambda *a: order.append(("queued", len(db.updates_to("call_logs")))),
        ):
            self._post(LEG_B_ANSWERED, db)
        self.assertEqual(order, [("queued", 1)])

    def test_redelivered_cdr_does_not_requeue_a_recording_in_progress(self):
        row = _call_log(status="completed", duration_seconds=6)
        row.update({"ai_status": "transcribing", "recording_filename": LEG_B_ANSWERED["filename"]})
        db = FakeDB(row)
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.queued, [])
        self.assertEqual(self.runs, [])

    def test_leg_a_never_triggers_a_recording_download(self):
        db = FakeDB(_call_log())
        self._post(LEG_A_ANSWERED, db)
        self.assertEqual(self.queued, [])
        self.assertEqual(self.runs, [])

    def test_terminal_cdr_recomputes_the_call_score(self):
        db = FakeDB(_call_log())
        self._post(LEG_B_ANSWERED, db)
        self.assertEqual(self.finalized, [CALL_LOG_ID])

    def test_leg_a_missed_recomputes_the_call_score(self):
        db = FakeDB(_call_log())
        self._post(LEG_A_MISSED, db)
        self.assertEqual(self.finalized, [CALL_LOG_ID])

    # ── lead matching ─────────────────────────────────────────────────

    def test_unlinked_lead_is_matched_on_normalized_phone(self):
        """CDR `to` is bare digits; leads.phone is '+91XXXXXXXXXX'."""
        db = FakeDB(_call_log(lead_id=None), lead_row={"id": "lead-9"})
        self._post(LEG_B_ANSWERED, db)
        lead_lookup = next(o for o in db.ops if o["table"] == "leads" and o["op"] == "select")
        self.assertEqual(lead_lookup["filters"]["phone"], "+919342012824")

    def test_leg_a_never_creates_a_lead_from_the_agent_number(self):
        """On leg A, `to` is the agent's own number — never a lead."""
        db = FakeDB(_call_log(lead_id=None), lead_row=None)
        self._post(LEG_A_ANSWERED, db)
        self.assertEqual([o for o in db.ops if o["table"] == "leads"], [])


if __name__ == "__main__":
    unittest.main()
