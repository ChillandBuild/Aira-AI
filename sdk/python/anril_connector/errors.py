"""Errors raised by the Anril Private Send plug-in. None of them ever carry a key or token."""


class AnrilPrivateSendError(Exception):
    """Base class for every plug-in error."""


class LicenseError(AnrilPrivateSendError):
    """Anril rejected the license key (401/403). `code`: invalid_key | revoked_key | feature_disabled."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or f"license rejected: {code}")
        self.code = code


class QuotaExceeded(AnrilPrivateSendError):
    """The monthly cap in the bundle is reached (limits.blocked is true)."""


class BundleUnavailable(AnrilPrivateSendError):
    """No verified bundle is usable: Anril is unreachable and the cached bundle is expired or missing."""
