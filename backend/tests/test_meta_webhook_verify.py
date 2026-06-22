# backend/tests/test_meta_webhook_verify.py
import hmac
import hashlib
from unittest.mock import patch
from app.services.meta_webhook_verify import verify_meta_signature

TENANT = "87ade391-3047-4624-8784-10ea8c6a47d1"
BODY = b'{"object":"instagram","entry":[]}'


def _sig(secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), BODY, hashlib.sha256).hexdigest()


def _settings(mapping: dict):
    return lambda key, tenant_id=None, fallback=None: mapping.get(key)


def test_default_uses_meta_app_secret():
    with patch("app.services.meta_webhook_verify.get_setting", _settings({"meta_app_secret": "metasecret"})):
        assert verify_meta_signature(BODY, _sig("metasecret"), TENANT) is True


def test_instagram_secret_verified_against_instagram_app_secret():
    mapping = {"meta_app_secret": "metasecret", "instagram_app_secret": "igsecret"}
    with patch("app.services.meta_webhook_verify.get_setting", _settings(mapping)):
        # Signed with the Instagram secret → valid only via instagram_app_secret
        assert verify_meta_signature(BODY, _sig("igsecret"), TENANT, secret_key="instagram_app_secret") is True
        # The Meta secret must NOT validate an Instagram-Login signature
        assert verify_meta_signature(BODY, _sig("metasecret"), TENANT, secret_key="instagram_app_secret") is False


def test_instagram_falls_back_to_meta_app_secret_when_unset():
    # No instagram_app_secret configured → fall back to the shared meta_app_secret
    with patch("app.services.meta_webhook_verify.get_setting", _settings({"meta_app_secret": "metasecret"})):
        assert verify_meta_signature(BODY, _sig("metasecret"), TENANT, secret_key="instagram_app_secret") is True


def test_no_secret_configured_fails_closed():
    with patch("app.services.meta_webhook_verify.get_setting", _settings({})):
        assert verify_meta_signature(BODY, _sig("anything"), TENANT, secret_key="instagram_app_secret") is False
