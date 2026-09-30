"""Fleet waiting counts for the operator clients list, and the stuck-approval alert."""
import json
from datetime import datetime, timezone

import pytest

from app.services import consistency
from app.services.brain import waiting
from app.services.operator_brain_fleet import STUCK_APPROVAL_DAYS, fleet_waiting
from brain_helpers import BrainDB

T1, T2, T3 = "tenant-1", "tenant-2", "tenant-3"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    fake = BrainDB()
    for tenant, name in ((T1, "Acme"), (T2, "Bravo"), (T3, "Quiet")):
        fake.add("tenants", id=tenant, name=name)
    return fake


@pytest.fixture
def reports(monkeypatch, db):
    """Stored consistency reports live in app_settings; the per-tenant helper reads the same rows."""
    def fake_get(key, fallback=None, tenant_id=None):
        rows = [r for r in db.rows("app_settings") if r["tenant_id"] == tenant_id and r["key"] == key]
        return rows[0]["value"] if rows else fallback

    monkeypatch.setattr(consistency, "get_setting", fake_get)


def _doc(db, tenant, name="a.pdf", **extra):
    return db.add("knowledge_documents", tenant_id=tenant, name=name, **extra)["id"]


def _review(db, tenant, document_id, created_at):
    db.add("knowledge_reviews", tenant_id=tenant, document_id=document_id, status="pending", created_at=created_at)


def _report(db, tenant, *issue_ids, dismissed=()):
    db.add("app_settings", tenant_id=tenant, key="consistency_report",
           value=json.dumps({"issues": [{"id": i} for i in issue_ids], "dismissed": list(dismissed)}))


def _by_tenant(result):
    return {row["tenant_id"]: row for row in result["data"]}


def test_counts_and_oldest_age_per_tenant(db, reports):
    _review(db, T1, _doc(db, T1), "2026-09-20T12:00:00+00:00")
    _review(db, T1, _doc(db, T1, "b.pdf"), "2026-09-28T12:00:00+00:00")
    _report(db, T1, "x", "y", dismissed=["y"])
    _doc(db, T1, "broken.pdf", status="failed")
    db.add("message_templates", tenant_id=T1, name="hello", status="REJECTED")
    rows = _by_tenant(fleet_waiting(db, now=NOW))
    assert rows[T1]["waiting_count"] == 2 + 1 + 1 + 1
    assert rows[T1]["pending_reviews"] == 2 and rows[T1]["oldest_review_days"] == 10
    assert T3 not in rows  # nothing waiting: not listed


def test_matches_the_per_tenant_helper_the_badge_uses(db, reports):
    doc_a = _doc(db, T1)
    _review(db, T1, doc_a, "2026-09-01T00:00:00+00:00")
    _review(db, T1, doc_a, "2026-09-05T00:00:00+00:00")  # two pending rows, one document: counted once
    _review(db, T1, _doc(db, T2, "secret.pdf"), "2026-09-06T00:00:00+00:00")  # forged: tenant 2's document
    _review(db, T2, _doc(db, T2, "own.pdf"), "2026-09-07T00:00:00+00:00")
    _report(db, T1, "a", "b", "c", dismissed=["c"])
    _doc(db, T2, "f.pdf", sort_state="failed")
    fleet = _by_tenant(fleet_waiting(db, now=NOW))
    for tenant in (T1, T2):
        assert fleet[tenant]["waiting_count"] == waiting.waiting_summary(db, tenant)["count"]
    assert fleet[T1]["pending_reviews"] == 1


def test_malformed_or_missing_report_counts_zero(db, reports):
    db.add("app_settings", tenant_id=T1, key="consistency_report", value="{not json")
    db.add("app_settings", tenant_id=T2, key="consistency_report", value=json.dumps({"issues": [{"no_id": 1}]}))
    result = fleet_waiting(db, now=NOW)
    assert result["data"] == [] and result["alerts"] == []


def test_alert_only_when_oldest_approval_is_older_than_seven_days(db, reports):
    assert STUCK_APPROVAL_DAYS == 7
    _review(db, T1, _doc(db, T1), "2026-09-22T12:00:00+00:00")  # exactly 8 days
    _review(db, T2, _doc(db, T2), "2026-09-23T12:00:00+00:00")  # exactly 7 days: not stuck yet
    result = fleet_waiting(db, now=NOW)
    assert [a["tenant_id"] for a in result["alerts"]] == [T1]
    alert = result["alerts"][0]
    assert alert["id"] == f"brain:stuck_approval:{T1}" and alert["source"] == "brain" and alert["severity"] == "warning"
    assert "Acme" in alert["detail"] and alert["href"] == f"/operator/client/{T1}?section=brain"


def test_conflicts_alone_never_raise_the_stuck_alert(db, reports):
    _report(db, T1, "a")
    assert fleet_waiting(db, now=NOW)["alerts"] == []


def test_query_count_does_not_grow_with_tenants(db, reports):
    counter = {"n": 0}
    original = db.table

    def counting(name):
        counter["n"] += 1
        return original(name)

    db.table = counting
    _review(db, T1, _doc(db, T1), "2026-09-01T00:00:00+00:00")
    _report(db, T1, "a")
    fleet_waiting(db, now=NOW)
    baseline = counter["n"]
    for i in range(30):
        tenant = f"bulk-{i}"
        db.add("tenants", id=tenant, name=tenant)
        _review(db, tenant, _doc(db, tenant), "2026-09-01T00:00:00+00:00")
        _report(db, tenant, "a")
    counter["n"] = 0
    fleet_waiting(db, now=NOW)
    assert counter["n"] == baseline
