"""
Tests for `_resolve_scheduler_run`, the pure decision logic behind the
operator Scheduler Health "Run now" action (POST
/api/v1/operator/scheduler/{job_id}/run).

Contract under test: given a job_id and the APScheduler `Job` looked up for
it (or `None`), the helper decides whether an immediate run may proceed --
404 for an unknown job, 409 for a paused job (next_run_time is None) -- with
no scheduler mutation or DB access. The route wires this to the real
`_scheduler` singleton; the singleton itself is not exercised here since the
decision logic is fully expressible without it.
"""
import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.routes.operator import _resolve_scheduler_run

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeJob:
    """Stand-in for an APScheduler `Job` exposing only what the route reads."""
    id: str
    next_run_time: datetime | None


class ResolveSchedulerRunTests(unittest.TestCase):
    def test_unknown_job_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            _resolve_scheduler_run("does-not-exist", None)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("does-not-exist", ctx.exception.detail)

    def test_paused_job_raises_409(self):
        job = FakeJob(id="scheduled-broadcasts", next_run_time=None)
        with self.assertRaises(HTTPException) as ctx:
            _resolve_scheduler_run("scheduled-broadcasts", job)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("paused", ctx.exception.detail.lower())

    def test_active_job_resolves_without_raising(self):
        job = FakeJob(id="scheduled-broadcasts", next_run_time=NOW)
        result = _resolve_scheduler_run("scheduled-broadcasts", job)
        self.assertEqual(result, {"id": "scheduled-broadcasts"})


if __name__ == "__main__":
    unittest.main()
