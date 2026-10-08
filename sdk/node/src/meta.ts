/**
 * WhatsApp Cloud API template send, using the client's own Meta token. The token goes only in the
 * Authorization header of this one request; it is never logged or placed in an error.
 */
import type { FetchFn } from "./http.js";

export const GRAPH_BASE = "https://graph.facebook.com";
const META_TIMEOUT_MS = 15_000;
const RETRYABLE_STATUSES: readonly number[] = [429, 503];
/** Socket-level codes where the connection was never made (fetch reports them as err.cause.code). */
const NEVER_CONNECTED_CODES: readonly string[] = [
  "ECONNREFUSED", "ENOTFOUND", "EAI_AGAIN", "ENETUNREACH", "EHOSTUNREACH", "UND_ERR_CONNECT_TIMEOUT",
];

/** Only a failed connect is safe to repeat; a read timeout or reset may mean Meta already took the message. */
function neverArrived(err: unknown): boolean {
  const code = (err as { cause?: { code?: unknown } } | null)?.cause?.code;
  return typeof code === "string" && NEVER_CONNECTED_CODES.includes(code);
}

export interface MetaOutcome {
  ok: boolean;
  messageId?: string;
  reason?: string;
  /** The request provably never reached Meta, so sending it again cannot double-send. */
  retryable?: boolean;
}

/** Same body as backend/app/services/meta_cloud.py::send_template_message. */
export function templateBody(
  toNumber: string, templateName: string, langCode: string, components: readonly object[],
): Record<string, unknown> {
  return {
    messaging_product: "whatsapp",
    to: toNumber,
    type: "template",
    template: { name: templateName, language: { code: langCode }, components: components.length ? components : [] },
  };
}

async function errorReason(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { error?: { code?: unknown; message?: unknown } };
    const { code, message } = body?.error ?? {};
    if (message) return code !== undefined && code !== null ? `meta_${code}: ${message}` : `meta: ${message}`;
  } catch {
    // fall through to the status code
  }
  return `http_${resp.status}`;
}

async function messageIdOf(resp: Response): Promise<string | undefined> {
  try {
    const body = (await resp.json()) as { messages?: { id?: unknown }[] };
    const id = body?.messages?.[0]?.id;
    return typeof id === "string" ? id : undefined;
  } catch {
    return undefined;
  }
}

export async function sendTemplate(
  fetchFn: FetchFn, graphVersion: string, phoneNumberId: string, token: string, body: Record<string, unknown>,
): Promise<MetaOutcome> {
  const url = `${GRAPH_BASE}/${graphVersion}/${phoneNumberId}/messages`;
  let resp: Response;
  try {
    resp = await fetchFn(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(META_TIMEOUT_MS),
    });
  } catch (err) {
    return { ok: false, reason: `network_error: ${err instanceof Error ? err.name : "Error"}`, retryable: neverArrived(err) };
  }
  if (!resp.ok) return { ok: false, reason: await errorReason(resp), retryable: RETRYABLE_STATUSES.includes(resp.status) };
  return { ok: true, messageId: await messageIdOf(resp) };
}
