"""Deals, Meta Ads, Auto-Messages, Anril Brain and Services each have their own
Roles toggle, so the old shared keys must no longer open them."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_and_role, require_any_permission
from app.routes import app_settings, deals, inbound_leads
from app.services.rbac import ALL_PERMISSION_KEYS, DEFAULT_TELECALLER_PERMISSIONS, normalize_permissions

NEW_KEYS = [
    "deals.view", "deals.manage",
    "meta_ads.view", "meta_ads.manage",
    "auto_messages.view", "auto_messages.manage",
    "brain.view",
    "services.view", "services.manage",
]


def _ctx(perms):
    return {"tenant_id": "t-1", "role": "caller", "permissions": perms}


def _allowed(dep, perms) -> bool:
    try:
        dep(_ctx(perms))
        return True
    except HTTPException as exc:
        assert exc.status_code == 403
        return False


def test_new_keys_are_in_the_catalog_and_survive_normalization():
    for key in NEW_KEYS:
        assert key in ALL_PERMISSION_KEYS
    assert normalize_permissions(NEW_KEYS) == sorted(NEW_KEYS)


def test_default_telecaller_keeps_deals():
    assert "deals.view" in DEFAULT_TELECALLER_PERMISSIONS


@pytest.mark.parametrize(
    "dep, perms, allowed",
    [
        (deals.require_deals_view, ["leads.view"], False),
        (deals.require_deals_view, ["deals.view"], True),
        (deals.require_deals_view, ["deals.manage"], True),
        (deals.require_deals_manage, ["leads.manage"], False),
        (deals.require_deals_manage, ["deals.view"], False),
        (deals.require_deals_manage, ["deals.manage"], True),
        (inbound_leads.require_meta_ads_view, ["inbound_leads.view"], False),
        (inbound_leads.require_meta_ads_view, ["meta_ads.view"], True),
        (inbound_leads.require_meta_ads_manage, ["meta_ads.view"], False),
        (inbound_leads.require_meta_ads_manage, ["meta_ads.manage"], True),
        (app_settings.require_services_read, ["catalog.view"], False),
        (app_settings.require_services_read, ["services.view"], True),
        (app_settings.require_services_read, ["settings.view"], True),
        (app_settings.require_services_manage, ["services.view"], False),
        (app_settings.require_services_manage, ["services.manage"], True),
        (app_settings.require_services_manage, ["settings.manage"], True),
    ],
)
def test_page_gates(dep, perms, allowed):
    assert _allowed(dep, perms) is allowed


def test_owner_passes_any_permission_gate():
    assert require_any_permission("services.manage")({"tenant_id": "t-1", "role": "owner", "permissions": []})


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/v1/inbound-leads/ad-filters"),
        ("get", "/api/v1/inbound-leads/ad-performance"),
        ("get", "/api/v1/inbound-leads/ad-performance/export"),
        ("post", "/api/v1/inbound-leads/ad-tracking-code"),
        ("post", "/api/v1/inbound-leads/ad-sync-now"),
    ],
)
def test_meta_ads_endpoints_reject_inbound_leads_only_users(method, path):
    app = FastAPI()
    app.include_router(inbound_leads.router, prefix="/api/v1/inbound-leads")
    app.dependency_overrides[get_tenant_and_role] = lambda: _ctx(["inbound_leads.view", "inbound_leads.manage"])
    res = getattr(TestClient(app), method)(path, **({"json": {}} if method == "post" else {}))
    assert res.status_code == 403
