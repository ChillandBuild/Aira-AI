from unittest.mock import MagicMock, patch

import pytest

from app.services import knowledge_versions as kv
from fake_supabase import FakeSupabase

T = "tenant-1"


@pytest.fixture
def settings(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(kv, "get_setting", lambda key, fallback=None, tenant_id=None: store.get((tenant_id, key), fallback))
    monkeypatch.setattr(kv, "save_setting", lambda key, value, tenant_id=None: store.__setitem__((tenant_id, key), value))
    monkeypatch.setattr(kv, "invalidate_cache", lambda key=None: None)
    return store


def test_first_save_records_the_old_text_as_a_baseline(settings):
    db = FakeSupabase()
    settings[(T, "business_description")] = "Old text"
    kv.save_description(db, T, "  New text  ", "edit", "user-1")

    rows = kv.list_versions(db, T, "description")
    assert [(r["reason"], r["content"]) for r in rows] == [("edit", "New text"), ("baseline", "Old text")]
    assert settings[(T, "business_description")] == "New text"
    assert rows[0]["created_by"] == "user-1"


def test_later_saves_write_one_version_each(settings):
    db = FakeSupabase()
    kv.save_description(db, T, "One", "edit", None)
    kv.save_description(db, T, "Two", "edit", None)
    assert [r["content"] for r in kv.list_versions(db, T, "description")] == ["Two", "One", ""]


def test_a_change_made_outside_this_module_gets_its_own_baseline(settings):
    db = FakeSupabase()
    kv.save_description(db, T, "One", "edit", None)
    settings[(T, "business_description")] = "Changed elsewhere"
    version = kv.current_description_version(db, T)
    assert (version["reason"], version["content"]) == ("baseline", "Changed elsewhere")
    assert kv.current_description_version(db, T)["id"] == version["id"]


def test_facts_versions_are_per_document(settings):
    db = FakeSupabase()
    kv.save_facts_version(db, T, "doc-a", "A facts", "upload", None)
    kv.save_facts_version(db, T, "doc-b", "B facts", "upload", None)
    assert [r["content"] for r in kv.list_versions(db, T, "facts", "doc-a")] == ["A facts"]
    assert kv.list_versions(db, T, "description") == []


def test_get_version_is_tenant_scoped(settings):
    db = FakeSupabase()
    version = kv.save_description(db, T, "Mine", "edit", None)
    assert kv.get_version(db, T, version["id"])["content"] == "Mine"
    assert kv.get_version(db, "other-tenant", version["id"]) is None


class TestQueueRubric:
    """queue_rubric_for_description keeps the existing PUT behaviour and adds the
    fill-if-missing case for a Description that just went from empty to filled."""

    def _run(self, auto_update: str, base_was_empty: bool, description: str = "We sell X"):
        from app.routes import ai_tune

        created = MagicMock()
        with patch.object(ai_tune, "get_setting", return_value=auto_update), \
             patch.object(ai_tune, "_auto_generate_rubric", new=MagicMock(return_value="coro")) as gen, \
             patch.object(ai_tune.asyncio, "create_task", return_value=created) as create_task:
            queued = ai_tune.queue_rubric_for_description(T, description, base_was_empty=base_was_empty)
        return queued, gen, create_task

    def test_auto_update_on_regenerates(self):
        queued, gen, create_task = self._run("true", base_was_empty=False)
        assert queued is True
        gen.assert_called_once_with("We sell X", T, force=True)
        create_task.assert_called_once()

    def test_first_description_fills_a_missing_rubric(self):
        queued, gen, _ = self._run("false", base_was_empty=True)
        assert queued is True
        gen.assert_called_once_with("We sell X", T, force=False)

    def test_otherwise_nothing_is_queued(self):
        queued, gen, create_task = self._run("false", base_was_empty=False)
        assert queued is False
        gen.assert_not_called()
        create_task.assert_not_called()

    def test_empty_description_never_queues(self):
        queued, _, _ = self._run("true", base_was_empty=True, description="")
        assert queued is False
