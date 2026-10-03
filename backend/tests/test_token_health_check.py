"""The daily token health check must flag dead tokens (code 190) only, not permission errors."""
import asyncio
from unittest.mock import MagicMock, patch

from app.services.incidents import is_token_auth_failure

PERMISSION_100 = {"code": 100, "message": "(#100) requires pages_read_engagement"}
EXPIRED_190 = {"code": 190, "message": "Error validating access token: Session has expired"}


def test_permission_error_is_not_an_auth_failure():
    assert not is_token_auth_failure(PERMISSION_100)
    assert not is_token_auth_failure(None)


def test_code_190_is_an_auth_failure():
    assert is_token_auth_failure(EXPIRED_190)


def _run_check(error):
    import app.main as main

    db = MagicMock()
    db.table.return_value.select.return_value.in_.return_value.not_.is_.return_value.execute.return_value.data = [
        {"tenant_id": "t1", "key": "instagram_access_token", "value": "tok"},
    ]
    resp = MagicMock()
    resp.json.return_value = {"error": error} if error else {"id": "1"}
    client = MagicMock()

    async def _get(*a, **k):
        return resp

    client.get = _get
    cm = MagicMock()

    async def _enter(*a):
        return client

    async def _exit(*a):
        return False

    cm.__aenter__ = _enter
    cm.__aexit__ = _exit
    with patch("app.db.supabase.get_supabase", return_value=db), \
         patch("httpx.AsyncClient", return_value=cm), \
         patch("app.services.incidents.create_token_incident") as incident:
        asyncio.run(main._check_token_health())
    return incident


def test_health_check_ignores_permission_error():
    assert not _run_check(PERMISSION_100).called


def test_health_check_records_expired_token():
    incident = _run_check(EXPIRED_190)
    assert incident.call_args.args[2] == "instagram"


def test_clear_token_incidents_deletes_only_that_channel():
    from app.services.incidents import clear_token_incidents

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "a", "detail": {"channel": "instagram"}},
        {"id": "b", "detail": {"channel": "facebook"}},
    ]
    clear_token_incidents(db, "t1", "instagram")
    db.table.return_value.delete.return_value.in_.assert_called_once_with("id", ["a"])
