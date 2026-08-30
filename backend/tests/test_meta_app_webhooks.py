"""Guards for automatic app-level webhook registration.

The callback URL and verify token are app-level, so nothing in the per-client signup
flow ever configured them and they were pasted into the Meta console by hand. These
cover the call that replaces that step.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import meta_app_webhooks as maw  # noqa: E402


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ── channel -> object mapping ───────────────────────────────────────────────

def test_every_channel_registers_the_shared_tenantless_url():
    for channel, (_obj, path, _fields) in maw.WEBHOOK_OBJECTS.items():
        assert "{tenant_id}" not in path, f"{channel} would register a single-tenant URL"
        assert path.startswith("/webhook/")


def test_objects_use_metas_names_not_our_channel_names():
    assert maw.WEBHOOK_OBJECTS["facebook"][0] == "page"
    assert maw.WEBHOOK_OBJECTS["instagram"][0] == "instagram"
    assert maw.WEBHOOK_OBJECTS["whatsapp"][0] == "whatsapp_business_account"


def test_instagram_omits_messenger_only_fields():
    _obj, _path, fields = maw.WEBHOOK_OBJECTS["instagram"]
    assert "message_deliveries" not in fields
    assert "message_reads" not in fields
    assert "messages" in fields


# ── verify token resolution ─────────────────────────────────────────────────

def test_env_verify_token_wins(monkeypatch):
    monkeypatch.setattr(maw.env_settings, "meta_verify_token", "from-env", raising=False)
    assert maw.resolve_verify_token() == "from-env"


def test_falls_back_to_a_stored_tenant_token(monkeypatch):
    """This deployment has no META_VERIFY_TOKEN, but every tenant holds a copy."""
    monkeypatch.setattr(maw.env_settings, "meta_verify_token", None, raising=False)

    class _Result:
        data = [{"value": "aira_super_secret_token_2"}]

    class _Query:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def neq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return _Result()

    class _DB:
        def table(self, *a, **k): return _Query()

    monkeypatch.setattr("app.db.supabase.get_supabase", lambda: _DB())
    assert maw.resolve_verify_token() == "aira_super_secret_token_2"


# ── the registration call ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_channel_is_rejected():
    result = await maw.ensure_app_webhook_subscription("myspace")
    assert result["ok"] is False
    assert "unknown channel" in result["detail"]


@pytest.mark.asyncio
async def test_missing_app_credentials_do_not_raise(monkeypatch):
    monkeypatch.setattr(maw.env_settings, "meta_app_id", None, raising=False)
    monkeypatch.setattr(maw.env_settings, "meta_app_secret", None, raising=False)
    result = await maw.ensure_app_webhook_subscription("instagram")
    assert result["ok"] is False
    assert "META_APP_ID" in result["detail"]


@pytest.mark.asyncio
async def test_missing_verify_token_does_not_raise(monkeypatch):
    monkeypatch.setattr(maw.env_settings, "meta_app_id", "2225044871604460", raising=False)
    monkeypatch.setattr(maw.env_settings, "meta_app_secret", "secret", raising=False)
    monkeypatch.setattr(maw, "resolve_verify_token", lambda: None)
    result = await maw.ensure_app_webhook_subscription("instagram")
    assert result["ok"] is False
    assert "verify token" in result["detail"]


# ── wiring ──────────────────────────────────────────────────────────────────

def test_activation_registers_the_webhook_for_both_branches():
    source = _read("app/routes/app_settings.py")
    body = source[source.index("async def activate_channel"):]
    body = body[:body.index('@router.post("/channels')] if '@router.post("/channels' in body else body

    # WhatsApp branch and the instagram/facebook branch each re-assert it.
    assert body.count("ensure_app_webhook_subscription(") >= 2
    assert 'ensure_app_webhook_subscription("whatsapp")' in body
    assert "ensure_app_webhook_subscription(channel)" in body


def test_a_manual_sync_endpoint_exists():
    source = _read("app/routes/app_settings.py")
    assert '@router.post("/webhook-subscriptions/sync")' in source
    assert "sync_all_app_webhook_subscriptions" in source


def test_registration_never_fails_an_activation():
    """A Meta-side problem must not roll back a channel that is otherwise live."""
    source = _read("app/services/meta_app_webhooks.py")
    fn = source[source.index("async def ensure_app_webhook_subscription"):]
    # Every failure path returns a dict; none raise.
    assert "raise" not in fn
    assert fn.count("return {") >= 4
