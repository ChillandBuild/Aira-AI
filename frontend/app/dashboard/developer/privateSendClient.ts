import { API_URL, getAuthHeaders } from "@/lib/api";

/*
  Typed calls for the Developer page's event-codes list and "Send from your server"
  section. The private-send router answers errors as {"error", "code"}; permission
  (403) and validation (422) answer {"detail"}. Both shapes end up in ApiCallError.
  Nothing here logs: a full license key only ever lives in a response body.
*/

export interface BuiltinEvent {
  key: string;
  label: string;
  description: string;
}

export interface CustomEvent {
  id: string;
  key: string;
  label: string;
  description: string | null;
  created_at: string;
}

export interface EventsResponse {
  builtin: BuiltinEvent[];
  custom: CustomEvent[];
  limit: number;
}

export interface CreatedKey {
  key: string;
  key_prefix: string;
  created_at: string | null;
}

/** "aira" (default): replies come to Anril's inbox. "client": ALL replies for the WhatsApp number go to the client's own system. */
export type ReplyMode = "client" | "aira";

/** How this account's app calls send-template. "template" (default): a template ID. "event": an event code. One way per account. */
export type PartnerSendMode = "template" | "event";

export class ApiCallError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "ApiCallError";
    this.status = status;
    this.code = code;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;
  const parts = detail
    .map((item) => asRecord(item)?.msg)
    .filter((msg): msg is string => typeof msg === "string");
  return parts.length ? parts.join("; ") : null;
}

/** Turns either error body shape into one error. Exported for tests and for the ingest call. */
export function toApiError(status: number, body: unknown): ApiCallError {
  const record = asRecord(body);
  const message =
    (typeof record?.error === "string" ? record.error : null) ??
    detailText(record?.detail) ??
    `Request failed (HTTP ${status})`;
  const code = typeof record?.code === "string" ? record.code : null;
  return new ApiCallError(message, status, code);
}

async function call<T>(method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const auth = await getAuthHeaders();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...auth },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiCallError("Couldn't reach Anril. Check your connection and try again.", 0, "network");
  }
  const parsed: unknown = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, parsed);
  return parsed as T;
}

const PRIVATE_SEND = "/api/v1/private-send";
const AUTO_MESSAGES = "/api/v1/auto-messages";
const PARTNER_SEND_MODE = "/api/v1/intake/partner/send-mode";

export const developerApi = {
  events: () => call<EventsResponse>("GET", `${AUTO_MESSAGES}/events`),
  createKey: () => call<CreatedKey>("POST", `${PRIVATE_SEND}/keys`),
  revokeKey: () => call<{ ok: boolean; revoked: number }>("DELETE", `${PRIVATE_SEND}/keys/current`),
  setReplyMode: (replyMode: ReplyMode) =>
    call<{ reply_mode: ReplyMode }>("PATCH", `${PRIVATE_SEND}/settings`, { reply_mode: replyMode }),
  partnerSendMode: () => call<{ mode: PartnerSendMode }>("GET", PARTNER_SEND_MODE),
  setPartnerSendMode: (mode: PartnerSendMode) => call<{ mode: PartnerSendMode }>("PUT", PARTNER_SEND_MODE, { mode }),
  publicKeys: () => call<{ public_keys: string[] }>("GET", `${PRIVATE_SEND}/public-key`),
};

/** Plain-words message for an error from the calls above. */
export function describeError(err: unknown): string {
  if (!(err instanceof ApiCallError)) return "Something went wrong. Try again.";
  switch (err.code) {
    case "key_exists":
      return "A key already exists. Reload this page to see it, or revoke it before making a new one.";
    case "feature_disabled":
      return "Send from your server isn't switched on for this account. Ask your Anril contact.";
    case "rate_limited":
      return "Too many changes in a short time. Wait a minute and try again.";
    case "no_active_key":
      return "There is no active key to revoke.";
    case "meta_not_configured":
      return "Save your WhatsApp access token and account id in Settings first.";
    case "meta_error":
      return "WhatsApp refused the change. Try again in a moment.";
    case "signing_key_missing":
      return "The public key isn't available right now. Ask your Anril contact.";
    default:
      break;
  }
  if (err.status === 403) return "You need admin access to do this.";
  return err.message;
}
