import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from anril_connector import LicenseError, QuotaExceeded
from conftest import LICENSE_KEY, b64, default_payload, envelope


def _parked(result):
    """No usable bundle: track() does not raise, it parks the send for run_due and sends nothing."""
    return (result.status, result.reason) == ("queued", "anril_unreachable")


def test_good_signature_is_used_and_headers_sent(client, anril):
    assert client.track("purchased", "9876543210", name="Asha Rao").status == "sent"
    req = anril.calls("/bundle")[0]
    assert req.headers["Authorization"] == f"Bearer {LICENSE_KEY}"
    assert req.headers["X-Anril-Plugin"].startswith("python/")


def test_bad_signature_is_never_used(client, anril, clock):
    other = Ed25519PrivateKey.generate()
    anril.bundle_body = envelope(other, default_payload(clock.now))
    assert _parked(client.track("purchased", "9876543210"))
    assert anril.meta_calls() == []


def test_tampered_payload_is_rejected(client, anril, clock):
    env = envelope(anril.private, default_payload(clock.now))
    tampered = default_payload(clock.now, tenant_id="evil")
    env["payload"] = b64(json.dumps(tampered).encode())
    anril.bundle_body = env
    assert _parked(client.track("purchased", "9876543210"))


def test_garbage_body_is_a_failed_refresh(client, anril):
    anril.bundle_body = {"nope": 1}
    assert _parked(client.track("purchased", "9876543210"))


def test_already_expired_bundle_is_rejected(client, anril, clock):
    anril.payload_overrides = {"expires_at": "2026-10-07T09:00:00Z"}
    assert _parked(client.track("purchased", "9876543210"))


def test_bundle_cached_for_five_minutes_then_refreshed(client, anril, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=4)
    client.track("purchased", "9123456789")
    assert len(anril.calls("/bundle")) == 1
    clock.advance(minutes=2)
    client.track("purchased", "9012345678")
    assert len(anril.calls("/bundle")) == 2


@pytest.mark.parametrize("status", [429, 500, 503])
def test_offline_grace_uses_last_verified_bundle(client, anril, clock, status):
    client.track("purchased", "9876543210")
    anril.bundle_status = status
    clock.advance(hours=5, minutes=59)
    assert client.track("purchased", "9123456789").status == "sent"


def test_offline_grace_over_refuses_to_send(client, anril, clock):
    client.track("purchased", "9876543210")
    anril.bundle_status = 503
    clock.advance(hours=6, minutes=1)
    assert _parked(client.track("purchased", "9123456789"))
    assert len(anril.meta_calls()) == 1


def test_grace_is_measured_from_last_successful_fetch(client, anril, clock):
    client.track("purchased", "9876543210")
    anril.bundle_status = 503
    clock.advance(hours=3)
    client.track("purchased", "9123456789")  # failed refresh must not extend the window
    clock.advance(hours=3, minutes=1)
    assert _parked(client.track("purchased", "9012345678"))


def test_network_error_falls_back_to_grace(client, anril, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=10)
    anril.bundle_network_error = True
    assert client.track("purchased", "9123456789").status == "sent"


@pytest.mark.parametrize("status,code", [(401, "invalid_key"), (401, "revoked_key"), (403, "feature_disabled")])
def test_license_errors_stop_at_once_and_drop_cache(client, anril, clock, status, code):
    client.track("purchased", "9876543210")
    anril.bundle_status, anril.bundle_error_code = status, code
    clock.advance(minutes=6)
    with pytest.raises(LicenseError) as err:
        client.track("purchased", "9123456789")
    assert err.value.code == code
    assert LICENSE_KEY not in str(err.value)
    anril.bundle_status = 503  # cache was dropped: grace must NOT rescue it
    assert _parked(client.track("purchased", "9012345678"))


def test_blocked_bundle_raises_quota_exceeded(client, anril):
    anril.payload_overrides = {"limits": {"monthly_cap": 10, "used": 10, "blocked": True}}
    with pytest.raises(QuotaExceeded):
        client.track("purchased", "9876543210")
    assert anril.meta_calls() == []


def test_cached_bundle_survives_restart_via_store(private_key, clock, anril, tmp_path):
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    db = f"sqlite:///{tmp_path / 'ps.db'}"

    def make():
        return AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key), store=db,
                               http=httpx.Client(transport=httpx.MockTransport(anril)), clock=clock)

    first = make()
    first.track("purchased", "9876543210")
    first.close()
    anril.bundle_status = 503
    clock.advance(hours=1)
    second = make()
    assert second.track("purchased", "9123456789").status == "sent"
    second.close()


def test_bad_public_key_rejected_early(private_key):
    from anril_connector import AnrilPrivateSend
    with pytest.raises(ValueError):
        AnrilPrivateSend(LICENSE_KEY, "t", "1", "not-a-key", store="sqlite:///:memory:")


# ---------------------------------------------------------------- key rotation

def test_list_of_keys_verifies_with_any_key(private_key, clock, anril):
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    old = Ed25519PrivateKey.generate()
    # the bundle is signed by `private_key`, which is the second of the two trusted keys
    http = httpx.Client(transport=httpx.MockTransport(anril))
    c = AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, [public_b64(old), public_b64(private_key)],
                        store="sqlite:///:memory:", http=http, clock=clock)
    assert c.track("purchased", "9876543210").status == "sent"
    c.close()


def test_list_of_keys_still_rejects_an_unknown_signer(private_key, clock, anril):
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    keys = [public_b64(Ed25519PrivateKey.generate()), public_b64(Ed25519PrivateKey.generate())]
    c = AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, keys, store="sqlite:///:memory:",
                        http=httpx.Client(transport=httpx.MockTransport(anril)), clock=clock)
    assert _parked(c.track("purchased", "9876543210"))
    c.close()


def test_key_id_does_not_pick_the_key(private_key, clock, anril):
    """key_id is informational: a wrong or missing key_id must not stop a valid signature verifying."""
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    env = envelope(private_key, default_payload(clock.now))
    env["key_id"] = "v999"
    anril.bundle_body = env
    c = AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, [public_b64(private_key)],
                        store="sqlite:///:memory:", http=httpx.Client(transport=httpx.MockTransport(anril)), clock=clock)
    assert c.track("purchased", "9876543210").status == "sent"
    c.close()


def test_empty_or_bad_key_list_rejected():
    from anril_connector import AnrilPrivateSend
    with pytest.raises(ValueError):
        AnrilPrivateSend(LICENSE_KEY, "t", "1", [], store="sqlite:///:memory:")
    with pytest.raises(ValueError):
        AnrilPrivateSend(LICENSE_KEY, "t", "1", ["bad"], store="sqlite:///:memory:")


# ---------------------------------------------------------------- tenant pin

def test_first_verified_bundle_pins_the_tenant(client, anril):
    client.track("purchased", "9876543210")
    assert client._store.get_meta("pinned_tenant_id") == "tenant-1"


def test_bundle_for_another_tenant_raises_tenant_mismatch(client, anril, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=6)
    anril.payload_overrides = {"tenant_id": "tenant-2"}
    with pytest.raises(LicenseError) as err:
        client.track("purchased", "9123456789")
    assert err.value.code == "tenant_mismatch"
    assert "tenant-1" not in str(err.value) and "tenant-2" not in str(err.value)
    assert len(anril.meta_calls()) == 1  # nothing sent on the foreign bundle
    assert client._store.get_meta("pinned_tenant_id") == "tenant-1"


def test_foreign_bundle_is_never_cached(client, anril, clock):
    client.track("purchased", "9876543210")
    clock.advance(minutes=6)
    anril.payload_overrides = {"tenant_id": "tenant-2"}
    with pytest.raises(LicenseError):
        client.track("purchased", "9123456789")
    assert "tenant-2" not in (client._store.get_meta("bundle") or "")  # still the tenant-1 bundle on disk


def test_pin_survives_restart(private_key, clock, anril, tmp_path):
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    db = f"sqlite:///{tmp_path / 'ps.db'}"

    def make():
        return AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key), store=db,
                               http=httpx.Client(transport=httpx.MockTransport(anril)), clock=clock)

    first = make()
    first.track("purchased", "9876543210")
    first.close()
    clock.advance(hours=1)
    anril.payload_overrides = {"tenant_id": "tenant-2"}
    second = make()
    with pytest.raises(LicenseError) as err:
        second.track("purchased", "9123456789")
    assert err.value.code == "tenant_mismatch"
    second.close()


# ---------------------------------------------------------------- old bundles (quiet hours / delay)

OLD_QUIET_HOURS = {"start": "00:00", "end": "23:59", "tz": "Asia/Kolkata", "categories": ["UTILITY", "MARKETING"]}


def test_old_bundle_with_quiet_hours_and_delay_is_accepted_and_ignored(client, anril, clock):
    """An older backend still sends quiet_hours and delay_minutes. The send is instant regardless, even
    when the quiet window covers the whole day and the rule asks for a 30 minute wait."""
    payload = default_payload(clock.now)
    payload["quiet_hours"] = OLD_QUIET_HOURS
    payload["rules"] = [{**r, "delay_minutes": 30} for r in payload["rules"]]
    anril.bundle_body = envelope(anril.private, payload)
    assert client.track("purchased", "9876543210").status == "sent"
    assert client.track("signed_up", "9123456789").status == "sent"
    assert len(anril.meta_calls()) == 2


@pytest.mark.parametrize("quiet", [None, "garbage", {"start": "25:99", "tz": "Nowhere/Land"}, ["x"]])
def test_malformed_quiet_hours_no_longer_reject_the_bundle(client, anril, clock, quiet):
    anril.bundle_body = envelope(anril.private, {**default_payload(clock.now), "quiet_hours": quiet})
    assert client.track("purchased", "9876543210").status == "sent"


def test_bundle_without_quiet_hours_or_delay_is_accepted(client, anril, clock):
    payload = default_payload(clock.now)
    assert "quiet_hours" not in payload
    assert all("delay_minutes" not in rule for rule in payload["rules"])
    anril.bundle_body = envelope(anril.private, payload)
    assert client.track("purchased", "9876543210").status == "sent"
