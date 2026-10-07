"""Fetch, verify and cache the signed rules bundle (contract: sdk/spec/CONTRACT.md).

Rules: an unverified bundle is never used; refresh every 5 minutes; if a refresh fails (429, 5xx,
network, bad signature) the last verified bundle stays usable until last successful fetch +
offline_grace_hours; 401/403 stop everything at once. The license key is only ever put in the
Authorization header, never logged or put into an error message."""
from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ._version import __version__
from .errors import BundleUnavailable, LicenseError
from .store import Store

logger = logging.getLogger("aira_private_send")

REFRESH_AFTER = timedelta(minutes=5)
BUNDLE_PATH = "/api/v1/private-send/bundle"
_META_KEY = "bundle"
_TENANT_KEY = "pinned_tenant_id"
_SUPPORTED_VERSION = 1
_LICENSE_STATUSES = (401, 403)

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def aira_headers(license_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {license_key}", "X-Aira-Plugin": f"python/{__version__}"}


def raise_if_license_rejected(resp: httpx.Response) -> None:
    """401/403 from Aira -> LicenseError(code). The body is parsed defensively and never echoed back."""
    if resp.status_code not in _LICENSE_STATUSES:
        return
    code = "invalid_key" if resp.status_code == 401 else "feature_disabled"
    try:
        body = resp.json()
        if isinstance(body, dict) and isinstance(body.get("code"), str):
            code = body["code"]
    except ValueError:
        pass
    raise LicenseError(code)


@dataclass(frozen=True)
class Bundle:
    data: Dict[str, Any]
    fetched_at: datetime

    @property
    def expires_at(self) -> datetime:
        return parse_time(self.data["expires_at"])

    @property
    def grace(self) -> timedelta:
        return timedelta(hours=float(self.data.get("offline_grace_hours", 0)))

    @property
    def blocked(self) -> bool:
        return bool((self.data.get("limits") or {}).get("blocked"))

    def rule_for(self, event: str) -> Optional[Dict[str, Any]]:
        for rule in self.data.get("rules") or []:
            if rule.get("event") == event and rule.get("enabled", True):
                return rule
        return None

    def template(self, template_id: str) -> Optional[Dict[str, Any]]:
        for tpl in self.data.get("templates") or []:
            if tpl.get("id") == template_id:
                return tpl
        return None


def load_public_key(aira_public_key: str) -> Ed25519PublicKey:
    if not isinstance(aira_public_key, str):
        raise ValueError("aira_public_key must be the base64 of a 32-byte Ed25519 public key")
    try:
        raw = base64.b64decode(aira_public_key, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("aira_public_key must be the base64 of a 32-byte Ed25519 public key") from exc


def load_public_keys(aira_public_key: Union[str, Sequence[str]]) -> List[Ed25519PublicKey]:
    """One base64 key or a list of them (key rotation). A bundle is valid if any key verifies it."""
    specs = [aira_public_key] if isinstance(aira_public_key, str) else list(aira_public_key)
    if not specs:
        raise ValueError("aira_public_key must contain at least one key")
    return [load_public_key(spec) for spec in specs]


def verify_envelope(
    public_keys: Union[Ed25519PublicKey, Sequence[Ed25519PublicKey]], payload_b64: str, sig_b64: str,
) -> Dict[str, Any]:
    """Verify the signature over the raw payload bytes with any of the keys, then parse. The envelope's
    key_id is informational and never used to pick a key. Raises ValueError on anything off."""
    keys = [public_keys] if isinstance(public_keys, Ed25519PublicKey) else list(public_keys)
    try:
        raw = base64.b64decode(payload_b64, validate=True)
        sig = base64.b64decode(sig_b64, validate=True)
    except (binascii.Error, TypeError) as exc:
        raise ValueError("bundle signature invalid") from exc
    if not any(_verifies(key, sig, raw) for key in keys):
        raise ValueError("bundle signature invalid")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("version") != _SUPPORTED_VERSION:
        raise ValueError("unsupported bundle version")
    for field in ("expires_at", "rules", "templates"):
        if field not in data:
            raise ValueError(f"bundle missing {field}")
    parse_time(data["expires_at"])
    return data


def _verifies(key: Ed25519PublicKey, sig: bytes, raw: bytes) -> bool:
    try:
        key.verify(sig, raw)
    except InvalidSignature:
        return False
    return True


class BundleManager:
    def __init__(
        self, license_key: str, public_keys: Sequence[Ed25519PublicKey], base_url: str, store: Store,
        http: httpx.Client, clock: Clock = utcnow,
    ):
        self._license_key = license_key
        self._public_keys = list(public_keys)
        self._url = base_url.rstrip("/") + BUNDLE_PATH
        self._store = store
        self._http = http
        self._clock = clock
        self._cached: Optional[Bundle] = None

    def current(self) -> Bundle:
        """A usable verified bundle, refreshing when older than 5 minutes. Raises LicenseError,
        BundleUnavailable."""
        now = self._clock()
        cached = self._cached or self._load_cached()
        if cached and now - cached.fetched_at < REFRESH_AFTER and now < cached.expires_at:
            return cached
        fresh = self._refresh(now)
        if fresh:
            return fresh
        if cached and now - cached.fetched_at <= cached.grace:
            return cached
        raise BundleUnavailable("Aira is unreachable and no verified rules bundle is within its offline grace")

    def _refresh(self, now: datetime) -> Optional[Bundle]:
        try:
            resp = self._http.get(self._url, headers=aira_headers(self._license_key))
        except httpx.HTTPError as exc:
            logger.warning("aira bundle refresh failed: %s", type(exc).__name__)
            return None
        if resp.status_code in _LICENSE_STATUSES:
            self.drop()
            raise_if_license_rejected(resp)
        if resp.status_code != 200:
            logger.warning("aira bundle refresh failed: HTTP %s", resp.status_code)
            return None
        return self._accept(resp, now)

    def _accept(self, resp: httpx.Response, now: datetime) -> Optional[Bundle]:
        try:
            body = resp.json()
            data = verify_envelope(self._public_keys, body["payload"], body["sig"])
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("aira bundle rejected: %s", exc)
            return None
        bundle = Bundle(data=data, fetched_at=now)
        if bundle.expires_at <= now:
            logger.warning("aira bundle rejected: already expired")
            return None
        self._check_tenant(data)
        self._cached = bundle
        self._store.set_meta(_META_KEY, json.dumps({"payload": body["payload"], "sig": body["sig"], "fetched_at": now.isoformat()}))
        return bundle

    def _check_tenant(self, data: Dict[str, Any]) -> None:
        """Pin the first verified bundle's tenant_id in the store; a later verified bundle for another
        tenant is a failed refresh (not cached) and raises LicenseError('tenant_mismatch')."""
        tenant = data.get("tenant_id")
        tenant = tenant if isinstance(tenant, str) and tenant else None
        pinned = self._store.get_meta(_TENANT_KEY)
        if pinned is None:
            if tenant:
                self._store.set_meta(_TENANT_KEY, tenant)
            return
        if tenant != pinned:
            logger.warning("aira bundle rejected: tenant_id does not match the pinned tenant")
            raise LicenseError("tenant_mismatch", "signed bundle is for a different tenant than this store is pinned to")

    def _load_cached(self) -> Optional[Bundle]:
        raw = self._store.get_meta(_META_KEY)
        if not raw:
            return None
        try:
            saved = json.loads(raw)
            data = verify_envelope(self._public_keys, saved["payload"], saved["sig"])
            bundle = Bundle(data=data, fetched_at=parse_time(saved["fetched_at"]))
        except (ValueError, KeyError, TypeError):
            return None
        self._cached = bundle
        return bundle

    def drop(self) -> None:
        self._cached = None
        self._store.delete_meta(_META_KEY)
