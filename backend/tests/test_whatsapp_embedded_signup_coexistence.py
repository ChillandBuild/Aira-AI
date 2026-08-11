from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_coexistence_signup_skips_phone_registration():
    from app.routes.app_settings import EmbeddedSignupRequest, whatsapp_embedded_signup

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp({"success": True})
        async def get(self, url, **kwargs):
            return _Resp({"display_phone_number": "+919999999999", "verified_name": "Bloom Matrix"})

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock()) as register, \
         patch("app.services.meta_cloud.request_coexistence_sync", new=AsyncMock()) as sync_trigger, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        result = await whatsapp_embedded_signup(
            EmbeddedSignupRequest(
                code="single-use-code",
                waba_id="waba-1",
                phone_number_id="phone-1",
                is_coexistence=True,
            ),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    register.assert_not_called()
    sync_trigger.assert_awaited_once_with("phone-1", "token-1")
    assert result["success"] is True
    assert result["phone_number"] == "+919999999999"


@pytest.mark.asyncio
async def test_standard_signup_still_registers_the_phone_number():
    from app.routes.app_settings import EmbeddedSignupRequest, whatsapp_embedded_signup

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp({"success": True})
        async def get(self, url, **kwargs):
            return _Resp({"display_phone_number": "+919999999999", "verified_name": "Bloom Matrix"})

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})) as register, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        await whatsapp_embedded_signup(
            EmbeddedSignupRequest(
                code="single-use-code",
                waba_id="waba-1",
                phone_number_id="phone-1",
            ),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    register.assert_awaited_once()
