/**
 * Fetch, verify and cache the signed rules bundle (contract: sdk/spec/CONTRACT.md).
 *
 * An unverified bundle is never used. Refresh every 5 minutes; if a refresh fails (429, 5xx, network,
 * bad signature) the last verified bundle stays usable until last successful fetch + offline_grace_hours;
 * 401/403 stop everything at once. The license key only goes into the Authorization header.
 */
import { createPublicKey, verify, type KeyObject } from "node:crypto";
import { BundleUnavailable, LicenseError, QuotaExceeded } from "./errors.js";
import { LICENSE_STATUSES, anrilHeaders, licenseErrorFor, type Clock, type FetchFn } from "./http.js";
import type { Store } from "./store.js";

export const REFRESH_AFTER_MS = 5 * 60 * 1000;
export const BUNDLE_PATH = "/api/v1/private-send/bundle";
const META_KEY = "bundle";
export const TENANT_META_KEY = "pinned_tenant_id";
const SUPPORTED_VERSION = 1;
const ED25519_SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");
const ED25519_RAW_LENGTH = 32;
const MS_PER_HOUR = 3_600_000;

export interface BundleRule {
  id: string;
  event: string;
  template_id: string;
  variables?: unknown[] | null;
  button_param?: unknown;
  enabled?: boolean;
}

export interface BundleTemplate {
  id: string;
  name: string;
  language?: string;
  category?: string;
  body_text?: string;
  header_text?: string | null;
  header_media_type?: string | null;
  header_media_url?: string | null;
  buttons?: unknown[];
  [key: string]: unknown;
}

export interface BundleData {
  version: number;
  tenant_id?: string;
  issued_at?: string;
  expires_at: string;
  offline_grace_hours?: number;
  limits?: { monthly_cap?: number | null; used?: number; blocked?: boolean };
  rules: BundleRule[];
  templates: BundleTemplate[];
}

export interface Bundle {
  readonly data: BundleData;
  readonly fetchedAt: Date;
}

export function loadPublicKey(anrilPublicKey: string): KeyObject {
  const raw = typeof anrilPublicKey === "string" ? Buffer.from(anrilPublicKey, "base64") : Buffer.alloc(0);
  if (raw.length !== ED25519_RAW_LENGTH) {
    throw new TypeError("anrilPublicKey must be the base64 of a 32-byte Ed25519 public key");
  }
  return createPublicKey({ key: Buffer.concat([ED25519_SPKI_PREFIX, raw]), format: "der", type: "spki" });
}

/** One base64 key or a list of them (key rotation). A bundle is valid if any key verifies it. */
export function loadPublicKeys(anrilPublicKey: string | readonly string[]): KeyObject[] {
  const specs = typeof anrilPublicKey === "string" ? [anrilPublicKey] : [...anrilPublicKey];
  if (!specs.length) throw new TypeError("anrilPublicKey must contain at least one key");
  return specs.map(loadPublicKey);
}

function verifies(key: KeyObject, raw: Buffer, sig: Buffer): boolean {
  try {
    return verify(null, raw, key, sig);
  } catch {
    return false;
  }
}

function parseTime(value: unknown): Date {
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) throw new Error("bad timestamp");
  return parsed;
}

/**
 * Verify the signature over the raw payload bytes with any of the keys, then parse. The envelope's
 * key_id is informational and never used to pick a key. Throws on anything off.
 */
export function verifyEnvelope(
  publicKeys: KeyObject | readonly KeyObject[], payloadB64: unknown, sigB64: unknown,
): BundleData {
  const keys = Array.isArray(publicKeys) ? (publicKeys as readonly KeyObject[]) : [publicKeys as KeyObject];
  if (typeof payloadB64 !== "string" || typeof sigB64 !== "string") throw new Error("bundle envelope malformed");
  const raw = Buffer.from(payloadB64, "base64");
  const sig = Buffer.from(sigB64, "base64");
  if (!keys.some((key) => verifies(key, raw, sig))) throw new Error("bundle signature invalid");
  const data = JSON.parse(raw.toString("utf8")) as BundleData;
  if (typeof data !== "object" || data === null || data.version !== SUPPORTED_VERSION) {
    throw new Error("unsupported bundle version");
  }
  if (!Array.isArray(data.rules) || !Array.isArray(data.templates)) throw new Error("bundle missing rules/templates");
  parseTime(data.expires_at);
  return data;
}

export function expiresAt(bundle: Bundle): Date {
  return parseTime(bundle.data.expires_at);
}

function graceMs(bundle: Bundle): number {
  return Number(bundle.data.offline_grace_hours ?? 0) * MS_PER_HOUR;
}

export function isBlocked(bundle: Bundle): boolean {
  return Boolean(bundle.data.limits?.blocked);
}

export function ruleFor(bundle: Bundle, event: string): BundleRule | undefined {
  return bundle.data.rules.find((r) => r.event === event && r.enabled !== false);
}

export function templateFor(bundle: Bundle, templateId: string): BundleTemplate | undefined {
  return bundle.data.templates.find((t) => t.id === templateId);
}

export function assertNotBlocked(bundle: Bundle): void {
  if (isBlocked(bundle)) throw new QuotaExceeded("monthly cap reached");
}

export class BundleManager {
  private cached: Bundle | null = null;

  constructor(
    private readonly licenseKey: string,
    private readonly publicKeys: KeyObject | readonly KeyObject[],
    private readonly baseUrl: string,
    private readonly store: Store,
    private readonly fetchFn: FetchFn,
    private readonly clock: Clock = () => new Date(),
  ) {}

  /** A usable verified bundle, refreshing when older than 5 minutes. Throws LicenseError, BundleUnavailable. */
  async current(): Promise<Bundle> {
    const now = this.clock();
    const cached = this.cached ?? (await this.loadCached());
    if (cached && now.getTime() - cached.fetchedAt.getTime() < REFRESH_AFTER_MS && now < expiresAt(cached)) {
      return cached;
    }
    const fresh = await this.refresh(now);
    if (fresh) return fresh;
    if (cached && now.getTime() - cached.fetchedAt.getTime() <= graceMs(cached)) return cached;
    throw new BundleUnavailable("Anril is unreachable and no verified rules bundle is within its offline grace");
  }

  async drop(): Promise<void> {
    this.cached = null;
    await this.store.deleteMeta(META_KEY);
  }

  private async refresh(now: Date): Promise<Bundle | null> {
    let resp: Response;
    try {
      resp = await this.fetchFn(this.baseUrl.replace(/\/+$/, "") + BUNDLE_PATH, { headers: anrilHeaders(this.licenseKey) });
    } catch {
      return null;
    }
    if (LICENSE_STATUSES.includes(resp.status)) {
      await this.drop();
      throw await licenseErrorFor(resp);
    }
    if (resp.status !== 200) return null;
    return this.accept(resp, now);
  }

  private async accept(resp: Response, now: Date): Promise<Bundle | null> {
    let body: { payload?: unknown; sig?: unknown };
    let data: BundleData;
    try {
      body = (await resp.json()) as { payload?: unknown; sig?: unknown };
      data = verifyEnvelope(this.publicKeys, body.payload, body.sig);
    } catch {
      return null;
    }
    const bundle: Bundle = { data, fetchedAt: now };
    if (expiresAt(bundle) <= now) return null;
    await this.checkTenant(data);
    this.cached = bundle;
    await this.store.setMeta(
      META_KEY,
      JSON.stringify({ payload: body.payload, sig: body.sig, fetched_at: now.toISOString() }),
    );
    return bundle;
  }

  /**
   * Pin the first verified bundle's tenant_id in the store; a later verified bundle for another tenant
   * is a failed refresh (not cached) and throws LicenseError('tenant_mismatch').
   */
  private async checkTenant(data: BundleData): Promise<void> {
    const tenant = typeof data.tenant_id === "string" && data.tenant_id ? data.tenant_id : null;
    const pinned = await this.store.getMeta(TENANT_META_KEY);
    if (pinned === null) {
      if (tenant) await this.store.setMeta(TENANT_META_KEY, tenant);
      return;
    }
    if (tenant !== pinned) {
      console.warn("anril bundle rejected: tenant_id does not match the pinned tenant");
      throw new LicenseError("tenant_mismatch", "signed bundle is for a different tenant than this store is pinned to");
    }
  }

  private async loadCached(): Promise<Bundle | null> {
    const raw = await this.store.getMeta(META_KEY);
    if (!raw) return null;
    try {
      const saved = JSON.parse(raw) as { payload: unknown; sig: unknown; fetched_at: string };
      const data = verifyEnvelope(this.publicKeys, saved.payload, saved.sig);
      const bundle: Bundle = { data, fetchedAt: parseTime(saved.fetched_at) };
      this.cached = bundle;
      return bundle;
    } catch {
      return null;
    }
  }
}
