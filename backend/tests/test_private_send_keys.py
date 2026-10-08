"""Client-owned Private Send key management: create / revoke a license key, set reply mode.

Reuses the stateful FakeDB from test_private_send.py so the real service code runs.
The permission check is the REAL require_permission("settings.manage"); only
get_tenant_and_role is overridden, so non-admin 403s are genuine."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_and_role
from app.routes import private_send as ps_routes
from app.routes import private_send_keys as keys_routes
from app.services import private_send as ps
from test_private_send import FakeDB, OTHER_TENANT, PUBLIC_BASE, TENANT, _add_key, _auth

BASE = "/api/v1/private-send"
ADMIN_CTX = {"tenant_id": TENANT, "role": "admin", "user_id": "u-admin", "permissions": ["settings.manage"]}
VIEWER_CTX = {"tenant_id": TENANT, "role": "member", "user_id": "u-viewer", "permissions": ["settings.view"]}


@pytest.fixture
def env(monkeypatch):
    db, settings = FakeDB(), {}
    db.rows("tenants").append({"id": TENANT, "enabled_features": ["private_send"]})
    db.rows("tenants").append({"id": OTHER_TENANT, "enabled_features": []})

    def get_setting(key, fallback=None, tenant_id=None):
        saved = [r["value"] for r in db.rows("app_settings") if (r["tenant_id"], r["key"]) == (tenant_id, key)]
        return (saved[-1] if saved else None) or settings.get((tenant_id, key)) or fallback

    monkeypatch.setattr(ps, "get_setting", get_setting)
    for mod in (keys_routes, ps_routes):
        monkeypatch.setattr(mod, "get_supabase", lambda: db)
    monkeypatch.setattr(keys_routes, "_key_limiter", keys_routes._SlidingWindow(5, 60))
    monkeypatch.setattr(keys_routes, "_settings_limiter", keys_routes._SlidingWindow(10, 60))
    monkeypatch.setattr(ps_routes, "_bundle_limiter", ps_routes._SlidingWindow(60, 60))
    monkeypatch.setattr(ps_routes, "_usage_limiter", ps_routes._SlidingWindow(30, 60))
    monkeypatch.setattr(ps_routes, "_ip_limiter", ps_routes._SlidingWindow(120, 60))
    ps.reset_unknown_key_cache()
    audit = []
    monkeypatch.setattr(keys_routes, "record_audit_event", lambda _db, **kw: audit.append(kw))

    ctx = {"value": ADMIN_CTX}
    app = FastAPI()
    app.include_router(keys_routes.router, prefix=BASE)
    app.include_router(ps_routes.public_router, prefix=PUBLIC_BASE)
    app.dependency_overrides[get_tenant_and_role] = lambda: ctx["value"]
    return SimpleNamespace(db=db, audit=audit, ctx=ctx, client=TestClient(app))


def _active_keys(env, tenant=TENANT):
    return [k for k in env.db.rows("private_send_keys") if k["tenant_id"] == tenant and k["status"] == "active"]


# ------------------------------------------------------------------ create

def test_create_returns_full_key_once_with_prefix_and_created_at(env):
    res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"key", "key_prefix", "created_at"}
    assert body["key"].startswith("aps_live_") and body["key_prefix"] == body["key"][:13]
    assert res.headers["cache-control"] == "no-store"
    stored = env.db.rows("private_send_keys")[0]
    assert stored["tenant_id"] == TENANT and stored["key_hash"] == ps.hash_key(body["key"])
    assert body["key"] not in str(stored)  # only the hash is stored


def test_key_is_never_shown_again_after_create(env):
    full = env.client.post(f"{BASE}/keys").json()["key"]
    # every read path available to the client: status, audit trail, stored rows, error bodies
    assert full not in str(env.audit)
    assert full not in str(env.db.rows("private_send_keys"))
    assert full not in env.client.post(f"{BASE}/keys").text  # the 409 body


def test_create_returns_409_key_exists_when_active_key_present(env):
    _add_key(env)
    res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 409 and res.json()["code"] == "key_exists"
    assert len(_active_keys(env)) == 1


def test_create_allowed_after_revoking_old_key(env):
    _add_key(env, status="revoked")
    assert env.client.post(f"{BASE}/keys").status_code == 200


def test_create_race_loser_is_revoked_and_gets_409(env):
    """Two creates both passed the 'no key yet' check: only the oldest key may survive."""
    older = _add_key(env)
    env.db.rows("private_send_keys")[0]["created_at"] = "2020-01-01T00:00:00Z"
    with patch.object(keys_routes, "_active_key_count", return_value=0):
        res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 409 and res.json()["code"] == "key_exists"
    assert [k["key_prefix"] for k in _active_keys(env)] == [older[:13]]


def test_create_failing_after_the_key_exists_revokes_it_and_says_it_was_not_saved(env):
    """The full key only ever leaves in the 200 body, so a key nobody saw must not stay active."""
    with patch.object(keys_routes, "_created_at", side_effect=RuntimeError("db hiccup")):
        res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 500 and res.json()["code"] == "key_not_saved"
    assert res.json()["error"] == "The key wasn't saved. Try again."
    assert "key" not in res.json()
    assert _active_keys(env) == []
    assert [k["status"] for k in env.db.rows("private_send_keys")] == ["revoked"]
    assert env.audit == []
    assert env.client.post(f"{BASE}/keys").status_code == 200  # a retry is not blocked by a ghost key


def test_create_failing_while_settling_the_race_also_revokes_the_new_key(env):
    real = keys_routes._active_keys
    calls = {"n": 0}

    def flaky(db, tenant_id):
        calls["n"] += 1
        if calls["n"] == 2:  # the post-create read
            raise RuntimeError("db hiccup")
        return real(db, tenant_id)

    with patch.object(keys_routes, "_active_keys", side_effect=flaky):
        res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 500 and res.json()["error"] == "The key wasn't saved. Try again."
    assert _active_keys(env) == []


def test_create_failing_before_a_key_exists_revokes_nothing(env):
    _add_key(env, status="revoked")
    with patch.object(ps, "create_key", side_effect=RuntimeError("db down")):
        res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 500 and res.json()["code"] == "key_not_saved"
    assert [k["status"] for k in env.db.rows("private_send_keys")] == ["revoked"]


def test_create_403_when_feature_not_enabled_for_tenant(env):
    env.ctx["value"] = {**ADMIN_CTX, "tenant_id": OTHER_TENANT}
    res = env.client.post(f"{BASE}/keys")
    assert res.status_code == 403 and res.json()["code"] == "feature_disabled"
    assert env.db.rows("private_send_keys") == []


def test_create_writes_audit_without_key(env):
    full = env.client.post(f"{BASE}/keys").json()["key"]
    assert [a["action"] for a in env.audit] == ["tenant.private_send_key_created"]
    assert env.audit[0]["tenant_id"] == TENANT and full not in str(env.audit)


# ------------------------------------------------------------------ permissions

@pytest.mark.parametrize("method,path,body", [
    ("post", "/keys", None),
    ("delete", "/keys/current", None),
    ("patch", "/settings", {"reply_mode": "aira"}),
])
def test_non_admin_gets_403_and_nothing_changes(env, method, path, body):
    _add_key(env)
    env.ctx["value"] = VIEWER_CTX
    res = getattr(env.client, method)(f"{BASE}{path}", **({"json": body} if body else {}))
    assert res.status_code == 403
    assert len(_active_keys(env)) == 1 and env.db.rows("app_settings") == []


# ------------------------------------------------------------------ tenant isolation

def test_create_ignores_tenant_id_in_query_and_stores_own_tenant(env):
    env.client.post(f"{BASE}/keys?tenant_id={OTHER_TENANT}")
    rows = env.db.rows("private_send_keys")
    assert [r["tenant_id"] for r in rows] == [TENANT]


def test_revoke_never_touches_another_tenants_key(env):
    mine, theirs = _add_key(env), _add_key(env, tenant=OTHER_TENANT)
    res = env.client.delete(f"{BASE}/keys/current")
    assert res.status_code == 200
    assert _active_keys(env) == [] and len(_active_keys(env, OTHER_TENANT)) == 1
    assert ps.find_key(env.db, theirs)["tenant_id"] == OTHER_TENANT
    with pytest.raises(ps.PrivateSendError):
        ps.find_key(env.db, mine)


def test_revoke_404_when_only_other_tenant_has_key(env):
    _add_key(env, tenant=OTHER_TENANT)
    res = env.client.delete(f"{BASE}/keys/current")
    assert res.status_code == 404 and res.json()["code"] == "no_active_key"
    assert len(_active_keys(env, OTHER_TENANT)) == 1


def test_settings_rejects_tenant_id_in_body_and_writes_nothing(env):
    res = env.client.patch(f"{BASE}/settings", json={"reply_mode": "aira", "tenant_id": OTHER_TENANT})
    assert res.status_code == 422
    assert env.db.rows("app_settings") == []


# ------------------------------------------------------------------ revoke

def test_revoked_key_is_rejected_by_bundle_and_usage_immediately(env):
    full = env.client.post(f"{BASE}/keys").json()["key"]
    assert ps.find_key(env.db, full)["tenant_id"] == TENANT
    res = env.client.delete(f"{BASE}/keys/current")
    assert res.status_code == 200 and res.json() == {"ok": True, "revoked": 1}
    row = env.db.rows("private_send_keys")[0]
    assert row["status"] == "revoked" and row["revoked_at"]
    for call in (
        env.client.get(f"{PUBLIC_BASE}/bundle", headers=_auth(full)),
        env.client.post(f"{PUBLIC_BASE}/usage", json={"rows": []}, headers=_auth(full)),
    ):
        assert call.status_code in (401, 422)
    bundle = env.client.get(f"{PUBLIC_BASE}/bundle", headers=_auth(full))
    assert bundle.status_code == 401 and bundle.json()["code"] == "revoked_key"


def test_revoke_404_when_no_active_key(env):
    res = env.client.delete(f"{BASE}/keys/current")
    assert res.status_code == 404 and res.json()["code"] == "no_active_key"


def test_revoke_still_works_after_feature_is_switched_off(env):
    _add_key(env)
    env.db.rows("tenants")[0]["enabled_features"] = []
    assert env.client.delete(f"{BASE}/keys/current").status_code == 200


def test_revoke_revokes_every_active_key_of_the_tenant(env):
    _add_key(env), _add_key(env)  # operator-created extras
    assert env.client.delete(f"{BASE}/keys/current").json() == {"ok": True, "revoked": 2}
    assert _active_keys(env) == []


def test_revoke_writes_audit(env):
    _add_key(env)
    env.client.delete(f"{BASE}/keys/current")
    assert [a["action"] for a in env.audit] == ["tenant.private_send_key_revoked"]


# ------------------------------------------------------------------ rate limit

def test_create_and_revoke_share_a_5_per_minute_limit(env):
    codes = []
    for _ in range(3):
        codes.append(env.client.post(f"{BASE}/keys").status_code)  # create, revoke, create, revoke, create all pass; the 6th call is limited
        codes.append(env.client.delete(f"{BASE}/keys/current").status_code)
    assert 429 not in codes[:5]
    assert codes[5] == 429
    limited = env.client.post(f"{BASE}/keys")
    assert limited.status_code == 429 and limited.json()["code"] == "rate_limited"
    assert limited.headers["retry-after"] == "60"


# ------------------------------------------------------------------ reply mode

@pytest.mark.parametrize("bad", [{"reply_mode": "both"}, {"reply_mode": ""}, {"reply_mode": None}, {}, {"reply_mode": "aira", "monthly_cap": 5}])
def test_reply_mode_validation_rejects_bad_bodies(env, bad):
    with patch.object(ps, "set_reply_mode", new=AsyncMock()) as set_mode:
        res = env.client.patch(f"{BASE}/settings", json=bad)
    assert res.status_code == 422
    set_mode.assert_not_awaited()


@pytest.mark.parametrize("mode", ["client", "aira"])
def test_reply_mode_valid_values_call_service_for_own_tenant(env, mode):
    with patch.object(ps, "set_reply_mode", new=AsyncMock()) as set_mode:
        res = env.client.patch(f"{BASE}/settings", json={"reply_mode": mode})
    assert res.status_code == 200 and res.json() == {"reply_mode": mode}
    set_mode.assert_awaited_once_with(env.db, TENANT, mode)
    assert env.audit[-1]["action"] == "tenant.private_send_settings_updated"


def test_reply_mode_403_when_feature_not_enabled(env):
    env.ctx["value"] = {**ADMIN_CTX, "tenant_id": OTHER_TENANT}
    with patch.object(ps, "set_reply_mode", new=AsyncMock()) as set_mode:
        res = env.client.patch(f"{BASE}/settings", json={"reply_mode": "aira"})
    assert res.status_code == 403 and res.json()["code"] == "feature_disabled"
    set_mode.assert_not_awaited()


def test_reply_mode_surfaces_service_error_code(env):
    err = ps.PrivateSendError(400, "meta_not_configured", "Save the Meta access token and WABA id first")
    with patch.object(ps, "set_reply_mode", new=AsyncMock(side_effect=err)):
        res = env.client.patch(f"{BASE}/settings", json={"reply_mode": "aira"})
    assert res.status_code == 400 and res.json()["code"] == "meta_not_configured"


# ------------------------------------------------------------------ public key

def _seed_b64(byte: int = 7) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode()


def _expected_public_b64(seed_b64: str) -> str:
    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed_b64))
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def test_public_key_returns_only_the_public_half_of_the_signing_seed(env, monkeypatch):
    seed = _seed_b64()
    monkeypatch.setenv(ps.SIGNING_ENV, seed)
    res = env.client.get(f"{BASE}/public-key")
    assert res.status_code == 200
    body = res.json()
    assert body == {"public_keys": [_expected_public_b64(seed)]}
    assert len(base64.b64decode(body["public_keys"][0])) == 32
    assert seed not in res.text  # the private seed never leaves the server
    assert res.headers["cache-control"] == "no-store"


def test_public_key_verifies_a_real_bundle_signature(env, monkeypatch):
    monkeypatch.setenv(ps.SIGNING_ENV, _seed_b64(9))
    shown = env.client.get(f"{BASE}/public-key").json()["public_keys"][0]
    payload = b'{"hello":"anril"}'
    signature = base64.b64decode(ps.sign_payload(payload))
    Ed25519PublicKey.from_public_bytes(base64.b64decode(shown)).verify(signature, payload)


def test_public_key_503_when_signing_key_missing(env, monkeypatch):
    monkeypatch.delenv(ps.SIGNING_ENV, raising=False)
    res = env.client.get(f"{BASE}/public-key")
    assert res.status_code == 503 and res.json()["code"] == "signing_key_missing"


def test_public_key_503_when_signing_key_is_malformed(env, monkeypatch):
    monkeypatch.setenv(ps.SIGNING_ENV, base64.b64encode(b"too-short").decode())
    res = env.client.get(f"{BASE}/public-key")
    assert res.status_code == 503 and res.json()["code"] == "signing_key_missing"
    assert "too-short" not in res.text


def test_public_key_is_readable_with_settings_view_only(env, monkeypatch):
    monkeypatch.setenv(ps.SIGNING_ENV, _seed_b64())
    env.ctx["value"] = VIEWER_CTX
    assert env.client.get(f"{BASE}/public-key").status_code == 200


def test_public_key_403_without_settings_view(env, monkeypatch):
    monkeypatch.setenv(ps.SIGNING_ENV, _seed_b64())
    env.ctx["value"] = {**VIEWER_CTX, "permissions": ["leads.manage"]}
    assert env.client.get(f"{BASE}/public-key").status_code == 403
