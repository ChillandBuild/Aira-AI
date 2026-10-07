/** Errors raised by the Aira Private Send plug-in. None of them ever carry a key or token. */

export class AiraPrivateSendError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** Aira rejected the license key (401/403). code: invalid_key | revoked_key | feature_disabled. */
export class LicenseError extends AiraPrivateSendError {
  readonly code: string;
  constructor(code: string, message = "") {
    super(message || `license rejected: ${code}`);
    this.code = code;
  }
}

/** The monthly cap in the bundle is reached (limits.blocked is true). */
export class QuotaExceeded extends AiraPrivateSendError {}

/** No verified bundle is usable: Aira is unreachable and the cached bundle is expired or missing. */
export class BundleUnavailable extends AiraPrivateSendError {}
