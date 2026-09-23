"""Regression test for AUDIT-2026-09.md finding C6.

build_follow_up_summary() used to query follow_up_jobs and leads with no
tenant filter at all, so GET /api/v1/follow-ups/summary (and the summary
tail of POST /follow-ups/run) returned every tenant's pending/sent/failed
counts plus a preview of other tenants' lead names and phones to any
authenticated caller.

This seeds two tenants' worth of follow_up_jobs/leads into one fake table
and asserts a call scoped to tenant-a never returns tenant-b's rows.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import growth


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Fake follow_up_jobs / leads table that actually respects .eq(),
    .in_() and .gte() filters, so the test proves tenant scoping -- not
    just that a tenant_id argument exists."""

    def __init__(self, rows: list[dict]):
        self._all_rows = rows
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def in_(self, col, values):
        self._rows = [r for r in self._rows if r.get(col) in values]
        return self

    def gte(self, col, val):
        self._rows = [r for r in self._rows if (r.get(col) or "") >= val]
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(list(self._rows))


class _FakeDB:
    def __init__(self, follow_up_jobs: list[dict], leads: list[dict]):
        self.follow_up_jobs = follow_up_jobs
        self.leads = leads

    def table(self, name):
        if name == "follow_up_jobs":
            return _Query(self.follow_up_jobs)
        if name == "leads":
            return _Query(self.leads)
        return _Query([])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def test_summary_never_returns_another_tenants_jobs_or_leads():
    jobs = [
        {"id": "job-a1", "tenant_id": "tenant-a", "lead_id": "lead-a1", "cadence": "3d", "status": "pending", "scheduled_for": _now_iso()},
        {"id": "job-b1", "tenant_id": "tenant-b", "lead_id": "lead-b1", "cadence": "3d", "status": "pending", "scheduled_for": _now_iso()},
    ]
    leads = [
        {"id": "lead-a1", "tenant_id": "tenant-a", "name": "Alice A", "phone": "+91100000001", "segment": "A"},
        {"id": "lead-b1", "tenant_id": "tenant-b", "name": "Bob B (secret)", "phone": "+91200000002", "segment": "A"},
    ]
    db = _FakeDB(jobs, leads)

    summary = growth.build_follow_up_summary("tenant-a", db=db)

    queue_lead_ids = {row["lead_id"] for row in summary["queue"]}
    assert queue_lead_ids == {"lead-a1"}, f"leaked another tenant's job into the queue: {queue_lead_ids}"

    queue_names = {row.get("lead_name") for row in summary["queue"]}
    assert "Bob B (secret)" not in queue_names

    assert summary["pending"] == 1, f"expected only tenant-a's 1 pending job, counted {summary['pending']}"


def test_summary_for_the_other_tenant_only_sees_its_own_row():
    jobs = [
        {"id": "job-a1", "tenant_id": "tenant-a", "lead_id": "lead-a1", "cadence": "3d", "status": "pending", "scheduled_for": _now_iso()},
        {"id": "job-b1", "tenant_id": "tenant-b", "lead_id": "lead-b1", "cadence": "3d", "status": "pending", "scheduled_for": _now_iso()},
    ]
    leads = [
        {"id": "lead-a1", "tenant_id": "tenant-a", "name": "Alice A", "phone": "+91100000001", "segment": "A"},
        {"id": "lead-b1", "tenant_id": "tenant-b", "name": "Bob B", "phone": "+91200000002", "segment": "A"},
    ]
    db = _FakeDB(jobs, leads)

    summary = growth.build_follow_up_summary("tenant-b", db=db)

    queue_lead_ids = {row["lead_id"] for row in summary["queue"]}
    assert queue_lead_ids == {"lead-b1"}
