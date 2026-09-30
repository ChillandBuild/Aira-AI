"""Per-tenant idle-close window (deal-lifecycle blueprint D1): the reader the idle sweep
uses, and the operator console GET/PATCH for the app_settings key deal_idle_close_days."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies.system_admin import get_system_admin
from app.main import app
from app.services import deal_settings
from app.services.deal_settings import (
    DEAL_IDLE_CLOSE_DAYS_KEY,
    clamp_deal_idle_close_days,
    get_deal_idle_close_days,
)


# ---- clamp_deal_idle_close_days: pure parsing, tolerant of anything ----

@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, 30),
        ("", 30),
        ("   ", 30),
        ("garbage", 30),
        ("nan", 30),
        ("inf", 30),
        ([], 30),
        (True, 30),  # a bool is not a day count
        ("30", 30),
        ("2", 2),
        ("90", 90),
        (" 45 ", 45),
        (7, 7),
        ("12.0", 12),
        ("12.9", 12),
        ("1", 2),
        ("0", 2),
        ("-5", 2),
        ("91", 90),
        ("100000", 90),
        (1, 2),
        (91, 90),
    ],
)
def test_clamp_returns_default_or_clamped_value(raw, expected):
    assert clamp_deal_idle_close_days(raw) == expected


# ---- get_deal_idle_close_days: built on get_setting ----

def test_reader_returns_default_when_setting_missing():
    with patch.object(deal_settings, "get_setting", return_value=None) as gs:
        assert get_deal_idle_close_days("tenant-1") == 30
    gs.assert_called_once_with(DEAL_IDLE_CLOSE_DAYS_KEY, tenant_id="tenant-1")


def test_reader_returns_stored_value():
    with patch.object(deal_settings, "get_setting", return_value="14"):
        assert get_deal_idle_close_days("tenant-1") == 14


def test_reader_clamps_out_of_range_and_tolerates_garbage():
    with patch.object(deal_settings, "get_setting", return_value="365"):
        assert get_deal_idle_close_days("tenant-1") == 90
    with patch.object(deal_settings, "get_setting", return_value="soon"):
        assert get_deal_idle_close_days("tenant-1") == 30


# ---- operator console routes ----

@pytest.fixture()
def client():
    app.dependency_overrides[get_system_admin] = lambda: {"user_id": "admin-1"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def _db_for_get(settings_rows):
    db = MagicMock()

    def table(name):
        tbl = MagicMock()
        if name == "tenants":
            tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "tenant-1", "enabled_features": [],
            }
        elif name == "app_settings":
            tbl.select.return_value.eq.return_value.execute.return_value.data = settings_rows
        elif name == "tenant_usage_counters":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return tbl

    db.table.side_effect = table
    return db


@pytest.mark.parametrize(
    "rows, expected",
    [
        ([], 30),
        ([{"key": DEAL_IDLE_CLOSE_DAYS_KEY, "value": "45"}], 45),
        ([{"key": DEAL_IDLE_CLOSE_DAYS_KEY, "value": "junk"}], 30),
        ([{"key": DEAL_IDLE_CLOSE_DAYS_KEY, "value": "500"}], 90),
    ],
)
def test_get_config_returns_idle_close_days(client, rows, expected):
    with patch("app.routes.operator.get_supabase", return_value=_db_for_get(rows)):
        res = client.get("/api/v1/operator/clients/tenant-1/config")
    assert res.status_code == 200
    assert res.json()["settings"][DEAL_IDLE_CLOSE_DAYS_KEY] == expected


def _patch(client, value):
    """PATCH the setting with a fresh mocked db; returns (response, app_settings table mock)."""
    db = MagicMock()
    app_settings = MagicMock()

    def table(name):
        if name == "app_settings":
            return app_settings
        tbl = MagicMock()
        if name == "tenants":
            tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "tenant-1"}
        return tbl

    db.table.side_effect = table
    with patch("app.routes.operator.get_supabase", return_value=db), \
         patch("app.routes.operator.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        res = client.patch(
            "/api/v1/operator/clients/tenant-1/config",
            json={"settings": {DEAL_IDLE_CLOSE_DAYS_KEY: value}},
        )
    return res, app_settings


@pytest.mark.parametrize("value", ["2", "90", "30"])
def test_patch_accepts_values_in_range_and_stores_them(client, value):
    res, app_settings = _patch(client, value)
    assert res.status_code == 200
    stored = app_settings.upsert.call_args.args[0]
    assert stored["key"] == DEAL_IDLE_CLOSE_DAYS_KEY
    assert stored["value"] == value


@pytest.mark.parametrize("value", ["1", "91", "0", "-3", "abc", "", "7.5", "true"])
def test_patch_rejects_out_of_range_or_non_integer(client, value):
    res, app_settings = _patch(client, value)
    assert res.status_code == 400
    assert "2" in res.json()["detail"] and "90" in res.json()["detail"]
    app_settings.upsert.assert_not_called()


def test_patch_rejects_boolean_value(client):
    res, app_settings = _patch(client, True)
    assert res.status_code == 400
    app_settings.upsert.assert_not_called()


def test_patch_bad_idle_value_blocks_sibling_settings_in_same_request(client):
    """All-or-nothing: an invalid value must not let the other keys in the batch through."""
    db = MagicMock()
    app_settings = MagicMock()
    db.table.side_effect = lambda name: app_settings if name == "app_settings" else MagicMock()
    with patch("app.routes.operator.get_supabase", return_value=db), \
         patch("app.routes.operator.record_audit_event"):
        res = client.patch(
            "/api/v1/operator/clients/tenant-1/config",
            json={"settings": {"kb_retrieval_mode": "keyword", DEAL_IDLE_CLOSE_DAYS_KEY: "91"}},
        )
    assert res.status_code == 400
    app_settings.upsert.assert_not_called()
