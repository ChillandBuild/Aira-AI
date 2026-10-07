/** Errors raised by the Anril Private Send plug-in. None of them ever carry a key or token. */

export class AnrilPrivateSendError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** Anril rejected the license key (401/403). code: invalid_key | revoked_key | feature_disabled. */
export class LicenseError extends AnrilPrivateSendError {
  readonly code: string;
  constructor(code: string, message = "") {
    super(message || `license rejected: ${code}`);
    this.code = code;
  }
}

/** The monthly cap in the bundle is reached (limits.blocked is true). */
export class QuotaExceeded extends AnrilPrivateSendError {}

/** No verified bundle is usable: Anril is unreachable and the cached bundle is expired or missing. */
export class BundleUnavailable extends AnrilPrivateSendError {}
