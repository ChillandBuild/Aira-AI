"""Ads-only Embedded Signup: a tenant with no Facebook Page can still connect Meta Ads.

The Page-based `/facebook/business-login/*` pair rejects a Page-less signup, so the
ads-only Login configuration needs its own endpoints. These tests pin the two things
that make it safe: the signup token never reaches the browser, and completing it
touches no other channel's credentials.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_ads_signup_start_returns_only_ad_accounts_and_stages_the_token():
    """Breaks if the one-time code leaks a token or stages under the WhatsApp keys."""
    from app.routes.app_settings import MetaAdsSignupStartRequest, start_meta_ads_signup

    db = MagicMock()
    discovered = {
        "pages": [],
        "ad_accounts": [{"id": "act_42", "name": "Astro Tamil Test", "account_id": "42", "currency": "INR"}],
        "catalogs": [],
    }

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "ads-system-user-token"})), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.get_supabase", return_value=db):
        result = await start_meta_ads_signup(
            MetaAdsSignupStartRequest(code="single-use-code"),
            ctx={"tenant_id": "tenant-1"},
        )

    assert result["ad_accounts"] == [
        {"id": "act_42", "name": "Astro Tamil Test", "account_id": "42", "currency": "INR"}
    ]
    assert "pages" not in result
    assert "ads-system-user-token" not in str(result)

    stored = {row["key"]: row for row in (call.args[0] for call in db.table.return_value.upsert.call_args_list) if "key" in row}
    assert set(stored) == {
        "meta_ads_onboarding_token",
        "meta_ads_onboarding_session_id",
        "meta_ads_onboarding_expires_at",
    }
    assert stored["meta_ads_onboarding_token"]["value"] == "ads-system-user-token"
    assert stored["meta_ads_onboarding_token"]["is_secret"] is True


@pytest.mark.asyncio
async def test_ads_signup_start_rejects_a_signup_that_granted_no_ad_account():
    """Breaks if a tenant can stage a session that can never be completed."""
    from app.routes.app_settings import MetaAdsSignupStartRequest, start_meta_ads_signup

    db = MagicMock()
    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token"})), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value={"pages": [], "ad_accounts": [], "catalogs": []})), \
         patch("app.routes.app_settings.get_supabase", return_value=db):
        with pytest.raises(HTTPException) as exc:
            await start_meta_ads_signup(
                MetaAdsSignupStartRequest(code="single-use-code"),
                ctx={"tenant_id": "tenant-1"},
            )

    assert exc.value.status_code == 400
    db.table.return_value.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_ads_signup_completion_connects_only_meta_ads():
    """Breaks if an ads-only signup writes WhatsApp, Page or Instagram credentials."""
    from app.routes.app_settings import MetaAdsSignupCompleteRequest, complete_meta_ads_signup

    db = MagicMock()
    discovered = {
        "pages": [],
        "ad_accounts": [{"id": "act_42", "name": "Astro Tamil Test"}],
        "catalogs": [],
    }
    staged = ["ads-system-user-token", "session-1", "2999-01-01T00:00:00+00:00"]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.record_audit_event"):
        result = await complete_meta_ads_signup(
            MetaAdsSignupCompleteRequest(session_id="session-1", ad_account_id="act_42"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result == {"success": True, "ad_account_id": "act_42", "ad_account_name": "Astro Tamil Test"}

    stored = {row["key"]: row for row in (call.args[0] for call in db.table.return_value.upsert.call_args_list) if "key" in row}
    assert set(stored) == {
        "meta_ads_access_token",
        "meta_ads_account_id",
        "meta_ads_account_name",
        "meta_ads_status",
        "meta_ads_connection_source",
    }
    assert stored["meta_ads_access_token"]["value"] == "ads-system-user-token"
    assert stored["meta_ads_access_token"]["is_secret"] is True
    assert stored["meta_ads_account_id"]["value"] == "act_42"
    assert stored["meta_ads_connection_source"]["value"] == "embedded"

    db.rpc.assert_called_once_with("claim_meta_assets", {
        "p_tenant_id": "tenant-1",
        "p_assets": [{"asset_type": "ad_account", "asset_id": "act_42"}],
    })


@pytest.mark.asyncio
async def test_ads_signup_completion_rejects_an_account_the_signup_never_granted():
    """Breaks if a browser-supplied id can claim an ad account Meta did not hand over."""
    from app.routes.app_settings import MetaAdsSignupCompleteRequest, complete_meta_ads_signup

    db = MagicMock()
    discovered = {"pages": [], "ad_accounts": [{"id": "act_42", "name": "Astro Tamil Test"}], "catalogs": []}
    staged = ["ads-system-user-token", "session-1", "2999-01-01T00:00:00+00:00"]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.routes.app_settings.record_audit_event"):
        with pytest.raises(HTTPException) as exc:
            await complete_meta_ads_signup(
                MetaAdsSignupCompleteRequest(session_id="session-1", ad_account_id="act_someone_else"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "user-1"},
            )

    assert exc.value.status_code == 400
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_ads_signup_completion_rejects_an_expired_session():
    """Breaks if a stale staged token can still be spent."""
    from app.routes.app_settings import MetaAdsSignupCompleteRequest, complete_meta_ads_signup

    db = MagicMock()
    staged = ["ads-system-user-token", "session-1", "2000-01-01T00:00:00+00:00"]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged):
        with pytest.raises(HTTPException) as exc:
            await complete_meta_ads_signup(
                MetaAdsSignupCompleteRequest(session_id="session-1", ad_account_id="act_42"),
                ctx={"tenant_id": "tenant-1"},
                user={"user_id": "user-1"},
            )

    assert exc.value.status_code == 400
    db.rpc.assert_not_called()
