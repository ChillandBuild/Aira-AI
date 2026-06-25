# backend/tests/test_telegram_settings.py
import pytest
from unittest.mock import MagicMock, patch

from app.services.incidents import create_token_incident
from app.services.ai_reply import send_telegram
from app.routes.app_settings import webhook_health, activate_channel, ActivateChannelRequest
from fastapi import HTTPException


def _mock_recent_incidents(db, data):
    """Wire the recent-token_invalid select chain used by create_token_incident."""
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=data)


# ── create_token_incident ─────────────────────────────────────────────────────
def test_create_token_incident_inserts_when_none_recent():
    db = MagicMock()
    _mock_recent_incidents(db, [])

    create_token_incident(db, "tenant-1", "telegram", "Unauthorized")

    insert_call = db.table.return_value.insert
    insert_call.assert_called_once()
    payload = insert_call.call_args[0][0]
    assert payload["tenant_id"] == "tenant-1"
    assert payload["type"] == "token_invalid"
    assert payload["detail"] == {"channel": "telegram", "error": "Unauthorized"}


def test_create_token_incident_deduped_when_same_channel_recent():
    db = MagicMock()
    _mock_recent_incidents(db, [{"detail": {"channel": "telegram"}}])

    create_token_incident(db, "tenant-1", "telegram", "Unauthorized")

    db.table.return_value.insert.assert_not_called()


def test_create_token_incident_not_deduped_across_channels():
    # A recent whatsapp incident must NOT suppress a telegram one (per-channel dedup).
    db = MagicMock()
    _mock_recent_incidents(db, [{"detail": {"channel": "whatsapp"}}])

    create_token_incident(db, "tenant-1", "telegram", "Unauthorized")

    db.table.return_value.insert.assert_called_once()


# ── send_telegram token-invalid detection (401 only) ──────────────────────────
class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = "error"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._resp

    async def get(self, *args, **kwargs):
        return self._resp


@pytest.mark.asyncio
async def test_send_telegram_records_incident_on_401():
    resp = _FakeResp(401, {"description": "Unauthorized"})
    with patch("app.config_dynamic.get_setting", return_value="123:abc"), \
         patch("app.services.ai_reply.httpx.AsyncClient", lambda *a, **k: _FakeClient(resp)), \
         patch("app.services.ai_reply.get_supabase", return_value=MagicMock()), \
         patch("app.services.incidents.create_token_incident") as mock_incident:

        result = await send_telegram("user-1", "hi", tenant_id="tenant-1")

        assert result is None
        mock_incident.assert_called_once()
        assert mock_incident.call_args[0][2] == "telegram"


@pytest.mark.asyncio
async def test_send_telegram_no_incident_on_403_blocked_by_user():
    resp = _FakeResp(403, {"description": "Forbidden: bot was blocked by the user"})
    with patch("app.config_dynamic.get_setting", return_value="123:abc"), \
         patch("app.services.ai_reply.httpx.AsyncClient", lambda *a, **k: _FakeClient(resp)), \
         patch("app.services.ai_reply.get_supabase", return_value=MagicMock()), \
         patch("app.services.incidents.create_token_incident") as mock_incident:

        result = await send_telegram("user-1", "hi", tenant_id="tenant-1")

        assert result is None
        mock_incident.assert_not_called()


# ── webhook-health includes telegram ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_health_includes_telegram():
    db = MagicMock()
    # Per-channel last-event query → no rows
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    # Token-alerts incidents query → no rows
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(data=[])

    with patch("app.routes.app_settings.get_supabase", return_value=db):
        result = await webhook_health(ctx={"tenant_id": "tenant-1"})

    assert "telegram" in result["health"]


# ── activate_channel telegram branch (#6) ─────────────────────────────────────
@pytest.mark.asyncio
async def test_activate_telegram_requires_saved_token():
    db = MagicMock()
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await activate_channel(
                ActivateChannelRequest(channel="telegram"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "u1"},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_activate_telegram_success_return_shape():
    db = MagicMock()

    class _FakeMeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"id": 42, "username": "AiraBot"}}

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="123:abc"), \
         patch("app.routes.app_settings.setup_telegram_webhook", return_value=(True, "secret-xyz", None)), \
         patch("app.routes.app_settings.httpx.AsyncClient", lambda *a, **k: _FakeClient(_FakeMeResp())), \
         patch("app.routes.app_settings.record_audit_event"):
        result = await activate_channel(
            ActivateChannelRequest(channel="telegram"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "u1"},
        )

    assert result["channel"] == "telegram"
    assert result["subscribed"] is True
    assert result["page_name"] == "@AiraBot"
    assert result["page_id"] == "42"
