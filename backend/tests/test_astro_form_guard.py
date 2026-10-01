"""Saving the Services form must fail for a client connected to AstroTamil when the form cannot
collect what AstroTamil needs. Live miss 2026-09-30: the form had no Gender and the place key was
typed "place_of_birh", and nothing complained until a paid question was refused."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.main import app
from app.services import astro_bridge

PACKAGES = [{"key": "basic", "name": "Basic", "amount_paise": 1000, "description": "", "active": True}]
GOOD_FIELDS = [
    {"key": "name", "label": "Name", "type": "text"},
    {"key": "gender", "label": "Gender", "type": "choice", "options": ["Male", "Female"]},
    {"key": "date_of_birth", "label": "Date of birth", "type": "text"},
    {"key": "place_of_birth", "label": "Place of birth", "type": "text"},
    {"key": "time_of_birth", "label": "Time of birth", "type": "text"},
    {"key": "question", "label": "Question", "type": "text"},
]
# The live form on 2026-09-30: no gender, place key mistyped.
BROKEN_FIELDS = [f for f in GOOD_FIELDS if f["key"] != "gender"]
BROKEN_FIELDS = [{**f, "key": "place_of_birh"} if f["key"] == "place_of_birth" else f for f in BROKEN_FIELDS]
_CONNECTED = {"astro_bridge_url": "https://astro.example.com", "astro_bridge_api_key": "k"}


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "t-1", "role": "owner", "permissions": []}
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def stored():
    with patch("app.routes.app_settings.get_intake_config") as get, \
         patch("app.routes.app_settings.save_intake_config") as save:
        get.return_value = {"enabled": True, "packages": PACKAGES, "fields": GOOD_FIELDS, "amount_paise": 0}
        yield get, save


@pytest.fixture
def connected():
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: _CONNECTED.get(k, fallback)):
        yield


def _patch(client, body):
    return client.patch("/api/v1/settings/intake-config", json=body)


@pytest.mark.usefixtures("connected")
def test_a_form_missing_gender_and_with_a_mistyped_place_key_is_refused_with_the_reason(client, stored):
    _get, save = stored
    res = _patch(client, {"fields": BROKEN_FIELDS})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Gender" in detail and "Place of birth" in detail and "place_of_birh" in detail
    save.assert_not_called()


@pytest.mark.usefixtures("connected")
def test_a_complete_form_is_saved(client, stored):
    _get, save = stored
    assert _patch(client, {"fields": GOOD_FIELDS}).status_code == 200
    save.assert_called_once()


@pytest.mark.usefixtures("connected")
def test_switching_the_feature_on_checks_the_stored_form(client, stored):
    get, save = stored
    get.return_value = {"enabled": False, "packages": PACKAGES, "fields": BROKEN_FIELDS, "amount_paise": 0}
    assert _patch(client, {"enabled": True}).status_code == 400
    save.assert_not_called()


@pytest.mark.usefixtures("connected")
def test_an_unrelated_save_is_not_blocked_by_an_old_broken_form(client, stored):
    get, save = stored
    get.return_value = {"enabled": True, "packages": PACKAGES, "fields": BROKEN_FIELDS, "amount_paise": 0}
    assert _patch(client, {"gst_percent": 18}).status_code == 200
    save.assert_called_once()


@pytest.mark.usefixtures("connected")
def test_a_form_for_a_disabled_feature_is_not_checked(client, stored):
    get, save = stored
    get.return_value = {"enabled": False, "packages": PACKAGES, "fields": [], "amount_paise": 0}
    assert _patch(client, {"fields": BROKEN_FIELDS}).status_code == 200


def test_a_client_without_the_connection_can_save_any_form(client, stored):
    _get, save = stored
    assert _patch(client, {"fields": BROKEN_FIELDS}).status_code == 200
    save.assert_called_once()
