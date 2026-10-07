import { generateKeyPairSync, sign, type KeyObject } from "node:crypto";
import type { BundleData } from "../src/bundle.js";

export const BASE = "https://aira.test";
export const LICENSE_KEY = "aps_live_" + "A".repeat(32);
export const META_TOKEN = "EAAmetaTOKENsecret";

export interface Keys {
  publicB64: string;
  privateKey: KeyObject;
}

export function makeKeys(): Keys {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const der = publicKey.export({ format: "der", type: "spki" });
  return { publicB64: Buffer.from(der.subarray(der.length - 32)).toString("base64"), privateKey };
}

export function envelope(keys: Keys, data: unknown): { payload: string; sig: string; key_id: string } {
  const raw = Buffer.from(JSON.stringify(data), "utf8");
  return {
    payload: raw.toString("base64"),
    sig: sign(null, raw, keys.privateKey).toString("base64"),
    key_id: "v1",
  };
}

export function bundleData(now: Date, overrides: Partial<BundleData> = {}): BundleData {
  return {
    version: 1,
    tenant_id: "t1",
    issued_at: now.toISOString(),
    expires_at: new Date(now.getTime() + 15 * 60_000).toISOString(),
    offline_grace_hours: 6,
    limits: { monthly_cap: 50000, used: 10, blocked: false },
    rules: [
      { id: "r1", event: "purchased", template_id: "tp1", delay_minutes: 0, variables: null, button_param: null, enabled: true },
      { id: "r2", event: "signed_up", template_id: "tp1", delay_minutes: 30, variables: null, button_param: null, enabled: true },
    ],
    templates: [
      { id: "tp1", name: "loan_ready", language: "en", category: "UTILITY", body_text: "Hi {{1}}, your loan is approved.",
        header_text: null, header_media_type: null, header_media_url: null, buttons: [] },
    ],
    ...overrides,
  };
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | undefined;
}

export type Handler = (call: Call) => Response | Promise<Response>;

/** Fetch mock that records every call and routes it by URL. */
export function mockFetch(handlers: { bundle?: Handler; usage?: Handler; meta?: Handler }) {
  const calls: Call[] = [];
  const fn = (async (input: string | URL | Request, init?: RequestInit) => {
    const call: Call = {
      url: String(input),
      method: init?.method ?? "GET",
      headers: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>)),
      body: typeof init?.body === "string" ? init.body : undefined,
    };
    calls.push(call);
    if (call.url.includes("/private-send/bundle")) return handlers.bundle!(call);
    if (call.url.includes("/private-send/usage")) return handlers.usage!(call);
    if (call.url.startsWith("https://graph.facebook.com/")) return handlers.meta!(call);
    throw new Error(`unexpected host: ${call.url}`);
  }) as typeof fetch;
  return { fn, calls };
}

export class FakeClock {
  constructor(public now: Date) {}
  read = (): Date => new Date(this.now.getTime());
  advance(ms: number): void {
    this.now = new Date(this.now.getTime() + ms);
  }
}
