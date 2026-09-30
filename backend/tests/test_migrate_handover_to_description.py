"""The one-off data step that moves handover_line into Description section 8.
Runs against an in-memory database only; the script is never pointed at a real one."""
import pytest

from app.services import business_profile as bp
from app.services import knowledge_versions as kv
from fake_supabase import FakeSupabase
from scripts import migrate_handover_to_description as mig

T1, T2, T3 = "tenant-1", "tenant-2", "tenant-3"
HEADING = "WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM"
LINE = "Call us 10am to 6pm."
DESCRIPTION = "ABOUT US\nWe sell sarees.\n\nHOW CUSTOMERS BUY\nOrder on WhatsApp."


@pytest.fixture
def db(monkeypatch):
    """A FakeSupabase whose app_settings rows also back knowledge_versions' settings calls."""
    fake = FakeSupabase()

    def rows_for(tenant_id, key):
        return [r for r in fake.rows("app_settings") if r["tenant_id"] == tenant_id and r["key"] == key]

    def get_setting(key, fallback=None, tenant_id=None):
        rows = rows_for(tenant_id, key)
        return (rows[0]["value"] or fallback) if rows else fallback

    def save_setting(key, value, tenant_id=None):
        rows = rows_for(tenant_id, key)
        if rows:
            rows[0]["value"] = value
        else:
            fake.add("app_settings", tenant_id=tenant_id, key=key, value=value)

    monkeypatch.setattr(kv, "get_setting", get_setting)
    monkeypatch.setattr(kv, "save_setting", save_setting)
    monkeypatch.setattr(kv, "invalidate_cache", lambda key=None: None)
    return fake


def _seed(db, tenant_id, *, handover=None, description=None):
    if handover is not None:
        db.add("app_settings", tenant_id=tenant_id, key="handover_line", value=handover)
    if description is not None:
        db.add("app_settings", tenant_id=tenant_id, key="business_description", value=description)


def _setting(db, tenant_id, key):
    rows = [r for r in db.rows("app_settings") if r["tenant_id"] == tenant_id and r["key"] == key]
    return rows[0]["value"] if rows else None


# ─── plan_tenant (pure) ───────────────────────────────────────────────────────

@pytest.mark.parametrize("line", ["CALL 9876543210", "SUPPORT TEAM", "Hello\nCALL US"])
def test_plan_stops_when_the_line_would_not_parse_back_as_the_section(line):
    plan = mig.plan_tenant(T1, DESCRIPTION, line)
    assert plan.action == mig.STOP
    assert plan.reason == "handover line would not parse cleanly (looks like a heading?)"
    assert plan.new_description == ""


def test_plan_migrates_a_multi_line_line_when_it_parses_back_whole():
    plan = mig.plan_tenant(T1, DESCRIPTION, "Call us 10am to 6pm.\nWe reply fast.")
    assert plan.action == mig.MIGRATE


def test_plan_appends_the_section_without_touching_existing_text():
    plan = mig.plan_tenant(T1, DESCRIPTION, LINE)
    assert plan.action == mig.MIGRATE
    assert plan.new_description == f"{DESCRIPTION}\n\n{HEADING}\n{LINE}"
    assert bp.parse(plan.new_description).sections["handover"] == LINE


def test_plan_for_a_tenant_with_no_description_holds_only_section_8():
    plan = mig.plan_tenant(T1, "", LINE)
    assert plan.action == mig.MIGRATE
    assert plan.new_description == f"{HEADING}\n{LINE}"
    assert list(bp.parse(plan.new_description).sections) == ["handover"]


def test_plan_skips_a_description_that_already_has_the_heading():
    plan = mig.plan_tenant(T1, f"{DESCRIPTION}\n\n{HEADING}\n", LINE)  # even an empty one
    assert plan.action == mig.SKIP and "8th heading" in plan.reason


def test_plan_skips_when_there_is_no_line():
    assert mig.plan_tenant(T1, DESCRIPTION, "   ").action == mig.SKIP


def test_plan_stops_when_the_cap_would_be_passed_and_never_trims():
    long_description = "ABOUT US\n" + ("word " * 695)
    plan = mig.plan_tenant(T1, long_description, "Call us today for any help you need.")
    assert plan.action == mig.STOP and "700" in plan.reason
    assert plan.new_description == ""  # nothing to write


def test_plan_allows_a_description_that_lands_exactly_on_the_cap():
    plan = mig.plan_tenant(T1, "ABOUT US\n" + ("word " * 695), "one two three four five")
    assert plan.action == mig.MIGRATE


# ─── run ──────────────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(db):
    _seed(db, T1, handover=LINE, description=DESCRIPTION)
    lines: list[str] = []
    results = mig.run(db, apply=False, out=lines.append)
    assert [p.action for p in results] == [mig.MIGRATE]
    assert _setting(db, T1, "business_description") == DESCRIPTION
    assert _setting(db, T1, "handover_line") == LINE
    assert db.rows("knowledge_versions") == []
    assert any("DRY RUN" in l for l in lines) and any("WOULD MIGRATE" in l for l in lines)


def test_apply_moves_the_line_writes_a_version_and_blanks_the_old_setting(db):
    _seed(db, T1, handover=LINE, description=DESCRIPTION)
    results = mig.run(db, apply=True, out=lambda _l: None)
    assert [p.action for p in results] == [mig.MIGRATE]

    new_text = _setting(db, T1, "business_description")
    assert new_text == f"{DESCRIPTION}\n\n{HEADING}\n{LINE}"
    assert _setting(db, T1, "handover_line") is None  # blanked
    versions = db.rows("knowledge_versions")
    assert [(v["kind"], v["reason"]) for v in versions] == [("description", "baseline"), ("description", "edit")]
    assert versions[0]["content"] == DESCRIPTION  # the old text is recoverable from history
    assert versions[1]["content"] == new_text
    # The single reader now returns the section, and a cleared section would not bring the old line back.
    assert bp.parse(new_text).sections["handover"] == LINE


def test_apply_gives_a_tenant_without_a_description_only_section_8(db):
    _seed(db, T2, handover=LINE)
    mig.run(db, apply=True, out=lambda _l: None)
    assert _setting(db, T2, "business_description") == f"{HEADING}\n{LINE}"
    assert _setting(db, T2, "handover_line") is None


def test_apply_is_idempotent(db):
    _seed(db, T1, handover=LINE, description=DESCRIPTION)
    mig.run(db, apply=True, out=lambda _l: None)
    after_first = _setting(db, T1, "business_description")
    versions_after_first = len(db.rows("knowledge_versions"))

    second = mig.run(db, apply=True, out=lambda _l: None)  # setting is gone: nothing to find
    assert second == []
    assert _setting(db, T1, "business_description") == after_first
    assert len(db.rows("knowledge_versions")) == versions_after_first


def test_apply_skips_a_tenant_that_already_has_the_heading_and_keeps_its_text(db):
    with_heading = f"{DESCRIPTION}\n\n{HEADING}\nExisting wording."
    _seed(db, T1, handover=LINE, description=with_heading)
    results = mig.run(db, apply=True, out=lambda _l: None)
    assert [p.action for p in results] == [mig.SKIP]
    assert _setting(db, T1, "business_description") == with_heading
    assert db.rows("knowledge_versions") == []


def test_apply_stops_for_an_over_cap_tenant_and_still_migrates_the_others(db):
    big = "ABOUT US\n" + ("word " * 698)
    _seed(db, T1, handover="Call us today for any help.", description=big)
    _seed(db, T2, handover=LINE, description=DESCRIPTION)
    lines: list[str] = []
    results = mig.run(db, apply=True, out=lines.append)

    by_tenant = {p.tenant_id: p.action for p in results}
    assert by_tenant == {T1: mig.STOP, T2: mig.MIGRATE}
    assert _setting(db, T1, "business_description") == big  # never trimmed, never written
    assert _setting(db, T1, "handover_line") == "Call us today for any help."  # old setting untouched
    assert any(T1 in l and "STOP" in l for l in lines)


def test_tenants_without_a_line_are_not_listed(db):
    _seed(db, T1, handover="", description=DESCRIPTION)
    _seed(db, T3, description=DESCRIPTION)
    assert mig.run(db, apply=True, out=lambda _l: None) == []


def test_only_tenant_flag_limits_the_run(db):
    _seed(db, T1, handover=LINE, description=DESCRIPTION)
    _seed(db, T2, handover=LINE, description=DESCRIPTION)
    results = mig.run(db, apply=True, only_tenant=T2, out=lambda _l: None)
    assert [p.tenant_id for p in results] == [T2]
    assert _setting(db, T1, "handover_line") == LINE


def test_old_setting_is_kept_when_the_write_does_not_read_back(db, monkeypatch):
    _seed(db, T1, handover=LINE, description=DESCRIPTION)
    monkeypatch.setattr(kv, "save_setting", lambda key, value, tenant_id=None: None)  # write silently lost
    results = mig.run(db, apply=True, out=lambda _l: None)
    assert [p.action for p in results] == [mig.FAILED]
    assert _setting(db, T1, "handover_line") == LINE


def test_main_reports_failure_through_the_exit_code(db, monkeypatch):
    _seed(db, T1, handover="Call us today for any help.", description="ABOUT US\n" + ("word " * 698))
    import sys
    monkeypatch.setattr(sys, "argv", ["migrate"])
    monkeypatch.setattr("app.db.supabase.get_supabase", lambda: db)
    assert mig.main() == 1
