"""GET /api/v1/intake/partner/config — what the Developer page shows a partner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.intake import require_settings_view, router

app = FastAPI()
app.include_router(router, prefix="/api/v1/intake")
app.dependency_overrides[require_settings_view] = lambda: {"tenant_id": "t-1"}
client = TestClient(app)


def _settings(values):
    def fake(key, tenant_id=None, **_kw):
        assert tenant_id == "t-1", "must be read for the caller's tenant"
        return values.get(key)
    return fake


def test_config_reports_tenant_paths_and_which_credentials_are_on_file():
    with patch("app.config_dynamic.get_setting", side_effect=_settings({
        "astro_bridge_secret": "s3cret", "astro_bridge_url": "https://partner.example",
    })):
        res = client.get("/api/v1/intake/partner/config")
    assert res.status_code == 200
    body = res.json()
    assert body["tenant_id"] == "t-1"
    assert body["secret_set"] is True
    assert body["bridge_url_set"] is True
    assert body["api_key_set"] is False
    assert body["signature_header"] == "X-Aira-Signature"
    assert body["legacy_signature_header"] == "X-Astro-Signature"
    assert body["paths"] == {
        "send_template": "/api/v1/intake/partner/send-template",
        "send_text": "/api/v1/intake/partner/send-text",
        "reply_callback": "/api/v1/intake/astro-reply",
        "legacy_prefix": "/api/v1/expert-handoff",
    }


def test_config_never_returns_the_secret_value():
    with patch("app.config_dynamic.get_setting", side_effect=_settings({"astro_bridge_secret": "s3cret"})):
        res = client.get("/api/v1/intake/partner/config")
    assert "s3cret" not in res.text
