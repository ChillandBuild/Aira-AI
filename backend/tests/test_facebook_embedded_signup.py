from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_unified_meta_signup_stages_whatsapp_and_returns_only_safe_asset_choices():
    """Breaks if the one-time code leaks a token or loses WhatsApp onboarding data."""
    from app.routes.app_settings import UnifiedMetaSignupStartRequest, start_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{
            "id": "page-1",
            "name": "Bloom Matrix",
            "access_token": "page-token-must-not-leave-server",
            "instagram_business_account": {"id": "ig-1", "username": "bloom"},
        }],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads", "account_id": "42"}],
        "catalogs": [],
    }

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "business-token"})), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.get_supabase", return_value=db):
        result = await start_unified_meta_signup(
            UnifiedMetaSignupStartRequest(
                code="single-use-code",
                waba_id="waba-1",
                phone_number_id="phone-1",
                business_id="business-1",
            ),
            ctx={"tenant_id": "tenant-1"},
        )

    assert result["pages"] == [{
        "id": "page-1",
        "name": "Bloom Matrix",
        "instagram_business_account": {"id": "ig-1", "username": "bloom"},
    }]
    assert result["ad_accounts"] == [{"id": "act_42", "name": "Bloom Ads", "account_id": "42"}]
    assert "catalogs" not in result
    assert "page-token-must-not-leave-server" not in str(result)
    assert "business-token" not in str(result)

    stored = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    assert {row["key"] for row in stored if "key" in row} >= {
        "meta_business_onboarding_token",
        "meta_business_onboarding_waba_id",
        "meta_business_onboarding_phone_number_id",
    }
    token_row = next(row for row in stored if row.get("key") == "meta_business_onboarding_token")
    waba_row = next(row for row in stored if row.get("key") == "meta_business_onboarding_waba_id")
    phone_row = next(row for row in stored if row.get("key") == "meta_business_onboarding_phone_number_id")
    assert token_row["value"] == "business-token"
    assert token_row["is_secret"] is True
    assert waba_row["value"] == "waba-1"
    assert phone_row["value"] == "phone-1"


class _UnifiedResponse:
    def __init__(self, data: dict):
        self._data = data

    def json(self):
        return self._data


class _UnifiedMetaClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _UnifiedResponse({"success": True})

    async def get(self, url, *args, **kwargs):
        assert url.endswith("/phone-1")
        return _UnifiedResponse({"display_phone_number": "+919999999999", "verified_name": "Bloom Matrix"})


@pytest.mark.asyncio
async def test_unified_meta_signup_completion_saves_whatsapp_and_the_selected_assets_together():
    """Breaks if a unified signup saves only one channel or claims an unselected asset."""
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
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_UnifiedMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        result = await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id="act_42"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result == {
        "success": True,
        "phone_number": "+919999999999",
        "page_id": "page-1",
        "instagram_connected": True,
        "ad_account_id": "act_42",
    }
    stored = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    assert {row["key"] for row in stored if "key" in row} >= {
        "meta_access_token", "meta_phone_number_id", "meta_waba_id", "whatsapp_status",
        "facebook_access_token", "facebook_page_id", "instagram_page_id",
        "meta_ads_access_token", "meta_ads_account_id", "meta_ads_status",
    }
    db.rpc.assert_called_once_with("claim_meta_assets", {
        "p_tenant_id": "tenant-1",
        "p_assets": [
            {"asset_type": "facebook_page", "asset_id": "page-1"},
            {"asset_type": "instagram_account", "asset_id": "ig-1"},
            {"asset_type": "whatsapp_business_account", "asset_id": "waba-1"},
            {"asset_type": "whatsapp_phone_number", "asset_id": "phone-1"},
            {"asset_type": "ad_account", "asset_id": "act_42"},
        ],
    })


@pytest.mark.asyncio
async def test_unified_meta_signup_coexistence_never_reregisters_the_business_app_number():
    """Breaks if a coexistence signup tries to register an already active app number."""
    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{"id": "page-1", "name": "Bloom", "access_token": "page-token"}],
        "ad_accounts": [],
        "catalogs": [],
    }
    registration = AsyncMock(return_value={"success": True})
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=[
             "business-token", "session-1", "2999-01-01T00:00:00+00:00", "waba-1", "phone-1", None, "true",
         ]), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=True)), \
         patch("app.services.meta_cloud.register_phone_number", new=registration), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_UnifiedMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    registration.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_meta_signup_rejects_an_ad_account_not_granted_by_meta():
    """Breaks if a caller can attach another business's ad account to its workspace."""
    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    discovered = {
        "pages": [{"id": "page-1", "name": "Bloom", "access_token": "page-token"}],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads"}],
        "catalogs": [],
    }
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=[
             "business-token", "session-1", "2999-01-01T00:00:00+00:00", "waba-1", "phone-1", None, "false",
         ]), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)):
        with pytest.raises(HTTPException) as exc:
            await complete_unified_meta_signup(
                UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id="act-other"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "user-1"},
            )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_unified_meta_signup_rejects_a_phone_number_not_owned_by_the_granted_waba():
    """Breaks if a workspace can claim another business's WhatsApp phone number."""
    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    discovered = {"pages": [{"id": "page-1", "name": "Bloom", "access_token": "page-token"}], "ad_accounts": [], "catalogs": []}
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=[
             "business-token", "session-1", "2999-01-01T00:00:00+00:00", "waba-1", "phone-other", None, "false",
         ]), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            await complete_unified_meta_signup(
                UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "user-1"},
            )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_business_login_start_returns_safe_assets_and_stores_only_server_side_session():
    from app.routes.app_settings import MetaBusinessLoginStartRequest, start_meta_business_login

    db = MagicMock()
    discovered = {
        "pages": [{
            "id": "page-1",
            "name": "Bloom Matrix",
            "access_token": "page-token-must-not-leave-server",
            "instagram_business_account": {"id": "ig-1", "username": "bloom"},
        }],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads", "account_id": "42"}],
        "catalogs": [{"id": "catalog-1", "name": "Bloom Products"}],
    }

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "business-token"})), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.get_supabase", return_value=db):
        result = await start_meta_business_login(
            MetaBusinessLoginStartRequest(code="single-use-code"),
            ctx={"tenant_id": "tenant-1"},
        )

    assert result["pages"] == [{
        "id": "page-1",
        "name": "Bloom Matrix",
        "instagram_business_account": {"id": "ig-1", "username": "bloom"},
    }]
    assert result["ad_accounts"] == [{"id": "act_42", "name": "Bloom Ads", "account_id": "42"}]
    assert result["catalogs"] == [{"id": "catalog-1", "name": "Bloom Products"}]
    assert "page-token-must-not-leave-server" not in str(result)
    assert "business-token" not in str(result)

    stored = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    token_row = next(row for row in stored if row["key"] == "meta_business_onboarding_token")
    assert token_row["value"] == "business-token"
    assert token_row["is_secret"] is True


@pytest.mark.asyncio
async def test_business_login_complete_rejects_an_ad_account_not_authorized_in_session():
    from app.routes.app_settings import MetaBusinessLoginCompleteRequest, complete_meta_business_login

    db = MagicMock()
    discovered = {
        "pages": [{"id": "page-1", "name": "Bloom Matrix", "access_token": "page-token"}],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads"}],
        "catalogs": [],
    }
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=["business-token", "session-1", "2999-01-01T00:00:00+00:00"]), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)):
        with pytest.raises(Exception) as exc:
            await complete_meta_business_login(
                MetaBusinessLoginCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id="act_other"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "user-1"},
            )

    assert getattr(exc.value, "status_code", None) == 400


class _Response:
    def json(self):
        return {"success": True}


class _MetaClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _Response()


@pytest.mark.asyncio
async def test_business_login_complete_saves_only_the_explicitly_selected_assets():
    from app.routes.app_settings import MetaBusinessLoginCompleteRequest, complete_meta_business_login

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
    discovered = {
        "pages": [{
            "id": "page-2",
            "name": "Chosen Page",
            "access_token": "chosen-page-token",
            "instagram_business_account": {"id": "ig-2"},
        }],
        "ad_accounts": [{"id": "act_2", "name": "Chosen Ads"}],
        "catalogs": [{"id": "catalog-2", "name": "Chosen Catalog"}],
    }
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=["business-token", "session-2", "2999-01-01T00:00:00+00:00"]), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_MetaClient()), \
         patch("app.routes.app_settings.record_audit_event") as audit:
        result = await complete_meta_business_login(
            MetaBusinessLoginCompleteRequest(
                session_id="session-2",
                page_id="page-2",
                ad_account_id="act_2",
                catalog_id="catalog-2",
            ),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result["page_id"] == "page-2"
    assert result["ad_account_id"] == "act_2"
    assert result["catalog_id"] == "catalog-2"
    stored = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    assert {row["key"] for row in stored} >= {
        "facebook_page_id", "facebook_access_token", "instagram_page_id",
        "meta_ads_account_id", "meta_ads_access_token", "meta_catalog_id",
    }
    db.rpc.assert_called_once_with("claim_meta_assets", {
        "p_tenant_id": "tenant-1",
        "p_assets": [
            {"asset_type": "facebook_page", "asset_id": "page-2"},
            {"asset_type": "instagram_account", "asset_id": "ig-2"},
            {"asset_type": "ad_account", "asset_id": "act_2"},
            {"asset_type": "catalog", "asset_id": "catalog-2"},
        ],
    })
    assert "business-token" not in str(audit.call_args)
    assert "chosen-page-token" not in str(audit.call_args)


def test_meta_asset_claim_conflict_is_reported_without_masking_other_failures():
    from app.routes.app_settings import _claim_business_assets

    db = MagicMock()
    db.rpc.return_value.execute.side_effect = RuntimeError("duplicate key SQLSTATE 23505")
    with pytest.raises(HTTPException) as conflict:
        _claim_business_assets(db, "tenant-1", [{"asset_type": "facebook_page", "asset_id": "page-1"}])
    assert conflict.value.status_code == 409

    db.rpc.return_value.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(HTTPException) as unavailable:
        _claim_business_assets(db, "tenant-1", [{"asset_type": "facebook_page", "asset_id": "page-1"}])
    assert unavailable.value.status_code == 503
