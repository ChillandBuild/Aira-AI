import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aira_private_send import BundleUnavailable, LicenseError, QuotaExceeded
from conftest import LICENSE_KEY, b64, default_payload, envelope


def test_good_signature_is_used_and_headers_sent(client, aira):
    assert client.track("purchased", "9876543210", name="Asha Rao").status == "sent"
    req = aira.calls("/bundle")[0]
    assert req.headers["Authorization"] == f"Bearer {LICENSE_KEY}"
    assert req.headers["X-Aira-Plugin"].startswith("python/")


def test_bad_signature_is_never_used(client, aira, clock):
    other = Ed25519PrivateKey.generate()
    aira.bundle_body = envelope(other, default_payload(clock.now))
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9876543210")
    assert aira.meta_calls() == []


def test_tampered_payload_is_rejected(client, aira, clock):
    env = envelope(aira.private, default_payload(clock.now))
    tampered = default_payload(clock.now, tenant_id="evil")
    env["payload"] = b64(json.dumps(tampered).encode())
    aira.bundle_body = env
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9876543210")


def test_garbage_body_is_a_failed_refresh(client, aira):
    aira.bundle_body = {"nope": 1}
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9876543210")


def test_already_expired_bundle_is_rejected(client, aira, clock):
    aira.payload_overrides = {"expires_at": "2026-10-07T09:00:00Z"}
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9876543210")


def test_bundle_cached_for_five_minutes_then_refreshed(client, aira, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=4)
    client.track("purchased", "9123456789")
    assert len(aira.calls("/bundle")) == 1
    clock.advance(minutes=2)
    client.track("purchased", "9012345678")
    assert len(aira.calls("/bundle")) == 2


@pytest.mark.parametrize("status", [429, 500, 503])
def test_offline_grace_uses_last_verified_bundle(client, aira, clock, status):
    client.track("purchased", "9876543210")
    aira.bundle_status = status
    clock.advance(hours=5, minutes=59)
    assert client.track("purchased", "9123456789").status == "sent"


def test_offline_grace_over_refuses_to_send(client, aira, clock):
    client.track("purchased", "9876543210")
    aira.bundle_status = 503
    clock.advance(hours=6, minutes=1)
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9123456789")
    assert len(aira.meta_calls()) == 1


def test_grace_is_measured_from_last_successful_fetch(client, aira, clock):
    client.track("purchased", "9876543210")
    aira.bundle_status = 503
    clock.advance(hours=3)
    client.track("purchased", "9123456789")  # failed refresh must not extend the window
    clock.advance(hours=3, minutes=1)
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9012345678")


def test_network_error_falls_back_to_grace(client, aira, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=10)
    aira.bundle_network_error = True
    assert client.track("purchased", "9123456789").status == "sent"


@pytest.mark.parametrize("status,code", [(401, "invalid_key"), (401, "revoked_key"), (403, "feature_disabled")])
def test_license_errors_stop_at_once_and_drop_cache(client, aira, clock, status, code):
    client.track("purchased", "9876543210")
    aira.bundle_status, aira.bundle_error_code = status, code
    clock.advance(minutes=6)
    with pytest.raises(LicenseError) as err:
        client.track("purchased", "9123456789")
    assert err.value.code == code
    assert LICENSE_KEY not in str(err.value)
    aira.bundle_status = 503  # cache was dropped: grace must NOT rescue it
    with pytest.raises(BundleUnavailable):
        client.track("purchased", "9012345678")


def test_blocked_bundle_raises_quota_exceeded(client, aira):
    aira.payload_overrides = {"limits": {"monthly_cap": 10, "used": 10, "blocked": True}}
    with pytest.raises(QuotaExceeded):
        client.track("purchased", "9876543210")
    assert aira.meta_calls() == []


def test_cached_bundle_survives_restart_via_store(private_key, clock, aira, tmp_path):
    import httpx
    from aira_private_send import AiraPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    db = f"sqlite:///{tmp_path / 'ps.db'}"

    def make():
        return AiraPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key), store=db,
                               http=httpx.Client(transport=httpx.MockTransport(aira)), clock=clock)

    first = make()
    first.track("purchased", "9876543210")
    first.close()
    aira.bundle_status = 503
    clock.advance(hours=1)
    second = make()
    assert second.track("purchased", "9123456789").status == "sent"
    second.close()


def test_bad_public_key_rejected_early(private_key):
    from aira_private_send import AiraPrivateSend
    with pytest.raises(ValueError):
        AiraPrivateSend(LICENSE_KEY, "t", "1", "not-a-key", store="sqlite:///:memory:")


# ---------------------------------------------------------------- key rotation

def test_list_of_keys_verifies_with_any_key(private_key, clock, aira):
    import httpx
    from aira_private_send import AiraPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    old = Ed25519PrivateKey.generate()
    # the bundle is signed by `private_key`, which is the second of the two trusted keys
    http = httpx.Client(transport=httpx.MockTransport(aira))
    c = AiraPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, [public_b64(old), public_b64(private_key)],
                        store="sqlite:///:memory:", http=http, clock=clock)
    assert c.track("purchased", "9876543210").status == "sent"
    c.close()


def test_list_of_keys_still_rejects_an_unknown_signer(private_key, clock, aira):
    import httpx
    from aira_private_send import AiraPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    keys = [public_b64(Ed25519PrivateKey.generate()), public_b64(Ed25519PrivateKey.generate())]
    c = AiraPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, keys, store="sqlite:///:memory:",
                        http=httpx.Client(transport=httpx.MockTransport(aira)), clock=clock)
    with pytest.raises(BundleUnavailable):
        c.track("purchased", "9876543210")
    c.close()


def test_key_id_does_not_pick_the_key(private_key, clock, aira):
    """key_id is informational: a wrong or missing key_id must not stop a valid signature verifying."""
    import httpx
    from aira_private_send import AiraPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    env = envelope(private_key, default_payload(clock.now))
    env["key_id"] = "v999"
    aira.bundle_body = env
    c = AiraPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, [public_b64(private_key)],
                        store="sqlite:///:memory:", http=httpx.Client(transport=httpx.MockTransport(aira)), clock=clock)
    assert c.track("purchased", "9876543210").status == "sent"
    c.close()


def test_empty_or_bad_key_list_rejected():
    from aira_private_send import AiraPrivateSend
    with pytest.raises(ValueError):
        AiraPrivateSend(LICENSE_KEY, "t", "1", [], store="sqlite:///:memory:")
    with pytest.raises(ValueError):
        AiraPrivateSend(LICENSE_KEY, "t", "1", ["bad"], store="sqlite:///:memory:")


# ---------------------------------------------------------------- tenant pin

def test_first_verified_bundle_pins_the_tenant(client, aira):
    client.track("purchased", "9876543210")
    assert client._store.get_meta("pinned_tenant_id") == "tenant-1"


def test_bundle_for_another_tenant_raises_tenant_mismatch(client, aira, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=6)
    aira.payload_overrides = {"tenant_id": "tenant-2"}
    with pytest.raises(LicenseError) as err:
        client.track("purchased", "9123456789")
    assert err.value.code == "tenant_mismatch"
    assert "tenant-1" not in str(err.value) and "tenant-2" not in str(err.value)
    assert len(aira.meta_calls()) == 1  # nothing sent on the foreign bundle
    assert client._store.get_meta("pinned_tenant_id") == "tenant-1"


def test_foreign_bundle_is_never_cached(client, aira, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=6)
    aira.payload_overrides = {"tenant_id": "tenant-2"}
    with pytest.raises(LicenseError):
        client.track("purchased", "9123456789")
    assert "tenant-2" not in (client._store.get_meta("bundle") or "")  # still the tenant-1 bundle on disk


def test_pin_survives_restart(private_key, clock, aira, tmp_path):
    import httpx
    from aira_private_send import AiraPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    db = f"sqlite:///{tmp_path / 'ps.db'}"

    def make():
        return AiraPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key), store=db,
                               http=httpx.Client(transport=httpx.MockTransport(aira)), clock=clock)

    first = make()
    first.track("purchased", "9876543210")
    first.close()
    clock.advance(hours=1)
    aira.payload_overrides = {"tenant_id": "tenant-2"}
    second = make()
    with pytest.raises(LicenseError) as err:
        second.track("purchased", "9123456789")
    assert err.value.code == "tenant_mismatch"
    second.close()
