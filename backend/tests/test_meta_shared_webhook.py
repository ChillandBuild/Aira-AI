"""Guards for the shared (tenant-agnostic) Meta webhook endpoints and the
app-identity check that makes a wrong-app misconfiguration fail loudly.

Background: Meta allows one callback URL per app per webhook object, so a URL with
`tenant_id` in its path can only ever serve one tenant. These cover the resolver
that replaces it, plus the diagnostics added alongside.
"""
import hashlib
import hmac
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import meta_webhook_verify as mwv  # noqa: E402


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ── secret_fingerprint ──────────────────────────────────────────────────────

def test_fingerprint_is_short_stable_and_hides_the_secret():
    secret = "cacb33d2eaa21f30a269611a09d908cc"
    fp = mwv.secret_fingerprint(secret)
    assert len(fp) == 8
    assert fp == mwv.secret_fingerprint(secret)
    assert secret not in fp
    assert fp != mwv.secret_fingerprint("e7da5a948bd77e470eec9bd9d5ab0e36")


# ── resolve_tenants_from_payload ────────────────────────────────────────────

def test_resolves_distinct_tenants_in_order(monkeypatch):
    owners = {"17841000000000001": "tenant-a", "17841000000000002": "tenant-b"}
    monkeypatch.setattr(mwv, "resolve_tenant_for_page", lambda pid, ch: owners.get(pid))

    payload = {"entry": [
        {"id": "17841000000000001"},
        {"id": "17841000000000002"},
        {"id": "17841000000000001"},  # duplicate — must collapse
    ]}
    assert mwv.resolve_tenants_from_payload(payload, "instagram") == ["tenant-a", "tenant-b"]


def test_unknown_and_empty_entries_resolve_to_nothing(monkeypatch):
    monkeypatch.setattr(mwv, "resolve_tenant_for_page", lambda pid, ch: None)
    assert mwv.resolve_tenants_from_payload({"entry": [{"id": "999"}]}, "instagram") == []
    assert mwv.resolve_tenants_from_payload({}, "facebook") == []
    assert mwv.resolve_tenants_from_payload({"entry": None}, "facebook") == []


# ── verify_meta_signature ───────────────────────────────────────────────────

SECRET = "0123456789abcdef0123456789abcdef"
BODY = b'{"object":"instagram","entry":[]}'


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes(monkeypatch):
    monkeypatch.setattr(mwv, "get_setting", lambda key, tenant_id=None: SECRET)
    assert mwv.verify_meta_signature(BODY, _sign(SECRET, BODY), "t1") is True


def test_signature_from_another_app_is_rejected_and_names_the_secret(monkeypatch, caplog):
    monkeypatch.setattr(mwv, "get_setting", lambda key, tenant_id=None: SECRET)
    other_app_signature = _sign("ffffffffffffffffffffffffffffffff", BODY)

    with caplog.at_level(logging.WARNING):
        assert mwv.verify_meta_signature(BODY, other_app_signature, "t1") is False

    # The whole point of the change: the rejection must be diagnosable without
    # reading the source, and must never leak the secret itself.
    log = caplog.text
    assert mwv.secret_fingerprint(SECRET) in log
    assert "different Meta app" in log
    assert SECRET not in log


def test_missing_signature_header_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(mwv, "get_setting", lambda key, tenant_id=None: SECRET)
    with caplog.at_level(logging.WARNING):
        assert mwv.verify_meta_signature(BODY, None, "t1") is False
    assert "X-Hub-Signature-256" in caplog.text


def test_unconfigured_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(mwv, "get_setting", lambda key, tenant_id=None: None)
    assert mwv.verify_meta_signature(BODY, _sign(SECRET, BODY), "t1") is False


# ── shared routes are registered ────────────────────────────────────────────

def test_both_channels_expose_a_tenantless_endpoint():
    for path in ("app/routes/instagram.py", "app/routes/facebook.py"):
        source = _read(path)
        assert '@router.get("")' in source, f"{path} has no shared GET route"
        assert '@router.post("")' in source, f"{path} has no shared POST route"
        # The per-tenant routes must survive — they are already configured in Meta.
        assert '@router.get("/{tenant_id}")' in source
        assert '@router.post("/{tenant_id}")' in source


def test_shared_endpoints_route_by_payload_not_by_url():
    for path, channel in (
        ("app/routes/instagram.py", "instagram"),
        ("app/routes/facebook.py", "facebook"),
    ):
        source = _read(path)
        assert f'resolve_tenants_from_payload(payload, "{channel}")' in source
        assert "matches_any_tenant_verify_token(token)" in source


# ── activation refuses a token from the wrong Meta app ──────────────────────

def test_activate_channel_checks_the_tokens_app_id():
    source = _read("app/routes/app_settings.py")
    body = source[source.index("async def activate_channel"):]
    body = body[:body.index("@router.post")]

    # WhatsApp has its own subscribed_apps call earlier in the same function, so
    # scope to the branch this guard belongs to.
    branch = body[body.index("# instagram or facebook"):]

    assert "_resolve_token_app_id(token)" in branch
    assert "token_app_id != env_settings.meta_app_id" in branch
    # Must abort before subscribing or writing status, not warn and continue.
    assert branch.index("token_app_id != env_settings.meta_app_id") < branch.index("subscribed_apps")
    assert branch.index("token_app_id != env_settings.meta_app_id") < branch.index('f"{channel}_status"')


def test_app_id_check_is_a_guard_not_a_gate():
    source = _read("app/routes/app_settings.py")
    helper = source[source.index("async def _resolve_token_app_id"):]
    helper = helper[:helper.index('@router.post("/activate")')]
    # An inconclusive debug_token answer returns None, and the caller's `if
    # token_app_id and ...` then skips the check rather than blocking activation.
    assert "return None" in helper
    assert "debug_token" in helper
