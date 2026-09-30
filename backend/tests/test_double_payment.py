"""R2: a second, different payment landing on an already-paid session is recorded, flagged
"refund needed" and surfaced to staff instead of being dropped silently. No auto-refund."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import intake

SID, TENANT, LEAD = "sess-1", "tenant-1", "lead-1"


class FakeDb:
    """Just the chain confirm_intake_payment uses on intake_sessions. `stale_first_read`
    serves the first read from before another webhook won the claim (the race)."""

    def __init__(self, row, stale_first_read=False):
        self.rows = {"intake_sessions": row}
        self.stale = dict(row, status="awaiting_payment") if stale_first_read else None
        self.other_writes = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.filters = db, name, "select", None, []
        self.single = False
        self.negate = False

    def select(self, *_):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def neq(self, col, val):
        self.filters.append(lambda r: r.get(col) != val)
        return self

    def is_(self, col, val):
        assert val == "null"
        self.filters.append(lambda r: r.get(col) is None)
        return self

    @property
    def not_(self):
        self.negate = True
        return self

    def contains(self, col, values):
        has = lambda r: set(values) <= set(r.get(col) or [])  # noqa: E731
        negate, self.negate = self.negate, False
        self.filters.append((lambda r: not has(r)) if negate else has)
        return self

    def maybe_single(self):
        self.single = True
        return self

    def execute(self):
        row = self.db.rows.get(self.name)
        if row is None:
            return SimpleNamespace(data=None)
        if self.op == "select":
            if self.db.stale:
                stale, self.db.stale = self.db.stale, None
                return SimpleNamespace(data=dict(stale))
            return SimpleNamespace(data=dict(row) if self.single else [dict(row)])
        if all(f(row) for f in self.filters):
            row.update(self.payload)
            return SimpleNamespace(data=[dict(row)])
        return SimpleNamespace(data=[])


def _paid_row(**over):
    return {
        "id": SID, "tenant_id": TENANT, "lead_id": LEAD, "status": "paid",
        "razorpay_payment_id": "pay_1", "extra_payment_ids": [], "refund_needed": False,
        "collected_data": {"name": "Vivek"}, "amount_paise": 100, **over,
    }


@pytest.fixture
def alerts():
    with patch.object(intake, "notify_pool") as pool, \
         patch("app.services.ai_reply._trigger_chat_escalation") as handover:
        yield SimpleNamespace(pool=pool, handover=handover)


def test_a_second_payment_is_recorded_flagged_and_alerted(alerts):
    db = FakeDb(_paid_row())
    assert intake.confirm_intake_payment(SID, "pay_2", amount_paid_paise=100, db=db) is None
    row = db.rows["intake_sessions"]
    assert row["extra_payment_ids"] == ["pay_2"] and row["refund_needed"] is True
    assert row["razorpay_payment_id"] == "pay_1" and row["status"] == "paid"
    alerts.pool.assert_called_once()
    assert alerts.pool.call_args.args[0] == TENANT and "refund" in alerts.pool.call_args.args[3].lower()
    alerts.handover.assert_called_once()
    assert alerts.handover.call_args.kwargs["tenant_id"] == TENANT
    assert alerts.handover.call_args.kwargs["lead_id"] == LEAD


def test_a_retried_webhook_for_the_second_payment_is_idempotent(alerts):
    db = FakeDb(_paid_row())
    intake.confirm_intake_payment(SID, "pay_2", db=db)
    intake.confirm_intake_payment(SID, "pay_2", db=db)
    assert db.rows["intake_sessions"]["extra_payment_ids"] == ["pay_2"]
    alerts.pool.assert_called_once()
    alerts.handover.assert_called_once()


def test_a_second_and_third_distinct_payment_are_both_kept(alerts):
    db = FakeDb(_paid_row())
    intake.confirm_intake_payment(SID, "pay_2", db=db)
    intake.confirm_intake_payment(SID, "pay_3", db=db)
    assert db.rows["intake_sessions"]["extra_payment_ids"] == ["pay_2", "pay_3"]


def test_a_retry_of_the_original_payment_is_not_a_double_payment(alerts):
    db = FakeDb(_paid_row())
    assert intake.confirm_intake_payment(SID, "pay_1", db=db) is None
    row = db.rows["intake_sessions"]
    assert row["extra_payment_ids"] == [] and row["refund_needed"] is False
    alerts.pool.assert_not_called()


def test_a_payment_that_loses_the_claim_race_is_recorded_too(alerts):
    db = FakeDb(_paid_row(), stale_first_read=True)
    assert intake.confirm_intake_payment(SID, "pay_2", db=db) is None
    assert db.rows["intake_sessions"]["extra_payment_ids"] == ["pay_2"]
    alerts.pool.assert_called_once()


def test_an_alert_failure_never_breaks_the_webhook(alerts):
    alerts.pool.side_effect = RuntimeError("notify down")
    alerts.handover.side_effect = RuntimeError("handover down")
    db = FakeDb(_paid_row())
    assert intake.confirm_intake_payment(SID, "pay_2", db=db) is None
    assert db.rows["intake_sessions"]["refund_needed"] is True
