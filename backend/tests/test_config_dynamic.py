import pytest
from unittest.mock import patch

from app.config_dynamic import require_tenant_setting


def test_require_tenant_setting_returns_value_when_configured():
    with patch("app.config_dynamic.get_setting", return_value="the-key"):
        assert require_tenant_setting("gemini_api_key", "tenant-1") == "the-key"


def test_require_tenant_setting_raises_when_not_configured():
    with patch("app.config_dynamic.get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="gemini_api_key not configured for this client"):
            require_tenant_setting("gemini_api_key", "tenant-1")


def test_require_tenant_setting_raises_when_no_tenant_id():
    with patch("app.config_dynamic.get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="openai_api_key not configured for this client"):
            require_tenant_setting("openai_api_key", None)
