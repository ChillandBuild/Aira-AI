from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


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
