"""A Form answers row shows the deal its session became, from one tenant-scoped lookup."""
from app.routes import intake
from tests.fake_supabase import FakeSupabase


def _db():
    db = FakeSupabase()
    db.add("deals", id="d1", tenant_id="t1", intake_session_id="s1", deal_number=7)
    db.add("deals", id="d2", tenant_id="t2", intake_session_id="s3", deal_number=9)
    return db


def test_a_session_with_a_deal_gets_its_label():
    rows = intake._with_deal_labels(_db(), "t1", [{"id": "s1"}])
    assert rows[0]["deal_label"] == "D-0007"


def test_a_session_still_filling_the_form_gets_none():
    rows = intake._with_deal_labels(_db(), "t1", [{"id": "s2"}])
    assert rows[0]["deal_label"] is None


def test_another_tenants_deal_is_never_used():
    rows = intake._with_deal_labels(_db(), "t1", [{"id": "s3"}])
    assert rows[0]["deal_label"] is None


def test_no_rows_means_no_lookup():
    assert intake._with_deal_labels(_db(), "t1", []) == []
