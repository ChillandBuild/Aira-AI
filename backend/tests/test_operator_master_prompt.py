"""The master prompt is platform-wide: one row in platform_defaults, read at reply
time by every tenant. These cover the reader and its fallbacks -- a bad read must
degrade to FALLBACK_PROMPT, never blow up a reply or client creation.
"""
from unittest.mock import MagicMock, patch

from app.routes import operator
from app.services import ai_reply
from app.services.ai_reply import FALLBACK_PROMPT


def _db_returning(rows):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = rows
    return db


def setup_function():
    ai_reply.invalidate_prompt_cache()


def teardown_function():
    ai_reply.invalidate_prompt_cache()


def test_template_routes_exist():
    paths = {route.path for route in operator.router.routes}
    assert "/prompt-template" in paths


def test_get_master_prompt_returns_stored_template():
    with patch.object(ai_reply, "get_supabase", return_value=_db_returning([{"value": "STORED TEMPLATE"}])):
        assert ai_reply.get_master_prompt() == "STORED TEMPLATE"


def test_get_master_prompt_falls_back_when_table_unreadable():
    """A reply must still go out if platform_defaults cannot be read."""
    db = MagicMock()
    db.table.side_effect = Exception("relation does not exist")
    with patch.object(ai_reply, "get_supabase", return_value=db):
        assert ai_reply.get_master_prompt() == FALLBACK_PROMPT


def test_get_master_prompt_falls_back_when_row_missing():
    with patch.object(ai_reply, "get_supabase", return_value=_db_returning([])):
        assert ai_reply.get_master_prompt() == FALLBACK_PROMPT


def test_get_master_prompt_falls_back_on_whitespace_only_row():
    with patch.object(ai_reply, "get_supabase", return_value=_db_returning([{"value": "   \n "}])):
        assert ai_reply.get_master_prompt() == FALLBACK_PROMPT


def test_get_master_prompt_is_cached_between_calls():
    db = _db_returning([{"value": "STORED TEMPLATE"}])
    with patch.object(ai_reply, "get_supabase", return_value=db):
        ai_reply.get_master_prompt()
        ai_reply.get_master_prompt()
    assert db.table.call_count == 1


def test_invalidate_prompt_cache_forces_a_reread():
    """Saving on the operator's Master Prompt page must take effect immediately --
    there is no per-client copy to fall back on."""
    db = _db_returning([{"value": "FIRST"}])
    with patch.object(ai_reply, "get_supabase", return_value=db):
        assert ai_reply.get_master_prompt() == "FIRST"
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": "SECOND"}
        ]
        assert ai_reply.get_master_prompt() == "FIRST"  # still cached
        ai_reply.invalidate_prompt_cache()
        assert ai_reply.get_master_prompt() == "SECOND"
