"""Regressions for the intake staleness sweep: dead awaiting_payment links get
cancelled, forgotten paid sessions get auto-resolved, both after 48h, and the
sweep never lets one bad row stop the rest."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock

import pytest

from app.services.intake import sweep_stale_intake_sessions

SID_AWAITING = "11111111-2222-3333-4444-555555555555"
SID_PAID = "22222222-3333-4444-5555-666666666666"
TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"


class _Chain:
    def __init__(self, result, log, table):
        self._result = result
        self._log = log
        self._table = table

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            if name in ("update", "insert"):
                self._log.append((self._table, name, args[0] if args else None))
            return self

        return _record

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _SeqDb:
    """Routes each .table(name) call to the next preset result for that table,
    recording every update/insert payload for assertions."""

    def __init__(self, results_by_table):
        self._results = {k: list(v) for k, v in results_by_table.items()}
        self.writes = []

    def table(self, name):
        return _Chain(self._results[name].pop(0), self.writes, name)


def _res(data):
    m = MagicMock()
    m.data = data
    return m


@pytest.mark.asyncio
async def test_sweep_cancels_stale_awaiting_payment_and_resolves_stale_paid():
    db = _SeqDb({
        "intake_sessions": [
            _res([{"id": SID_AWAITING}]),          # stale awaiting_payment query
            _res([{"id": SID_AWAITING}]),           # cancel update
            _res([{"id": SID_PAID, "tenant_id": TENANT}]),  # stale paid query
            _res([{"id": SID_PAID}]),               # resolve update
        ],
    })

    out = await sweep_stale_intake_sessions(db=db)

    assert out == {"cancelled": 1, "resolved": 1}
    updates = [(t, p) for t, op, p in db.writes if op == "update"]
    assert updates[0] == ("intake_sessions", {"status": "cancelled"})
    assert updates[1][1]["status"] == "resolved"
    assert "resolved_at" in updates[1][1]


@pytest.mark.asyncio
async def test_sweep_no_stale_rows_is_a_clean_no_op():
    db = _SeqDb({
        "intake_sessions": [
            _res([]),  # no stale awaiting_payment
            _res([]),  # no stale paid
        ],
    })

    out = await sweep_stale_intake_sessions(db=db)

    assert out == {"cancelled": 0, "resolved": 0}
    assert db.writes == []


@pytest.mark.asyncio
async def test_sweep_survives_a_failing_cancel_and_continues_to_paid():
    db = _SeqDb({
        "intake_sessions": [
            _res([{"id": SID_AWAITING}]),
            RuntimeError("db blip"),  # cancel update fails
            _res([{"id": SID_PAID, "tenant_id": TENANT}]),
            _res([{"id": SID_PAID}]),
        ],
    })

    out = await sweep_stale_intake_sessions(db=db)

    assert out == {"cancelled": 0, "resolved": 1}


def test_sweep_job_is_registered_in_the_scheduler():
    import inspect

    import app.main as main

    src = inspect.getsource(main)
    assert "intake-staleness-sweep" in src
    assert "_sweep_stale_intake_sessions" in src
