"""The generic settings PATCH no longer writes handover_line (blueprint 9B): the handover
wording is the 8th Description section, owner-only. Saving the Description still re-checks
consistency; saving anything else does not."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.routes import app_settings


@pytest.fixture
def env(monkeypatch):
    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"ok": True}]
    monkeypatch.setattr(app_settings, "get_supabase", lambda: db)
    monkeypatch.setattr(app_settings, "record_audit_event", lambda *a, **k: None)
    rechecks: list[str] = []

    async def fake_check(tenant_id):
        rechecks.append(tenant_id)

    monkeypatch.setattr("app.services.consistency.run_check_safely", fake_check)
    app = FastAPI()
    app.include_router(app_settings.router, prefix="/api/v1/settings")
    app.dependency_overrides[app_settings.require_settings_manage] = lambda: {"tenant_id": "t1"}
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
    return SimpleNamespace(client=TestClient(app), db=db, rechecks=rechecks)


def test_patching_handover_line_is_rejected_with_a_pointer_to_the_description(env):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"handover_line": "Call us."}})
    assert res.status_code == 400
    assert "Description" in res.json()["detail"]
    env.db.table.assert_not_called()  # nothing written


def test_clearing_handover_line_through_the_generic_route_is_rejected_too(env):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"handover_line": ""}})
    assert res.status_code == 400
    env.db.table.assert_not_called()


def test_a_mixed_request_is_rejected_whole(env):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"handover_line": "x", "business_name": "Shop"}})
    assert res.status_code == 400
    env.db.table.assert_not_called()


def test_other_settings_still_save_and_do_not_trigger_a_recheck(env):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_name": "Shop"}})
    assert res.status_code == 200 and res.json() == {"updated": ["business_name"]}
    assert env.rechecks == []


def test_saving_the_description_still_rechecks_consistency(env):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": "ABOUT US\nA shop."}})
    assert res.status_code == 200
    assert env.rechecks == ["t1"]
