import pytest
from unittest.mock import MagicMock, patch

from app.config_dynamic import get_setting, invalidate_cache, require_tenant_setting


@pytest.fixture(autouse=True)
def _clear_setting_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def test_require_tenant_setting_returns_value_when_configured():
    with patch("app.config_dynamic.get_setting", return_value="the-key"):
        assert require_tenant_setting("gemini_api_key", "tenant-1") == "the-key"


def test_require_tenant_setting_raises_when_not_configured():
    with patch("app.config_dynamic.get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="gemini_api_key not configured for this client"):
            require_tenant_setting("gemini_api_key", "tenant-1")


def test_require_tenant_setting_raises_when_no_tenant_id():
    with patch("app.config_dynamic.get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="openai_api_key not configured for this client"):
            require_tenant_setting("openai_api_key", None)


def _mock_db(*, side_effects):
    """Build a MagicMock db whose app_settings select().eq().eq().maybe_single().execute()
    calls raise/return in sequence, mirroring the get_setting query chain."""
    execute = MagicMock(side_effect=side_effects)
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute = execute
    return db, execute


def test_get_setting_retries_once_on_transient_failure_then_succeeds():
    """A single dropped connection (e.g. Supabase 'Server disconnected') must not be
    reported as 'not configured' — the retry should recover silently."""
    ok_result = MagicMock(data={"value": "the-token"})
    db, execute = _mock_db(side_effects=[ConnectionError("Server disconnected"), ok_result])

    with patch("app.db.supabase.get_supabase", return_value=db):
        value = get_setting("meta_access_token", tenant_id="tenant-x")

    assert value == "the-token"
    assert execute.call_count == 2


def test_get_setting_does_not_cache_a_failed_read():
    """If both attempts fail, the None must not be cached — otherwise a transient
    outage would masquerade as 'not configured' for the rest of the cache TTL."""
    db, execute = _mock_db(side_effects=[ConnectionError("boom"), ConnectionError("boom")])

    with patch("app.db.supabase.get_supabase", return_value=db):
        first = get_setting("meta_access_token", tenant_id="tenant-y")
        second = get_setting("meta_access_token", tenant_id="tenant-y")

    assert first is None
    assert second is None
    # No caching on failure means every call re-attempts both tries against the DB.
    assert execute.call_count == 4


def test_get_setting_caches_a_successful_read():
    ok_result = MagicMock(data={"value": "cached-value"})
    db, execute = _mock_db(side_effects=[ok_result])

    with patch("app.db.supabase.get_supabase", return_value=db):
        first = get_setting("meta_access_token", tenant_id="tenant-z")
        second = get_setting("meta_access_token", tenant_id="tenant-z")

    assert first == "cached-value"
    assert second == "cached-value"
    assert execute.call_count == 1
