from unittest.mock import MagicMock, patch

import pytest


def _deleted_keys(db):
    """Setting keys the call deleted, across every .delete().eq().in_() chain."""
    keys = []
    for call in db.table.return_value.delete.return_value.eq.return_value.in_.call_args_list:
        keys.extend(call.args[1])
    return keys


class _StubResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _StubGraphClient:
    """Records the Graph calls disconnect makes so tests can assert on them."""

    calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def delete(self, url, **_):
        type(self).calls.append(url)
        return _StubResponse({"success": True})


@pytest.mark.asyncio
async def test_disconnecting_instagram_never_touches_the_page_subscription():
    """Breaks if dropping Instagram silently kills Messenger — they share the Page webhook."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="instagram", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert _StubGraphClient.calls == []
    assert "instagram_access_token" in _deleted_keys(db)


@pytest.mark.asyncio
async def test_shared_meta_keys_survive_while_another_meta_channel_is_connected():
    """Breaks if disconnecting Ads deletes the app secret that verifies WhatsApp webhooks."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    db = MagicMock()

    # Every lookup returns a value: WhatsApp is still fully configured.
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="meta_ads", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    deleted = _deleted_keys(db)
    assert "meta_ads_access_token" in deleted
    assert "meta_app_secret" not in deleted
    assert "meta_webhook_verify_token" not in deleted


@pytest.mark.asyncio
async def test_shared_meta_keys_go_when_the_last_meta_channel_disconnects():
    """Breaks if a full Meta teardown leaves the app secret behind as orphaned config."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    db = MagicMock()
    _StubGraphClient.calls = []

    # Nothing is configured after the teardown.
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value=None), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="meta", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    deleted = _deleted_keys(db)
    assert "meta_app_secret" in deleted
    assert "meta_webhook_verify_token" in deleted


@pytest.mark.asyncio
async def test_assets_are_released_only_when_the_caller_opts_in():
    """Breaks if a routine disconnect frees the tenant's number for another workspace."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="asset-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )
    assert db.rpc.call_count == 0

    db2 = MagicMock()
    _StubGraphClient.calls = []
    with patch("app.routes.app_settings.get_supabase", return_value=db2), \
         patch("app.routes.app_settings._get_setting_value", return_value="asset-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=True),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    name, payload = db2.rpc.call_args.args
    assert name == "release_meta_assets"
    assert payload["p_tenant_id"] == "tenant-1"
    assert {a["asset_type"] for a in payload["p_assets"]} == {
        "whatsapp_business_account", "whatsapp_phone_number",
    }


@pytest.mark.asyncio
async def test_a_failed_meta_unsubscribe_still_completes_the_local_teardown():
    """Breaks if an already-revoked token leaves the tenant unable to disconnect at all."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    class _FailingClient(_StubGraphClient):
        async def delete(self, url, **_):
            raise RuntimeError("token revoked")

    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_FailingClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        result = await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result["results"][0]["webhook_unsubscribed"] is False
    assert "meta_access_token" in _deleted_keys(db)


@pytest.mark.asyncio
async def test_disconnecting_whatsapp_deactivates_rather_than_deletes_its_phone_number():
    """Breaks if call and message history loses its phone_numbers foreign key."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="phone-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    # "archived" is the only teardown status phone_numbers_status_check accepts.
    assert {"status": "archived", "paused_outbound": True} in update_payloads
    assert db.table.return_value.delete.return_value.eq.return_value.eq.call_count == 0


@pytest.mark.asyncio
async def test_disconnect_completes_even_if_archiving_the_phone_number_fails():
    """Breaks if a phone_numbers write error strands the tenant with an unsubscribed
    webhook and live credentials — delivery dead, dashboard still showing connected."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.side_effect = (
        Exception('violates check constraint "phone_numbers_status_check"')
    )

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="phone-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert "meta_access_token" in _deleted_keys(db)
