"""A manual Meta channel save must fill in the shared app-level credentials.

`meta_app_secret` and `meta_webhook_verify_token` are Aira's own values, identical
for every tenant, and only the WhatsApp form asks for them. Embedded Signup copied
them in; the manual save path never did — so an Instagram- or Facebook-only tenant
had neither, and `verify_meta_signature` rejected every inbound message with
"not configured for tenant … — rejecting webhook".
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _update_settings_body() -> str:
    source = _read("app/routes/app_settings.py")
    start = source.index("async def update_settings")
    return source[start:source.index("@router.", start)]


def _shared_credentials_helper() -> str:
    source = _read("app/routes/app_settings.py")
    start = source.index("def _save_shared_meta_app_credentials")
    return source[start:source.index("def _public_business_login_assets", start)]


def test_manual_save_fills_the_shared_credentials():
    body = _update_settings_body()
    assert "_save_shared_meta_app_credentials(db, tenant_id, only_if_missing=True)" in body


def test_only_meta_channels_trigger_it():
    """meta_ads uses a system-user token and has no webhook signature to verify."""
    body = _update_settings_body()
    assert 'if channel in ("whatsapp", "instagram", "facebook")' in body
    assert "touched_meta_channel" in body


def test_it_runs_after_the_operators_own_values_are_stored():
    """Otherwise only_if_missing would see an empty row and overwrite the typed value."""
    body = _update_settings_body()
    assert body.index("for key, value in payload.updates.items()") < body.index(
        "_save_shared_meta_app_credentials"
    )


def test_only_if_missing_skips_an_existing_value():
    helper = _shared_credentials_helper()
    assert "only_if_missing and _get_setting_value(db, tenant_id, key)" in helper
    assert "continue" in helper


def test_default_still_overwrites_for_embedded_signup():
    """Signup flows call it without the flag; env stays the source of truth there."""
    helper = _shared_credentials_helper()
    assert "only_if_missing: bool = False" in helper
    source = _read("app/routes/app_settings.py")
    # The four embedded-signup call sites must not have picked up the flag.
    assert source.count("_save_shared_meta_app_credentials(db, tenant_id)") == 4


def test_verify_token_falls_back_when_env_is_unset():
    """META_VERIFY_TOKEN is not set on this deployment; the tenants' copy is."""
    helper = _shared_credentials_helper()
    assert "env_settings.meta_verify_token or resolve_verify_token()" in helper
