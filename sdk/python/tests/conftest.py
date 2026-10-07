import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from anril_private_send import AnrilPrivateSend

LICENSE_KEY = "aps_live_" + "A" * 32
META_TOKEN = "EAAG-secret-meta-token"
PHONE_NUMBER_ID = "1234567890"
T0 = datetime(2026, 10, 7, 10, 0, 0, tzinfo=timezone.utc)

TEMPLATE_ID = "tpl-1"
SLOW_TEMPLATE_ID = "tpl-2"


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def public_b64(private: Ed25519PrivateKey) -> str:
    return b64(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def default_payload(now: datetime = T0, **overrides) -> dict:
    payload = {
        "version": 1, "tenant_id": "tenant-1",
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        "offline_grace_hours": 6,
        "limits": {"monthly_cap": 50000, "used": 10, "blocked": False},
        "rules": [
            {"id": "r1", "event": "purchased", "template_id": TEMPLATE_ID, "delay_minutes": 0,
             "variables": [{"source": "first_name", "fallback": "there"}], "button_param": None, "enabled": True},
            {"id": "r2", "event": "signed_up", "template_id": SLOW_TEMPLATE_ID, "delay_minutes": 30,
             "variables": [], "button_param": None, "enabled": True},
        ],
        "templates": [
            {"id": TEMPLATE_ID, "name": "loan_ready", "language": "en", "category": "UTILITY",
             "body_text": "Hi {{1}}, your loan is approved.", "header_text": None,
             "header_media_type": None, "header_media_url": None, "buttons": []},
            {"id": SLOW_TEMPLATE_ID, "name": "welcome", "language": "en_US", "category": "UTILITY",
             "body_text": "Welcome {{1}}!", "header_text": None,
             "header_media_type": None, "header_media_url": None, "buttons": []},
        ],
    }
    return {**payload, **overrides}


def envelope(private: Ed25519PrivateKey, payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    return {"payload": b64(raw), "sig": b64(private.sign(raw)), "key_id": "v1"}


class Clock:
    def __init__(self, now: datetime = T0):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now = self.now + timedelta(**kwargs)


class FakeAnril:
    """Routes bundle / usage / Meta calls and records every request."""

    def __init__(self, private: Ed25519PrivateKey, clock: Clock):
        self.private = private
        self.clock = clock
        self.bundle_status = 200
        self.bundle_network_error = False
        self.bundle_body = None  # override the 200 body
        self.bundle_error_code = None
        self.payload_overrides = {}
        self.usage_status = 200
        self.usage_json = {"ok": True, "accepted": 1}
        self.meta_status = 200
        self.meta_json = {"messages": [{"id": "wamid.ABC"}]}
        self.requests = []

    def _bundle(self) -> httpx.Response:
        if self.bundle_status != 200:
            body = {"error": "x", "code": self.bundle_error_code} if self.bundle_error_code else {}
            return httpx.Response(self.bundle_status, json=body)
        if self.bundle_body is not None:
            return httpx.Response(200, json=self.bundle_body)
        payload = default_payload(self.clock.now, **self.payload_overrides)
        return httpx.Response(200, json=envelope(self.private, payload))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/private-send/bundle"):
            if self.bundle_network_error:
                raise httpx.ConnectError("down")
            return self._bundle()
        if request.url.path.endswith("/private-send/usage"):
            return httpx.Response(self.usage_status, json=self.usage_json)
        if request.url.host == "graph.facebook.com":
            return httpx.Response(self.meta_status, json=self.meta_json)
        return httpx.Response(404)

    def calls(self, suffix: str):
        return [r for r in self.requests if r.url.path.endswith(suffix)]

    def meta_calls(self):
        return [r for r in self.requests if r.url.host == "graph.facebook.com"]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def private_key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def anril(private_key, clock):
    return FakeAnril(private_key, clock)


@pytest.fixture
def client(private_key, clock, anril):
    http = httpx.Client(transport=httpx.MockTransport(anril))
    c = AnrilPrivateSend(
        license_key=LICENSE_KEY, meta_token=META_TOKEN, phone_number_id=PHONE_NUMBER_ID,
        anril_public_key=public_b64(private_key), store="sqlite:///:memory:", http=http, clock=clock,
    )
    yield c
    c.close()
