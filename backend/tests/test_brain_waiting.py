"""Aira Brain: what is waiting on the client. The badge (/brain/count) and the hub total
(/brain waiting.count) come from one helper and must never disagree."""
import json

import pytest
from fastapi import HTTPException

from app.routes import brain as brain_routes
from app.services import brain, consistency
from app.services.brain import waiting
from brain_helpers import BrainDB

T1, T2 = "tenant-1", "tenant-2"


def _report(*issue_ids, dismissed=()):
    return json.dumps({"issues": [{"id": i} for i in issue_ids], "dismissed": list(dismissed)})


@pytest.fixture
def db():
    return BrainDB()


@pytest.fixture
def reports(monkeypatch):
    """Stored consistency reports by tenant; gather() and current_report() must never run."""
    store: dict[str, str | None] = {}
    monkeypatch.setattr(consistency, "get_setting", lambda key, fallback=None, tenant_id=None: store.get(tenant_id))

    def boom(*_a, **_k):
        raise AssertionError("the brain must read the stored report only")

    monkeypatch.setattr(consistency, "gather", boom)
    monkeypatch.setattr(consistency, "current_report", boom)
    return store


def _doc(db, tenant, name="a.pdf", **extra):
    return db.add("knowledge_documents", tenant_id=tenant, name=name, **extra)["id"]


def _review(db, tenant, document_id, created_at, status="pending"):
    return db.add("knowledge_reviews", tenant_id=tenant, document_id=document_id, status=status, created_at=created_at)


class TestSortReviews:
    def test_only_this_tenants_reviews(self, db, reports):
        mine, theirs = _doc(db, T1), _doc(db, T2)
        _review(db, T1, mine, "2026-09-01")
        _review(db, T2, theirs, "2026-09-02")
        result = waiting.pending_sort_reviews(db, T1)
        assert [r["document_id"] for r in result] == [mine]

    def test_forged_review_naming_another_tenants_document_is_dropped(self, db, reports):
        mine, theirs = _doc(db, T1), _doc(db, T2, name="secret.pdf")
        _review(db, T1, mine, "2026-09-01")
        _review(db, T1, theirs, "2026-09-02")  # tenant 1's row, tenant 2's document
        result = waiting.pending_sort_reviews(db, T1)
        assert [r["document_id"] for r in result] == [mine]
        assert "secret.pdf" not in json.dumps(result)

    def test_two_pending_rows_for_one_document_count_once_latest_wins(self, db, reports):
        doc = _doc(db, T1, name="price list.pdf")
        _review(db, T1, doc, "2026-09-01")
        newest = _review(db, T1, doc, "2026-09-03")
        result = waiting.pending_sort_reviews(db, T1)
        assert len(result) == 1
        assert result[0]["id"] == newest["id"]
        assert result[0]["title"] == "price list.pdf"

    def test_applied_and_discarded_reviews_are_not_waiting(self, db, reports):
        doc = _doc(db, T1)
        _review(db, T1, doc, "2026-09-01", status="applied")
        _review(db, T1, doc, "2026-09-02", status="discarded")
        assert waiting.pending_sort_reviews(db, T1) == []


class TestConsistencyCount:
    def test_counts_visible_issues_and_skips_dismissed(self, reports):
        reports[T1] = _report("a", "b", "c", dismissed=["b"])
        assert waiting.consistency_issue_count(T1) == 2

    def test_other_tenants_report_is_not_counted(self, reports):
        reports[T2] = _report("a", "b")
        assert waiting.consistency_issue_count(T1) == 0

    @pytest.mark.parametrize("raw", [
        None, "", "not json", "[]", "null", '{"issues": "oops"}', '{"issues": [1, 2]}',
        '{"issues": [{"no_id": true}]}', '{"issues": [{"id": "a"}], "dismissed": 5}',
    ])
    def test_missing_empty_or_malformed_report_is_zero(self, reports, raw):
        reports[T1] = raw
        assert waiting.consistency_issue_count(T1) == 0


class TestFailedFilesAndTemplates:
    def test_failed_upload_and_failed_sort_are_listed_for_this_tenant_only(self, db, reports):
        _doc(db, T1, name="bad-upload.pdf", status="failed")
        _doc(db, T1, name="bad-sort.pdf", status="indexed", sort_state="failed")
        _doc(db, T1, name="fine.pdf", status="indexed", sort_state="review")
        _doc(db, T2, name="other.pdf", status="failed")
        names = sorted(f["name"] for f in waiting.failed_files(db, T1))
        assert names == ["bad-sort.pdf", "bad-upload.pdf"]

    def test_only_rejected_templates_for_this_tenant(self, db, reports):
        db.add("message_templates", tenant_id=T1, name="offer", status="REJECTED", rejection_reason="Variables")
        db.add("message_templates", tenant_id=T1, name="hello", status="APPROVED")
        db.add("message_templates", tenant_id=T2, name="theirs", status="REJECTED")
        result = waiting.rejected_templates(db, T1)
        assert [(t["name"], t["reason"]) for t in result] == [("offer", "Variables")]


class TestBadgeMatchesHub:
    def test_count_equals_the_hub_waiting_total_and_never_touches_gather(self, db, reports, monkeypatch):
        doc = _doc(db, T1)
        _review(db, T1, doc, "2026-09-01")
        _review(db, T1, doc, "2026-09-02")  # duplicate for one document
        _doc(db, T1, name="bad.pdf", status="failed")
        db.add("message_templates", tenant_id=T1, name="offer", status="REJECTED")
        reports[T1] = _report("a", "b")

        summary = waiting.waiting_summary(db, T1)
        badge = brain.brain_count(T1, db=db)

        assert summary["count"] == 1 + 2 + 1 + 1
        assert badge == {"count": summary["count"], "sort_count": 1, "consistency_count": 2}

    def test_empty_tenant_is_zero_not_an_error(self, db, reports):
        assert brain.brain_count(T1, db=db) == {"count": 0, "sort_count": 0, "consistency_count": 0}


class TestRoutes:
    def test_count_route_returns_the_helper_result(self, monkeypatch):
        monkeypatch.setattr(brain_routes, "brain_count", lambda tenant_id: {"count": 3, "sort_count": 1, "consistency_count": 2})
        assert brain_routes.get_count({"tenant_id": T1}) == {"count": 3, "sort_count": 1, "consistency_count": 2}

    def test_both_routes_need_knowledge_view(self):
        no_access = {"tenant_id": T1, "role": "caller", "permissions": ["leads.view"]}
        with pytest.raises(HTTPException) as exc:
            brain_routes.require_read(no_access)
        assert exc.value.status_code == 403
        assert brain_routes.require_read({**no_access, "permissions": ["knowledge.view"]})
        assert brain_routes.require_read({**no_access, "permissions": ["knowledge.manage"]})

    def test_routes_are_mounted_under_api_v1_brain(self):
        from app.main import app

        paths = set(app.openapi()["paths"])
        assert {"/api/v1/brain", "/api/v1/brain/count"} <= paths
