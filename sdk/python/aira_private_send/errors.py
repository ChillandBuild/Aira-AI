"""Errors raised by the Aira Private Send plug-in. None of them ever carry a key or token."""


class AiraPrivateSendError(Exception):
    """Base class for every plug-in error."""


class LicenseError(AiraPrivateSendError):
    """Aira rejected the license key (401/403). `code`: invalid_key | revoked_key | feature_disabled."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or f"license rejected: {code}")
        self.code = code


class QuotaExceeded(AiraPrivateSendError):
    """The monthly cap in the bundle is reached (limits.blocked is true)."""


class BundleUnavailable(AiraPrivateSendError):
    """No verified bundle is usable: Aira is unreachable and the cached bundle is expired or missing."""
