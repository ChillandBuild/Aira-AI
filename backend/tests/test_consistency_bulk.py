"""Bulk Fix / Dismiss / Restore for the conflicts panel, and the section field on issues
(blueprint sections 7, 9, 9A, 12). The service works on one report read, changed and saved once."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import consistency as routes
from app.services import consistency
from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv

CHECKED = "2026-09-30T10:00:00+00:00"
CONFIG = {
    "enabled": True,
    "fields": [{"key": "name", "label": "Name", "type": "text"},
               {"key": "date_of_birth", "label": "Date of birth", "type": "text"}],
    "packages": [{"key": "one", "name": "One Question", "amount_paise": 4900}],
}
DESCRIPTION = (
    "Hello from the Astro team.\n"
    "ABOUT US\n"
    "We read stars.\n"
    "HOW CUSTOMERS BUY\n"
    "Accurate guidance starts from ₹29. Everything happens through the app.\n"
    "WHAT YOU MUST NEVER DO\n"
    "Never ask for DOB, TOB, or POB.\n"
    "Be kind."
)
PRICE = "Accurate guidance starts from ₹29."
APP = "Everything happens through the app."
NEVER = "Never ask for DOB, TOB, or POB."
FILE_TEXT = "Fees: Rs 99 per question.\nWe are open daily."


def _issue(issue_id, quote, proposed, where="description", **extra):
    base = {"id": issue_id, "kind": "other", "where": where, "document_id": None, "document_name": None,
            "editable": True, "quote": quote, "topic": "t", "truth": "x", "proposed": proposed}
    return {**base, **extra}


def _issues():
    return [
        _issue("p", PRICE, "Accurate guidance starts from ₹49."),
        _issue("a", APP, "Everything happens in this chat."),
        _issue("n", NEVER, ""),
        _issue("f", "Fees: Rs 99 per question.", "Fees: Rs 49 per question.", where="knowledge",
               document_id="d1", document_name="kb.docx"),
    ]


class World:
    """An in-memory tenant: the report, the Description, one sorted file, and a write log."""

    def __init__(self, issues=None, dismissed=None):
        self.report = {"issues": issues if issues is not None else _issues(), "dismissed": dismissed or [],
                       "checked_at": CHECKED, "fingerprint": "f"}
        self.description = DESCRIPTION
        self.file_text = FILE_TEXT
        self.report_saves = 0
        self.description_saves: list[str] = []
        self.fact_saves: list[tuple[str, str]] = []

    def install(self, monkeypatch):
        def save_report(tenant_id, report):
            self.report = report
            self.report_saves += 1

        def save_description(db, tenant_id, text, reason, user_id):
            assert reason == "edit"
            self.description = text
            self.description_saves.append(text)

        def update_facts(db, tenant_id, document_id, text, user_id):
            self.file_text = text
            self.fact_saves.append((document_id, text))
            return {"facts": text, "campaign_tag_id": None}

        src = {"description": DESCRIPTION, "handover_line": "", "config": CONFIG, "selling": True, "catalog": [],
               "documents": []}
        monkeypatch.setattr(consistency, "load_report", lambda tenant_id: self.report)
        monkeypatch.setattr(consistency, "_save_report", save_report)
        monkeypatch.setattr(consistency, "gather", lambda db, tenant_id: src)
        monkeypatch.setattr(consistency, "_documents", lambda db, tenant_id: [
            {"id": "d1", "name": "kb.docx", "text": self.file_text, "editable": True}])
        monkeypatch.setattr(kv, "current_description", lambda tenant_id: self.description)
        monkeypatch.setattr(kv, "save_description", save_description)
        monkeypatch.setattr(ks, "update_facts", update_facts)
        return self


@pytest.fixture
def world(monkeypatch):
    return World().install(monkeypatch)


def fix(ids, *, owner=True, checked_at=CHECKED):
    return consistency.apply_fixes(object(), "t", ids, checked_at, user_id="u", is_owner=owner)


def response_part(result):
    return {k: result[k] for k in ("applied", "skipped", "failed")}


class TestApplyFixes:
    def test_three_description_fixes_save_one_version_and_the_report_once(self, world):
        result = fix(["p", "a", "n"])
        assert result["applied"] == ["p", "a", "n"] and not result["skipped"] and not result["failed"]
        assert len(world.description_saves) == 1
        assert "₹49" in world.description and "₹29" not in world.description
        assert "in this chat" in world.description and "DOB" not in world.description
        assert world.report_saves == 1
        assert [i["id"] for i in world.report["issues"]] == ["f"]

    def test_mixed_batch_reports_applied_skipped_and_failed(self, world):
        world.report["issues"] = [
            *_issues(),
            _issue("none", "Be kind.", None),
            _issue("bad", "Be kind.", "Only ₹19 today!"),
            _issue("gone", "This sentence was edited away.", "x"),
        ]
        result = fix(["p", "none", "bad", "gone", "missing", "f"])
        assert result["applied"] == ["p", "f"]
        assert [(s["id"], s["code"]) for s in result["skipped"]] == [("none", "no_proposal")]
        assert [(f["id"], f["code"]) for f in result["failed"]] == [
            ("bad", "unverified_tokens"), ("gone", "text_changed"), ("missing", "not_found")]
        assert all(e["reason"] for e in result["skipped"] + result["failed"])
        assert len(world.fact_saves) == 1 and world.fact_saves[0][0] == "d1"
        assert sorted(i["id"] for i in world.report["issues"]) == ["a", "bad", "gone", "n", "none"]

    def test_non_owner_skips_description_items_but_still_fixes_files(self, world):
        result = fix(["p", "f", "n"], owner=False)
        assert result["applied"] == ["f"]
        assert [(s["id"], s["reason"], s["code"]) for s in result["skipped"]] == [
            ("p", "Only an account owner can change the Description.", "owner_only"),
            ("n", "Only an account owner can change the Description.", "owner_only")]
        assert world.description_saves == [] and len(world.fact_saves) == 1

    def test_stale_checked_at_raises_409_and_changes_nothing(self, world):
        with pytest.raises(consistency.FixError) as e:
            fix(["p"], checked_at="2026-01-01T00:00:00+00:00")
        assert e.value.status == 409 and str(e.value) == "Issues changed, reload"
        assert world.report_saves == 0 and world.description_saves == []

    def test_two_edits_on_one_file_are_chained_into_one_facts_update(self, world):
        world.file_text = "Fees: Rs 99 per question.\nRefunds: Rs 99 back."
        world.report["issues"] = [
            _issue("f1", "Fees: Rs 99 per question.", "Fees: Rs 49 per question.", where="knowledge",
                   document_id="d1", document_name="kb.docx"),
            _issue("f2", "Refunds: Rs 99 back.", "Refunds: Rs 49 back.", where="knowledge",
                   document_id="d1", document_name="kb.docx"),
        ]
        result = fix(["f1", "f2"])
        assert result["applied"] == ["f1", "f2"]
        assert world.fact_saves == [("d1", "Fees: Rs 49 per question.\nRefunds: Rs 49 back.")]
        assert result["index_jobs"] == [{"document_id": "d1", "facts": world.file_text, "campaign_tag_id": None}]

    def test_a_file_that_is_not_sorted_is_skipped(self, world):
        world.report["issues"] = [_issue("k", "x", "", where="knowledge", document_id="d1", editable=False)]
        result = fix(["k"])
        assert [(s["id"], s["code"]) for s in result["skipped"]] == [("k", "not_editable")]

    def test_a_missing_file_fails_and_a_stale_handover_line_never_writes(self, world):
        world.report["issues"] = [
            _issue("h", "x", "y", where="handover_line"),
            _issue("g", "x", "", where="knowledge", document_id="nope"),
        ]
        result = fix(["h", "g"])
        assert [(f["id"], f["code"]) for f in result["failed"]] == [("h", "file_gone"), ("g", "file_gone")]
        assert world.fact_saves == [] and world.description_saves == [] and world.report_saves == 0

    def test_a_failed_save_moves_its_issues_to_failed_and_keeps_them_in_the_report(self, world, monkeypatch):
        def boom(*args):
            raise RuntimeError("db down")

        monkeypatch.setattr(kv, "save_description", boom)
        result = fix(["p", "f"])
        assert result["applied"] == ["f"]
        assert [(f["id"], f["code"], f["reason"]) for f in result["failed"]] == [("p", "save_failed", "db down")]
        assert "p" in [i["id"] for i in world.report["issues"]]

    def test_duplicate_ids_are_fixed_once(self, world):
        assert fix(["p", "p"])["applied"] == ["p"]

    def test_recheck_only_when_something_was_applied(self, world):
        assert fix(["missing"])["recheck"] is False
        assert fix(["p"])["recheck"] is True


class TestParityWithSingleFix:
    @pytest.mark.parametrize("issue_id", ["p", "n", "f"])
    def test_a_batch_of_one_equals_apply_fix(self, monkeypatch, issue_id):
        single = World().install(monkeypatch)
        consistency.apply_fix(object(), "t", issue_id, user_id="u", is_owner=True)
        single_state = (single.description, single.file_text, single.report["issues"], single.description_saves,
                        single.fact_saves)
        batch = World().install(monkeypatch)
        result = fix([issue_id])
        assert result["applied"] == [issue_id]
        assert (batch.description, batch.file_text, batch.report["issues"], batch.description_saves,
                batch.fact_saves) == single_state

    @pytest.mark.parametrize("issue_id,owner,status", [("p", False, 403), ("missing", True, 404)])
    def test_a_refusal_in_apply_fix_is_a_refusal_in_the_batch(self, monkeypatch, issue_id, owner, status):
        World().install(monkeypatch)
        with pytest.raises(consistency.FixError) as e:
            consistency.apply_fix(object(), "t", issue_id, user_id="u", is_owner=owner)
        assert e.value.status == status
        result = fix([issue_id], owner=owner)
        assert result["applied"] == [] and len(result["skipped"] + result["failed"]) == 1


class TestDismissAndRestore:
    def test_round_trip(self, world):
        result = consistency.dismiss_many("t", ["p", "a", "ghost"], CHECKED)
        assert result["dismissed"] == ["p", "a"]
        assert [(s["id"], s["code"]) for s in result["skipped"]] == [("ghost", "not_found")]
        assert world.report["dismissed"] == ["p", "a"] and world.report_saves == 1
        assert [i["id"] for i in consistency.visible(world.report)["issues"]] == ["n", "f"]

        back = consistency.restore("t", ["a", "n"])
        assert back["restored"] == ["a"]
        assert [(s["id"], s["code"]) for s in back["skipped"]] == [("n", "not_dismissed")]
        assert world.report["dismissed"] == ["p"]
        assert [i["id"] for i in consistency.visible(world.report)["issues"]] == ["a", "n", "f"]

    def test_dismiss_with_a_stale_checked_at_raises_409(self, world):
        with pytest.raises(consistency.FixError) as e:
            consistency.dismiss_many("t", ["p"], "old")
        assert e.value.status == 409 and world.report_saves == 0

    def test_dismissing_twice_does_not_duplicate(self, world):
        consistency.dismiss_many("t", ["p"], CHECKED)
        consistency.dismiss_many("t", ["p"], CHECKED)
        assert world.report["dismissed"] == ["p"]


class TestSectionField:
    def test_sentence_in_section_two_gets_its_key_and_label(self):
        assert consistency.section_of(DESCRIPTION, PRICE) == ("how_to_buy", "How customers buy")
        assert consistency.section_of(DESCRIPTION, NEVER) == ("never", "Never do")

    def test_whitespace_differences_still_locate_the_sentence(self):
        assert consistency.section_of(DESCRIPTION, "Everything  happens\nthrough the app.")[0] == "how_to_buy"

    def test_sentence_in_the_free_text_area_has_no_section(self):
        assert consistency.section_of(DESCRIPTION, "Hello from the Astro team.") == (None, None)

    def test_sentence_that_cannot_be_found_has_no_section(self):
        assert consistency.section_of(DESCRIPTION, "Not written anywhere.") == (None, None)
        assert consistency.section_of(DESCRIPTION, "") == (None, None)

    def test_a_heading_line_is_not_part_of_a_section(self):
        assert consistency.section_of(DESCRIPTION, "HOW CUSTOMERS BUY") == (None, None)

    def test_with_sections_sets_nulls_for_files_and_does_not_mutate(self):
        original = [_issue("p", PRICE, "x"), _issue("f", "Fees", "y", where="knowledge", document_id="d1")]
        out = consistency.with_sections(original, DESCRIPTION)
        assert (out[0]["section"], out[0]["section_label"]) == ("how_to_buy", "How customers buy")
        assert (out[1]["section"], out[1]["section_label"]) == (None, None)
        assert "section" not in original[0]

    def test_handover_sentence_gets_the_eighth_section(self):
        text = "WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM\nCall the app support."
        assert consistency.section_of(text, "Call the app support.") == (
            "handover", "What Aira says when it brings in your team")

    def test_run_check_stores_the_section_on_each_issue(self, monkeypatch):
        import asyncio

        saved = {}
        src = {"description": DESCRIPTION, "handover_line": "", "config": CONFIG, "selling": True, "catalog": [],
               "documents": []}
        monkeypatch.setattr(consistency, "gather", lambda db, t: src)
        monkeypatch.setattr(consistency, "load_report", lambda t: {"dismissed": []})
        monkeypatch.setattr(consistency, "_save_report", lambda t, r: saved.update(r))

        async def no_model(*a, **k):
            return [], True

        monkeypatch.setattr(consistency, "_model_issues", no_model)
        report = asyncio.run(consistency.run_check(object(), "t"))
        by_quote = {i["quote"]: i for i in saved["issues"]}
        assert by_quote[PRICE]["section"] == "how_to_buy"
        assert by_quote[NEVER]["section_label"] == "Never do"
        assert report["dismissed_issues"] == []

    def test_report_saved_before_the_field_gets_it_on_read(self, monkeypatch):
        stored = {"issues": [_issue("p", PRICE, "x"), _issue("o", "Hello from the Astro team.", "x")],
                  "dismissed": ["o"], "fingerprint": "f", "checked_at": CHECKED, "suggestions_complete": True}
        monkeypatch.setattr(consistency, "load_report", lambda t: stored)
        monkeypatch.setattr(consistency, "gather", lambda db, t: {"description": DESCRIPTION})
        monkeypatch.setattr(consistency, "fingerprint", lambda src: "f")
        report = consistency.current_report(object(), "t")
        assert [(i["id"], i["section"]) for i in report["issues"]] == [("p", "how_to_buy")]
        assert report["dismissed_issues"] == [{
            "id": "o", "topic": "t", "quote": "Hello from the Astro team.", "where": "description",
            "document_name": None, "section": None, "section_label": None}]
        assert "section" not in stored["issues"][0]  # the stored report is not mutated

    def test_a_report_that_was_never_checked_has_an_empty_dismissed_list(self, monkeypatch):
        monkeypatch.setattr(consistency, "load_report", lambda t: {})
        assert consistency.current_report(object(), "t")["dismissed_issues"] == []


class TestRoutes:
    @pytest.fixture
    def env(self, monkeypatch):
        world = World().install(monkeypatch)
        background = {"index": [], "recheck": []}

        async def fake_index(tenant_id, document_id, facts, campaign_tag_id):
            background["index"].append((tenant_id, document_id, facts))

        async def fake_recheck(tenant_id):
            background["recheck"].append(tenant_id)

        monkeypatch.setattr(ks, "index_facts", fake_index)
        monkeypatch.setattr(consistency, "run_check_safely", fake_recheck)
        monkeypatch.setattr(routes, "get_supabase", lambda: object())
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1/consistency")
        ctx = {"tenant_id": "t1", "user_id": "u1", "role": "owner"}
        app.dependency_overrides[routes.require_manage] = lambda: ctx
        app.dependency_overrides[routes.require_read] = lambda: ctx
        return type("Env", (), {"client": TestClient(app), "world": world, "background": background, "ctx": ctx})

    def test_fix_batch_returns_the_contract_and_queues_one_recheck_and_one_index(self, env):
        res = env.client.post("/api/v1/consistency/fix-batch", json={"issue_ids": ["p", "a", "f", "ghost"], "checked_at": CHECKED})
        assert res.status_code == 200
        assert res.json() == {"success": True, "applied": ["p", "a", "f"], "skipped": [], "failed": [
            {"id": "ghost", "reason": "Aira no longer sees this problem. Check again.", "code": "not_found"}]}
        assert env.background["recheck"] == ["t1"]
        assert [j[1] for j in env.background["index"]] == ["d1"]

    def test_fix_batch_with_a_stale_checked_at_is_409(self, env):
        res = env.client.post("/api/v1/consistency/fix-batch", json={"issue_ids": ["p"], "checked_at": "old"})
        assert res.status_code == 409 and res.json()["detail"] == "Issues changed, reload"
        assert env.background["recheck"] == []

    def test_non_owner_gets_owner_only_skips(self, env):
        env.ctx["role"] = "custom"
        res = env.client.post("/api/v1/consistency/fix-batch", json={"issue_ids": ["p", "f"], "checked_at": CHECKED})
        body = res.json()
        assert body["applied"] == ["f"] and [s["code"] for s in body["skipped"]] == ["owner_only"]

    @pytest.mark.parametrize("path", ["fix-batch", "dismiss-batch"])
    @pytest.mark.parametrize("ids", [[], ["x"] * 101, [1, 2], "abc", [""], ["y" * 65]])
    def test_bad_issue_ids_are_422(self, env, path, ids):
        res = env.client.post(f"/api/v1/consistency/{path}", json={"issue_ids": ids, "checked_at": CHECKED})
        assert res.status_code == 422

    def test_batch_needs_checked_at(self, env):
        assert env.client.post("/api/v1/consistency/dismiss-batch", json={"issue_ids": ["p"]}).status_code == 422

    def test_exactly_one_hundred_ids_is_allowed(self, env):
        ids = [f"id{i}" for i in range(100)]
        res = env.client.post("/api/v1/consistency/dismiss-batch", json={"issue_ids": ids, "checked_at": CHECKED})
        assert res.status_code == 200 and len(res.json()["skipped"]) == 100

    def test_dismiss_batch_then_restore_then_get(self, env):
        res = env.client.post("/api/v1/consistency/dismiss-batch", json={"issue_ids": ["p", "ghost"], "checked_at": CHECKED})
        assert res.json() == {"success": True, "dismissed": ["p"], "skipped": [
            {"id": "ghost", "reason": "Aira no longer sees this problem.", "code": "not_found"}]}
        got = env.client.get("/api/v1/consistency").json()
        assert [i["id"] for i in got["issues"]] == ["a", "n", "f"]
        assert got["dismissed_issues"][0]["id"] == "p" and got["dismissed_issues"][0]["quote"] == PRICE
        restored = env.client.post("/api/v1/consistency/restore", json={"issue_ids": ["p"]})
        assert restored.json() == {"success": True, "restored": ["p"], "skipped": []}
        assert env.client.get("/api/v1/consistency").json()["dismissed_issues"] == []

    def test_dismiss_batch_with_a_stale_checked_at_is_409(self, env):
        res = env.client.post("/api/v1/consistency/dismiss-batch", json={"issue_ids": ["p"], "checked_at": "old"})
        assert res.status_code == 409

    def test_restore_needs_no_checked_at_but_ids(self, env):
        assert env.client.post("/api/v1/consistency/restore", json={"issue_ids": []}).status_code == 422
