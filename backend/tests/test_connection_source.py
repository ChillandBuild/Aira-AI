from unittest.mock import MagicMock, patch

import pytest


def _upserted(db):
    """Every row app_settings upserted during the call, keyed by setting key."""
    rows = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    return {row["key"]: row for row in rows if "key" in row}


@pytest.mark.asyncio
async def test_manual_credential_save_marks_only_the_touched_channel_as_manual():
    """Breaks if a manual token save silently keeps an 'embedded' badge on the card."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"instagram_access_token": "IGQV-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["instagram_connection_source"]["value"] == "manual"
    assert rows["instagram_connection_source"]["is_secret"] is False
    assert "whatsapp_connection_source" not in rows
    assert "facebook_connection_source" not in rows
    assert "meta_ads_connection_source" not in rows


@pytest.mark.asyncio
async def test_manual_credential_save_still_resets_channel_status_to_configured():
    """Breaks if folding the status reset into the shared channel map loses the reset."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"meta_access_token": "EAAG-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["whatsapp_status"]["value"] == "configured"
    assert rows["whatsapp_connection_source"]["value"] == "manual"


@pytest.mark.asyncio
async def test_non_channel_settings_never_stamp_a_connection_source():
    """Breaks if unrelated settings writes pollute the channel source markers."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"groq_api_key": "gsk-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert not [key for key in _upserted(db) if key.endswith("_connection_source")]


class _StubResponse:
    def __init__(self, data: dict):
        self._data = data

    def json(self):
        return self._data


class _StubMetaClient:
    """Mimics the Graph calls complete_unified_meta_signup makes, in order."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, **_):
        return _StubResponse({"success": True})

    async def get(self, url, **_):
        return _StubResponse({"display_phone_number": "+919999999999", "verified_name": "Bloom"})


@pytest.mark.asyncio
async def test_unified_signup_marks_every_provisioned_channel_as_embedded():
    """Breaks if a Meta-provisioned channel shows up in the manual grid as hand-configured."""
    from unittest.mock import AsyncMock

    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{
            "id": "page-1",
            "name": "Bloom Matrix",
            "access_token": "page-token",
            "instagram_business_account": {"id": "ig-1"},
        }],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads"}],
        "catalogs": [],
    }
    staged_values = [
        "business-token", "session-1", "2999-01-01T00:00:00+00:00",
        "waba-1", "phone-1", None, "false",
    ]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged_values), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=True)), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id="act_42"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    for channel in ("whatsapp", "facebook", "instagram", "meta_ads"):
        assert rows[f"{channel}_connection_source"]["value"] == "embedded", channel


@pytest.mark.asyncio
async def test_unified_signup_without_an_ad_account_leaves_ads_unstamped():
    """Breaks if Meta Ads is labelled connected-via-Meta when no ad account was granted."""
    from unittest.mock import AsyncMock

    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{"id": "page-1", "name": "Bloom Matrix", "access_token": "page-token"}],
        "ad_accounts": [],
        "catalogs": [],
    }
    staged_values = [
        "business-token", "session-1", "2999-01-01T00:00:00+00:00",
        "waba-1", "phone-1", None, "false",
    ]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged_values), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=True)), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id=None),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["whatsapp_connection_source"]["value"] == "embedded"
    assert rows["facebook_connection_source"]["value"] == "embedded"
    assert "instagram_connection_source" not in rows
    assert "meta_ads_connection_source" not in rows
