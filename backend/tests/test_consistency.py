"""Aira's sources must not contradict the Services page (services/consistency.py).
Cases mirror the real Astro Tamil setup found 2026-09-26: an app price of ₹29 in the
Description while ₹49/₹99 is sold in chat, 'never ask for DOB' while DOB is a required
detail, and a handover line that sends people to the app's support."""
import asyncio

import pytest

from app.services import consistency

CONFIG = {
    "enabled": True,
    "fields": [{"key": "name", "label": "Name", "type": "text"},
               {"key": "date_of_birth", "label": "Date of birth", "type": "text"}],
    "packages": [{"key": "one", "name": "One Question", "amount_paise": 4900},
                 {"key": "detailed", "name": "Detailed Question", "amount_paise": 9900}],
}
DESCRIPTION = (
    "HOW CUSTOMERS BUY\n"
    "Accurate guidance starts from ₹29. Everything happens through the app.\n"
    "WHAT YOU MUST NEVER DO\n"
    "Never ask for DOB, TOB, or POB.\n"
    "Be kind."
)
HANDOVER = "App la irukkura support option moolama contact pannalam."


def _src(**over):
    base = {
        "description": DESCRIPTION, "handover_line": HANDOVER, "config": CONFIG, "selling": True,
        "catalog": [], "documents": [{"id": "d1", "name": "kb.docx", "text": "Fees: Rs 49 per question.", "editable": True}],
    }
    return {**base, **over}


class TestDeterministic:
    def test_price_not_on_services_page(self):
        issues = consistency.price_issues(_src())
        assert len(issues) == 1
        assert issues[0]["where"] == "description" and "₹29" in issues[0]["quote"]
        assert "₹29" in issues[0]["topic"] and "₹49" in issues[0]["truth"]

    def test_real_price_in_knowledge_is_fine(self):
        assert all(i["where"] != "knowledge" for i in consistency.price_issues(_src()))

    def test_no_structured_prices_means_nothing_to_compare(self):
        assert consistency.price_issues(_src(selling=False)) == []

    def test_catalog_prices_count_as_truth(self):
        src = _src(selling=False, catalog=[{"name": "Kit", "price_paise": 2900}])
        issues = consistency.price_issues(src)
        assert [i["where"] for i in issues] == ["knowledge"]  # ₹29 is the Kit; Rs 49 is sold nowhere

    def test_never_ask_for_a_required_detail(self):
        issues = consistency.never_ask_issues(_src())
        assert [i["quote"] for i in issues] == ["Never ask for DOB, TOB, or POB."]
        assert "Date of birth" in issues[0]["topic"]

    def test_never_ask_ignored_when_not_selling(self):
        assert consistency.never_ask_issues(_src(selling=False)) == []

    def test_handover_line_that_sends_people_elsewhere(self):
        issues = consistency.handover_issues(_src())
        assert issues and issues[0]["where"] == "handover_line"

    def test_in_chat_handover_line_is_fine(self):
        assert consistency.handover_issues(_src(handover_line="I'll check with the team, they'll reply here.")) == []


class TestModelValidation:
    def test_quote_must_be_in_the_named_source(self):
        items = [
            {"where": "description", "quote": "Everything happens through the app.", "topic": "Where to buy",
             "proposed": "You can book and pay right here in chat."},
            {"where": "description", "quote": "A line that is not there", "proposed": ""},
            {"where": "knowledge", "document_name": "missing.docx", "quote": "Fees", "proposed": ""},
        ]
        out = consistency.validate_model_issues(items, _src())
        assert len(out) == 1
        assert out[0]["quote"] == "Everything happens through the app."  # the sentence, not its paragraph
        assert out[0]["proposed"] == "You can book and pay right here in chat."

    def test_proposed_fix_may_not_invent_a_price(self):
        items = [{"where": "description", "quote": "Accurate guidance starts from ₹29.", "proposed": "Starts from ₹19."}]
        assert consistency.validate_model_issues(items, _src())[0]["proposed"] is None

    def test_proposed_fix_may_use_a_services_page_price(self):
        items = [{"where": "description", "quote": "Accurate guidance starts from ₹29.",
                  "proposed": "Accurate guidance starts from ₹49."}]
        assert consistency.validate_model_issues(items, _src())[0]["proposed"] == "Accurate guidance starts from ₹49."


class TestMerge:
    def test_one_issue_per_line_and_deterministic_topic_wins(self):
        det = consistency.price_issues(_src())
        model = consistency.validate_model_issues(
            [{"where": "description", "quote": det[0]["quote"], "topic": "vague", "proposed": "Starts from ₹49 here in chat."}],
            _src(),
        )
        merged = consistency.merge(det, model)
        assert len(merged) == 1 and merged[0]["topic"] == det[0]["topic"]
        assert merged[0]["proposed"] == "Starts from ₹49 here in chat." and merged[0]["id"]


class TestReplaceLine:
    def test_one_sentence_inside_a_paragraph(self):
        text = "HOW CUSTOMERS BUY\nDownload the app. Starts from ₹29. No office to visit."
        out = consistency._replace_line(text, "Starts from ₹29.", "Consultations are ₹49 or ₹99, paid right here in chat.")
        assert out == "HOW CUSTOMERS BUY\nDownload the app. Consultations are ₹49 or ₹99, paid right here in chat. No office to visit."

    def test_removing_a_sentence_leaves_the_rest(self):
        assert consistency._replace_line("A one. Never ask for DOB. B two.", "Never ask for DOB.", "") == "A one. B two."

    def test_replaces_only_that_line_and_keeps_indent(self):
        assert consistency._replace_line("a\n  old line\nb", "old line", "new line") == "a\n  new line\nb"

    def test_empty_proposal_removes_the_line(self):
        assert consistency._replace_line("a\nold\nb", "old", "") == "a\nb"

    def test_changed_source_is_a_conflict(self):
        with pytest.raises(consistency.FixError) as e:
            consistency._replace_line("a\nb", "old", "x")
        assert e.value.status == 409


class TestApplyFix:
    def _report(self, monkeypatch, issue):
        saved = {}
        monkeypatch.setattr(consistency, "load_report", lambda tenant_id: {"issues": [issue], "dismissed": []})
        monkeypatch.setattr(consistency, "_save_report", lambda tenant_id, report: saved.update(report))
        monkeypatch.setattr(consistency, "gather", lambda db, tenant_id: _src())
        return saved

    def test_description_fix_needs_an_owner(self, monkeypatch):
        issue = {"id": "i1", "where": "description", "quote": "Never ask for DOB, TOB, or POB.", "proposed": ""}
        self._report(monkeypatch, issue)
        with pytest.raises(consistency.FixError) as e:
            consistency.apply_fix(object(), "t", "i1", user_id="u", is_owner=False)
        assert e.value.status == 403

    def test_description_fix_saves_a_new_version(self, monkeypatch):
        from app.services import knowledge_versions as kv

        issue = {"id": "i1", "where": "description", "quote": "Never ask for DOB, TOB, or POB.", "proposed": ""}
        saved = self._report(monkeypatch, issue)
        writes = []
        monkeypatch.setattr(kv, "current_description", lambda tenant_id: DESCRIPTION)
        monkeypatch.setattr(kv, "save_description", lambda db, t, text, reason, user: writes.append((text, reason)))
        consistency.apply_fix(object(), "t", "i1", user_id="u", is_owner=True)
        assert "Never ask for DOB" not in writes[0][0] and writes[0][1] == "consistency_fix"
        assert saved["issues"] == []

    def test_handover_fix_writes_the_setting(self, monkeypatch):
        issue = {"id": "h", "where": "handover_line", "quote": HANDOVER, "proposed": "Team kitta check panni inga reply pannuvanga."}
        self._report(monkeypatch, issue)
        writes = {}
        monkeypatch.setattr(consistency, "save_setting", lambda key, value, tenant_id: writes.update({key: value}))
        monkeypatch.setattr(consistency, "invalidate_cache", lambda key=None: None)
        consistency.apply_fix(object(), "t", "h", user_id="u", is_owner=False)
        assert writes["handover_line"] == "Team kitta check panni inga reply pannuvanga."

    def test_new_wording_with_an_invented_price_is_refused(self, monkeypatch):
        issue = {"id": "p", "where": "handover_line", "quote": HANDOVER, "proposed": None}
        self._report(monkeypatch, issue)
        with pytest.raises(consistency.FixError):
            consistency.apply_fix(object(), "t", "p", user_id="u", is_owner=True, text="Only ₹19 today!")

    def test_legacy_file_cannot_be_auto_fixed(self, monkeypatch):
        issue = {"id": "k", "where": "knowledge", "quote": "x", "proposed": "", "editable": False, "document_id": "d1"}
        self._report(monkeypatch, issue)
        with pytest.raises(consistency.FixError) as e:
            consistency.apply_fix(object(), "t", "k", user_id="u", is_owner=True)
        assert "Re-sort" in str(e.value)


def test_run_check_keeps_deterministic_findings_when_the_model_fails(monkeypatch):
    saved = {}
    monkeypatch.setattr(consistency, "gather", lambda db, tenant_id: _src())
    monkeypatch.setattr(consistency, "load_report", lambda tenant_id: {"dismissed": []})
    monkeypatch.setattr(consistency, "_save_report", lambda tenant_id, report: saved.update(report))

    async def broken(*a, **k):
        return []

    monkeypatch.setattr(consistency, "_model_issues", broken)
    report = asyncio.run(consistency.run_check(object(), "t"))
    kinds = sorted(i["kind"] for i in report["issues"])
    assert kinds == ["handover", "price", "required_detail"]
    assert saved["fingerprint"]


def test_dismissed_issues_are_hidden():
    report = {"issues": [{"id": "a"}, {"id": "b"}], "dismissed": ["a"]}
    assert [i["id"] for i in consistency.visible(report)["issues"]] == ["b"]
