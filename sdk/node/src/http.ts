import { VERSION } from "./version.js";
import { LicenseError } from "./errors.js";

export type FetchFn = typeof fetch;
export type Clock = () => Date;

export const LICENSE_STATUSES: readonly number[] = [401, 403];

export function anrilHeaders(licenseKey: string): Record<string, string> {
  return { Authorization: `Bearer ${licenseKey}`, "X-Anril-Plugin": `node/${VERSION}` };
}

/** 401/403 from Anril -> LicenseError(code). The body is parsed defensively and never echoed back. */
export async function licenseErrorFor(resp: Response): Promise<LicenseError> {
  let code = resp.status === 401 ? "invalid_key" : "feature_disabled";
  try {
    const body: unknown = await resp.json();
    const bodyCode = (body as { code?: unknown } | null)?.code;
    if (typeof bodyCode === "string") code = bodyCode;
  } catch {
    // keep the default code
  }
  return new LicenseError(code);
}
