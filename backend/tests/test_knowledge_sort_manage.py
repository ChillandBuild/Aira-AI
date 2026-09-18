import pytest

from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv
from knowledge_sort_helpers import T, add_doc, env  # noqa: F401  (env is a fixture)

DESC = "ABOUT US\nWe are AstroTamil.\n\nRULES\n- Never predict.\n- Shared rule.\n- Never ask for DOB in chat."


def _setup(env):
    env.set_description(DESC)
    kv.current_description_version(env.db, T)
    other = add_doc(env.db, name="other.docx", status="indexed", sorted_at="x", rule_lines=["- Shared rule."])
    doc = add_doc(
        env.db, name="rules.docx", status="indexed", sorted_at="x", full_text="Price 29.",
        rule_lines=["- Never predict.", "- Shared rule.", "- Never ask for date of birth in chat."],
    )
    env.db.add("knowledge_chunks", tenant_id=T, document_id=doc["id"], content="Price 29.")
    return doc, other


# ─── facts ────────────────────────────────────────────────────────────────────

def test_editing_facts_needs_a_sorted_file(env):
    legacy = add_doc(env.db, status="indexed", full_text="raw")
    with pytest.raises(ks.SortError, match="Sort this file"):
        ks.update_facts(env.db, T, legacy["id"], "x", None)


def test_editing_facts_versions_them_and_clears_old_chunks(env):
    doc, _ = _setup(env)
    result = ks.update_facts(env.db, T, doc["id"], "  Price 49.  ", "u1")
    assert result["facts"] == "Price 49."
    saved = next(d for d in env.db.rows("knowledge_documents") if d["id"] == doc["id"])
    assert saved["full_text"] == "Price 49."
    assert [v["reason"] for v in kv.list_versions(env.db, T, "facts", doc["id"])] == ["edit"]
    assert env.db.rows("knowledge_chunks") == []


# ─── delete ───────────────────────────────────────────────────────────────────

def test_delete_preview_lists_own_lines_keeps_shared_and_finds_edited(env):
    doc, _ = _setup(env)
    preview = ks.build_delete_preview(env.db, T, doc["id"])
    assert preview["remove_lines"] == ["- Never predict."]
    assert preview["edited_lines"] == [
        {"original": "- Never ask for date of birth in chat.", "current": "- Never ask for DOB in chat."}
    ]
    assert preview["chunk_count"] == 1 and preview["has_facts"] is True
    assert preview["description_will_change"] is True


def test_delete_keeps_edited_lines_by_default(env):
    doc, _ = _setup(env)
    base = ks.build_delete_preview(env.db, T, doc["id"])["base_version_id"]
    result = ks.delete_document(env.db, T, doc["id"], base_version_id=base, remove_edited=[], user_id=None, is_owner=True)
    assert result["description_changed"] is True
    assert "- Never predict." not in env.description()
    assert "- Shared rule." in env.description()
    assert "- Never ask for DOB in chat." in env.description()
    assert [d["name"] for d in env.db.rows("knowledge_documents")] == ["other.docx"]
    assert kv.list_versions(env.db, T, "description")[0]["reason"] == "delete_document"


def test_delete_removes_an_edited_line_when_asked(env):
    doc, _ = _setup(env)
    base = ks.build_delete_preview(env.db, T, doc["id"])["base_version_id"]
    ks.delete_document(
        env.db, T, doc["id"], base_version_id=base, remove_edited=["- Never ask for DOB in chat."], user_id=None, is_owner=True
    )
    assert "DOB" not in env.description()


def test_delete_refuses_a_stale_preview_and_a_non_owner(env):
    doc, _ = _setup(env)
    with pytest.raises(ks.StaleError):
        ks.delete_document(env.db, T, doc["id"], base_version_id="old", remove_edited=[], user_id=None, is_owner=True)
    with pytest.raises(ks.OwnerRequiredError):
        ks.delete_document(env.db, T, doc["id"], base_version_id=None, remove_edited=[], user_id=None, is_owner=False)
    assert len(env.db.rows("knowledge_documents")) == 2


def test_a_manager_can_delete_a_file_that_adds_no_lines(env):
    _setup(env)
    faq = add_doc(env.db, name="faq.txt", status="indexed", sorted_at="x", full_text="Q/A")
    result = ks.delete_document(env.db, T, faq["id"], base_version_id=None, remove_edited=[], user_id=None, is_owner=False)
    assert result["description_changed"] is False
    assert env.description() == DESC


# ─── restore ──────────────────────────────────────────────────────────────────

def test_restoring_a_description_writes_a_new_version(env):
    env.set_description("First")
    first = kv.current_description_version(env.db, T)
    kv.save_description(env.db, T, "Second", "edit", None)

    result = ks.restore_version(env.db, T, first["id"], user_id="u1", is_owner=True)
    assert result["description_changed"] is True
    assert env.description() == "First"
    assert [v["reason"] for v in kv.list_versions(env.db, T, "description")] == ["restore", "edit", "baseline"]


def test_restoring_an_empty_version_or_as_a_non_owner_is_refused(env):
    empty = kv.current_description_version(env.db, T)
    kv.save_description(env.db, T, "Now filled", "edit", None)
    with pytest.raises(ks.EmptyDescriptionError):
        ks.restore_version(env.db, T, empty["id"], user_id=None, is_owner=True)

    filled = kv.save_description(env.db, T, "Newer", "edit", None)
    kv.save_description(env.db, T, "Newest", "edit", None)
    with pytest.raises(ks.OwnerRequiredError):
        ks.restore_version(env.db, T, filled["id"], user_id=None, is_owner=False)


def test_restoring_facts_rewrites_the_document(env):
    doc, _ = _setup(env)
    ks.update_facts(env.db, T, doc["id"], "Price 49.", None)
    old = kv.list_versions(env.db, T, "facts", doc["id"])[0]
    ks.update_facts(env.db, T, doc["id"], "Price 59.", None)

    result = ks.restore_version(env.db, T, old["id"], user_id=None, is_owner=False)
    assert result == {"kind": "facts", "document_id": doc["id"], "facts": "Price 49.", "campaign_tag_id": None}
    saved = next(d for d in env.db.rows("knowledge_documents") if d["id"] == doc["id"])
    assert saved["full_text"] == "Price 49."


def test_restoring_an_unknown_version_is_not_found(env):
    with pytest.raises(ks.NotFoundError):
        ks.restore_version(env.db, T, "missing", user_id=None, is_owner=True)
