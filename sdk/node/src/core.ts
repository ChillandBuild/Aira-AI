/**
 * Ports of backend/app/services/auto_messages.py (normalize_event, parse_payload, _clean, _resolve,
 * build_components) and backend/app/routes/upload.py (_normalize_phone). The shared vectors in
 * sdk/spec/vectors must pass byte-for-byte.
 */
import {
  PY_WS, collapseWhitespace, isRecord, ownGet, pyLen, pySlice, pyStr, pyStrip, pyTruthy,
} from "./pyCompat.js";

export type JsonRecord = Record<string, unknown>;

export interface Context {
  first_name: string;
  full_name: string;
  page_url: string;
  phone: string;
  extra: Record<string, string>;
}

export interface ParsedPayload {
  phone: string;
  name: string;
  event_raw: string;
  page_url: string;
  extra: Record<string, string>;
}

export const EVENTS = ["interested", "signed_up", "purchased"] as const;

const EVENT_ALIASES: ReadonlyMap<string, string> = new Map(Object.entries({
  interested: "interested", interest: "interested", enquiry: "interested", inquiry: "interested",
  lead: "interested", enquired: "interested",
  signed_up: "signed_up", signup: "signed_up", sign_up: "signed_up", register: "signed_up",
  registered: "signed_up", registration: "signed_up",
  purchased: "purchased", purchase: "purchased", order: "purchased", order_placed: "purchased",
  bought: "purchased", paid: "purchased", sale: "purchased",
}));

const PHONE_KEYS = ["phone", "mobile", "phone_number", "mobile_number", "whatsapp", "whatsapp_number", "contact", "number"];
const NAME_KEYS = ["name", "full_name", "customer_name", "your_name"];
const URL_KEYS = ["page_url", "url", "link"];
const EVENT_KEYS = ["event", "type", "trigger"];
const RESERVED: ReadonlySet<string> = new Set([
  ...PHONE_KEYS, ...NAME_KEYS, ...URL_KEYS, ...EVENT_KEYS, "first_name", "last_name",
]);
const MAX_EXTRA_KEYS = 20;
const MAX_FIELD_CHARS = 200;
const MAX_EXTRA_KEY_CHARS = 50;
const MAX_PARAM_CHARS = 500;

// Python \b / \w are Unicode aware; JS \b is ASCII only. Emulate Python's exactly.
const WORD = "[\\p{L}\\p{N}_]";
const PY_BOUNDARY = `(?:(?<=${WORD})(?!${WORD})|(?<!${WORD})(?=${WORD}))`;
const TLDS = "com|in|net|org|io|co|xyz|link|ly|me|info|biz|app|site|online|shop|top|club|live";

const LINK_RE = new RegExp(`(https?://|www\\.|${PY_BOUNDARY}[a-z0-9-]+\\.(${TLDS})${PY_BOUNDARY})`, "iu");
const VAR_PATTERN = `\\{\\{${PY_WS}*(\\p{Nd}+)${PY_WS}*\\}\\}`;
const UNTRUSTED: ReadonlySet<string> = new Set(["first_name", "full_name", "extra"]);

// ------------------------------------------------------------ parsing

function text(value: unknown): string {
  if (value === null || value === undefined || typeof value === "object") return "";
  return pySlice(pyStrip(pyStr(value)), MAX_FIELD_CHARS);
}

function lowerKeyed(payload: JsonRecord): Map<string, unknown> {
  const lowered = new Map<string, unknown>();
  for (const [key, value] of Object.entries(payload)) lowered.set(pyStrip(key).toLowerCase(), value);
  return lowered;
}

function first(lowered: Map<string, unknown>, keys: readonly string[]): string {
  for (const key of keys) {
    const value = text(lowered.get(key));
    if (value) return value;
  }
  return "";
}

/** null for an event we do not know. Missing/empty means "interested". */
export function normalizeEvent(raw: string | null | undefined): string | null {
  if (!raw) return "interested";
  const slug = pyStrip(raw).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return EVENT_ALIASES.get(slug) ?? null;
}

function collectExtra(payload: JsonRecord): Record<string, string> {
  const extra = new Map<string, string>();
  for (const [key, value] of Object.entries(payload)) {
    const k = pyStrip(key).toLowerCase();
    if (RESERVED.has(k) || k.startsWith("_") || !text(value)) continue;
    if (extra.size >= MAX_EXTRA_KEYS) break;
    extra.set(pySlice(k, MAX_EXTRA_KEY_CHARS), text(value));
  }
  return Object.fromEntries(extra);
}

export function parsePayload(payload: JsonRecord): ParsedPayload {
  const lowered = lowerKeyed(payload);
  const fullName = first(lowered, NAME_KEYS);
  const name = fullName || [first(lowered, ["first_name"]), first(lowered, ["last_name"])].filter(Boolean).join(" ");
  return {
    phone: first(lowered, PHONE_KEYS),
    name,
    event_raw: first(lowered, EVENT_KEYS),
    page_url: first(lowered, URL_KEYS),
    extra: collectExtra(payload),
  };
}

// ------------------------------------------------------------ phone

const MIN_PHONE_DIGITS = 8;
const MAX_PHONE_DIGITS = 15;

function inDigitRange(digits: string): boolean {
  const length = pyLen(digits);
  return length >= MIN_PHONE_DIGITS && length <= MAX_PHONE_DIGITS;
}

/** Port of _normalize_phone: E.164-ish with +, Indian 10-digit mobiles get +91. */
export function normalizePhone(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const stripped = pyStrip(raw);
  const kept = stripped.replace(/[^\p{Nd}+]/gu, "");
  if (!kept) return null;
  const digits = kept.replace(/^\++/, "").replace(/^0+/, "");
  const length = pyLen(digits);
  if (length === 10 && "6789".includes(digits[0] ?? "x")) return `+91${digits}`;
  if (length === 12 && digits.startsWith("91") && "6789".includes(digits[2] ?? "x")) return `+${digits}`;
  return inDigitRange(digits) ? `+${digits}` : null;
}

// ------------------------------------------------------------ components

/** Meta rejects text parameters with newlines, tabs or long runs of spaces. */
export function clean(value: unknown): string {
  if (!pyTruthy(value)) return "";
  return pySlice(pyStrip(collapseWhitespace(pyStr(value))), MAX_PARAM_CHARS);
}

function lookup(spec: JsonRecord, ctx: Context, source: string): unknown {
  if (source === "text") return spec.value || "";
  if (source === "extra") {
    const key = pyStrip(String(spec.key || "")).toLowerCase();
    return ownGet(ctx.extra, key) ?? "";
  }
  return ownGet(ctx, source) || "";
}

export function resolve(spec: unknown, ctx: Context, defaultSource: string): string {
  const base: JsonRecord = isRecord(spec) && pyTruthy(spec) ? spec : { source: defaultSource };
  const source = typeof base.source === "string" && base.source ? base.source : defaultSource;
  let value = clean(lookup(base, ctx, source));
  if (UNTRUSTED.has(source) && LINK_RE.test(value)) value = "";
  return value || clean(base.fallback) || "-";
}

const URL_SAFE = new Set("/?=&-_.~");
const encoder = new TextEncoder();

/** Python urllib.parse.quote(value, safe="/?=&-_.~"). */
export function quote(value: string): string {
  let out = "";
  for (const byte of encoder.encode(value)) {
    const ch = String.fromCharCode(byte);
    const isAlnum = /[A-Za-z0-9]/.test(ch);
    out += isAlnum || URL_SAFE.has(ch) ? ch : `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
  }
  return out;
}

function hasVar(value: unknown): boolean {
  return new RegExp(VAR_PATTERN, "u").test(typeof value === "string" ? value : "");
}

function distinctVarCount(body: unknown): number {
  const found = new Set<string>();
  for (const m of (typeof body === "string" ? body : "").matchAll(new RegExp(VAR_PATTERN, "gu"))) found.add(m[1] as string);
  return found.size;
}

function headerComponent(template: JsonRecord, ctx: Context): JsonRecord[] {
  const mediaType = String(template.header_media_type || "").toUpperCase();
  if (mediaType === "IMAGE" || mediaType === "VIDEO" || mediaType === "DOCUMENT") {
    const link = template.header_media_url;
    if (!link) return [];
    const kind = mediaType.toLowerCase();
    return [{ type: "header", parameters: [{ type: kind, [kind]: { link } }] }];
  }
  if (!hasVar(template.header_text)) return [];
  const value = resolve({ source: "first_name", fallback: "there" }, ctx, "first_name");
  return [{ type: "header", parameters: [{ type: "text", text: value }] }];
}

function bodyComponent(template: JsonRecord, rule: JsonRecord, ctx: Context): JsonRecord[] {
  const count = distinctVarCount(template.body_text);
  if (!count) return [];
  const specs = Array.isArray(rule.variables) ? rule.variables : [];
  const parameters = Array.from({ length: count }, (_, i) => ({
    type: "text",
    text: resolve(i < specs.length ? specs[i] : null, ctx, i === 0 ? "first_name" : "text"),
  }));
  return [{ type: "body", parameters }];
}

function buttonComponents(template: JsonRecord, rule: JsonRecord, ctx: Context): JsonRecord[] {
  const buttons = Array.isArray(template.buttons) ? template.buttons : [];
  const out: JsonRecord[] = [];
  buttons.forEach((btn: unknown, index: number) => {
    if (!isRecord(btn)) return;
    if (String(btn.type || "").toUpperCase() !== "URL" || !hasVar(btn.url)) return;
    const suffix = quote(resolve(rule.button_param, ctx, "text"));
    out.push({ type: "button", sub_type: "url", index: String(index), parameters: [{ type: "text", text: suffix }] });
  });
  return out;
}

export function buildComponents(template: JsonRecord, rule: JsonRecord, ctx: Context): JsonRecord[] {
  return [...headerComponent(template, ctx), ...bodyComponent(template, rule, ctx), ...buttonComponents(template, rule, ctx)];
}

// ------------------------------------------------------------ context

/** The ctx the backend's send_one builds: first_name, full_name, page_url, phone, extra. */
export function buildContext(
  name: string | null | undefined, phone: string, extra?: JsonRecord | null, pageUrl?: string | null,
): Context {
  const fullName = pyStrip(name ?? "");
  const extras = new Map<string, string>();
  for (const [key, value] of Object.entries(extra ?? {})) {
    const v = text(value);
    if (v) extras.set(pySlice(pyStrip(key).toLowerCase(), MAX_EXTRA_KEY_CHARS), v);
  }
  if (pageUrl) extras.set("page_url", text(pageUrl));
  const extraObj = Object.fromEntries(extras);
  return {
    first_name: fullName ? (fullName.split(" ")[0] ?? "") : "",
    full_name: fullName,
    page_url: extras.get("page_url") ?? "",
    phone,
    extra: extraObj,
  };
}
