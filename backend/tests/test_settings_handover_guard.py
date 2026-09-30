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
    ctx = {"tenant_id": "t1", "role": "owner"}
    app.dependency_overrides[app_settings.require_settings_manage] = lambda: ctx
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
    return SimpleNamespace(client=TestClient(app), db=db, rechecks=rechecks, ctx=ctx)


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


@pytest.fixture
def description_writes(monkeypatch):
    """Records the versioned Description saves and rubric follow-ups of the owner path."""
    saves: list[tuple] = []
    rubrics: list[tuple] = []
    monkeypatch.setattr(
        "app.services.knowledge_versions.save_description",
        lambda db, tenant_id, text, reason, user_id: saves.append((tenant_id, text, reason, user_id)),
    )
    monkeypatch.setattr(
        "app.routes.ai_tune.queue_rubric_for_description",
        lambda tenant_id, text, **kw: rubrics.append((tenant_id, text)) or True,
    )
    return SimpleNamespace(saves=saves, rubrics=rubrics)


def test_saving_the_description_still_rechecks_consistency(env, description_writes):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": "ABOUT US\nA shop."}})
    assert res.status_code == 200
    assert env.rechecks == ["t1"]


def test_a_non_owner_cannot_write_the_description_through_the_generic_route(env, description_writes):
    env.ctx["role"] = "manager"
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": "ABOUT US\nA shop."}})
    assert res.status_code == 403
    assert res.json()["detail"] == "Only the owner can edit the Description"
    env.db.table.assert_not_called()
    assert description_writes.saves == [] and env.rechecks == []


def test_a_mixed_request_with_the_description_is_rejected_whole_for_a_non_owner(env, description_writes):
    env.ctx["role"] = "manager"
    res = env.client.patch(
        "/api/v1/settings/",
        json={"updates": {"business_name": "Shop", "business_description": "ABOUT US\nA shop."}},
    )
    assert res.status_code == 403
    env.db.table.assert_not_called()


def test_the_owner_description_write_is_versioned_and_queues_the_rubric(env, description_writes):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": " ABOUT US\nA shop. "}})
    assert res.status_code == 200 and res.json() == {"updated": ["business_description"]}
    assert description_writes.saves == [("t1", "ABOUT US\nA shop.", "edit", "u1")]
    assert description_writes.rubrics == [("t1", "ABOUT US\nA shop.")]
    env.db.table.return_value.upsert.assert_not_called()  # never a raw setting write


def test_the_owner_description_over_the_word_cap_is_rejected_and_not_saved(env, description_writes):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": "word " * 701}})
    assert res.status_code == 422
    assert description_writes.saves == [] and env.rechecks == []


def test_the_owner_can_clear_the_description_through_the_versioned_path(env, description_writes):
    res = env.client.patch("/api/v1/settings/", json={"updates": {"business_description": ""}})
    assert res.status_code == 200
    assert description_writes.saves == [("t1", "", "edit", "u1")]
