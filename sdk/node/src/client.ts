/** AnrilPrivateSend: track events, send via the client's own Meta token, report counts only. */
import { assertNotBlocked, BundleManager, loadPublicKeys, ruleFor, templateFor, type Bundle } from "./bundle.js";
import { buildComponents, buildContext, normalizeEvent, normalizePhone, type JsonRecord } from "./core.js";
import { BundleUnavailable } from "./errors.js";
import { anrilHeaders, licenseErrorFor, LICENSE_STATUSES, type Clock, type FetchFn } from "./http.js";
import { sendTemplate, templateBody, type MetaOutcome } from "./meta.js";
import { iso, openStore, type CounterRow, type SendRow, type Store, type StoredSend } from "./store.js";
import { VERSION } from "./version.js";

const STUCK_AFTER_MS = 15 * 60_000;
const RETRY_DELAY_MS = 60_000;
const RETRY_WINDOW_MS = 3_600_000;
const USAGE_INTERVAL_MS = 15 * 60_000;
const DAY_MS = 86_400_000;
const USAGE_PATH = "/api/v1/private-send/usage";
const MAX_USAGE_ROWS = 500;
const DUE_BATCH = 50;
const HTTP_TIMEOUT_MS = 20_000;
const LAST_USAGE_KEY = "last_usage_report";
const PHONE_NUMBER_ID_RE = /^\d+$/;
const GRAPH_VERSION_RE = /^v\d+\.\d+$/;
const LOCAL_HTTP_HOSTS: readonly string[] = ["localhost", "127.0.0.1"];

type UsageOutcome = "ok" | "rejected" | "retry";

/** https only (the license key rides in the Authorization header); http is allowed for localhost tests. */
function checkBaseUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new TypeError("anrilBaseUrl is not a valid URL");
  }
  const isHttps = parsed.protocol === "https:" && parsed.hostname !== "";
  const isLocalHttp = parsed.protocol === "http:" && LOCAL_HTTP_HOSTS.includes(parsed.hostname);
  if (!isHttps && !isLocalHttp) {
    throw new TypeError("anrilBaseUrl must be https:// (http:// is only allowed for localhost and 127.0.0.1)");
  }
  return url;
}

export interface AnrilPrivateSendOptions {
  licenseKey: string;
  metaToken: string;
  phoneNumberId: string;
  /** One base64 key, or a list of them while Anril rotates its signing key. */
  anrilPublicKey: string | readonly string[];
  store?: string | Store;
  anrilBaseUrl?: string;
  graphVersion?: string;
  fetch?: FetchFn;
  clock?: Clock;
}

export interface TrackInput {
  phone: string;
  name?: string | null;
  extra?: JsonRecord | null;
  pageUrl?: string | null;
}

export interface SendResult {
  /** queued = waiting for a retry because Meta or Anril could not be reached */
  status: "sent" | "failed" | "queued" | "skipped";
  reason?: string;
  messageId?: string;
}

interface UsageRow {
  day: string;
  event: string;
  template_id: string;
  sent: number;
  failed: number;
}

const utcDay = (moment: Date): string => moment.toISOString().slice(0, 10);

export class AnrilPrivateSend {
  readonly #licenseKey: string;
  readonly #metaToken: string;
  private readonly phoneNumberId: string;
  private readonly baseUrl: string;
  private readonly graphVersion: string;
  private readonly fetchFn: FetchFn;
  private readonly clock: Clock;
  private readonly storeSpec: string | Store;
  private readonly publicKey: ReturnType<typeof loadPublicKeys>;
  private storeReady: Promise<{ store: Store; bundles: BundleManager }> | null = null;

  constructor(options: AnrilPrivateSendOptions) {
    for (const [label, value] of [
      ["licenseKey", options.licenseKey], ["metaToken", options.metaToken],
      ["phoneNumberId", options.phoneNumberId],
    ] as const) {
      if (!value) throw new Error(`${label} is required`);
    }
    if (typeof options.phoneNumberId !== "string" || !PHONE_NUMBER_ID_RE.test(options.phoneNumberId)) {
      throw new TypeError("phoneNumberId must contain digits only");
    }
    const graphVersion = options.graphVersion ?? "v21.0";
    if (typeof graphVersion !== "string" || !GRAPH_VERSION_RE.test(graphVersion)) {
      throw new TypeError("graphVersion must look like v21.0");
    }
    this.#licenseKey = options.licenseKey;
    this.#metaToken = options.metaToken;
    this.phoneNumberId = options.phoneNumberId;
    this.baseUrl = checkBaseUrl(options.anrilBaseUrl ?? "https://aira-ai-5tfr.onrender.com").replace(/\/+$/, "");
    this.graphVersion = graphVersion;
    this.fetchFn = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.clock = options.clock ?? (() => new Date());
    this.storeSpec = options.store ?? "sqlite:./anril_connector.db";
    this.publicKey = loadPublicKeys(options.anrilPublicKey);
  }

  /** Never show the license key or Meta token. */
  toString(): string {
    return `AnrilPrivateSend(phoneNumberId=${this.phoneNumberId}, plugin=node/${VERSION})`;
  }

  toJSON(): { phoneNumberId: string; plugin: string } {
    return { phoneNumberId: this.phoneNumberId, plugin: `node/${VERSION}` };
  }

  [Symbol.for("nodejs.util.inspect.custom")](): string {
    return this.toString();
  }

  // ------------------------------------------------------------ public API

  /**
   * Send the matching template now. No checks: no opt-out list, no duplicate window, no quiet hours, no
   * delay. The row is written 'queued' and delivered in the same call; it stays queued (for runDue) only
   * when Meta or Anril could not be reached.
   */
  async track(event: string, input: TrackInput): Promise<SendResult> {
    const normEvent = normalizeEvent(event);
    if (!normEvent) throw new Error(`unknown event ${JSON.stringify(event)}`);
    const phone = normalizePhone(input.phone);
    if (!phone) throw new Error("missing or invalid phone");
    const { store, bundles } = await this.ready();
    const now = this.clock();
    let bundle: Bundle;
    try {
      bundle = await bundles.current();
    } catch (err) {
      if (err instanceof BundleUnavailable) return this.parkForRetry(store, phone, normEvent, input, now);
      throw err;
    }
    assertNotBlocked(bundle);
    const rule = ruleFor(bundle, normEvent);
    if (!rule) return this.skip(store, phone, normEvent, null, "no_rule", now);
    const row = queueRow(phone, normEvent, rule.template_id, input, now, now);
    const id = await store.insertSend(row);
    return this.deliver(store, { ...row, id, extra: row.extra ?? {} }, bundle);
  }

  /**
   * The retry path: send queued rows left by an unreachable Meta or Anril. Returns how many were sent.
   * A row still failing an hour after it was created is failed for good.
   */
  async runDue(): Promise<number> {
    const { store, bundles } = await this.ready();
    const now = this.clock();
    await store.failStuck(new Date(now.getTime() - STUCK_AFTER_MS));
    const due = await store.dueSends(now, DUE_BATCH);
    const live: StoredSend[] = [];
    for (const row of due) {
      if (!(await this.giveUpIfStale(store, row, now))) live.push(row);
    }
    if (!live.length) return 0;
    const bundle = await bundles.current();
    assertNotBlocked(bundle);
    let sent = 0;
    for (const row of live) {
      try {
        if ((await this.deliver(store, row, bundle)).status === "sent") sent += 1;
      } catch {
        // one bad row must not stop the batch; a row left in 'sending' is failed as 'interrupted' later
      }
    }
    return sent;
  }

  /**
   * POST cumulative counters for today and yesterday (counts only, never a phone or name).
   * Throttled to once per 15 minutes unless {force:true}. Returns rows reported (0 if throttled,
   * nothing to report, or Anril unreachable/rate-limited; counters are cumulative so the next call catches up).
   * A 422 (e.g. unknown_template) is logged and skipped so a bad row never blocks reporting.
   */
  async reportUsage(options: { force?: boolean } = {}): Promise<number> {
    const { store } = await this.ready();
    const now = this.clock();
    if (!options.force && (await this.usageThrottled(store, now))) return 0;
    const rows = await this.usageRows(store, now);
    if (!rows.length) return 0;
    let accepted = 0;
    for (let start = 0; start < rows.length; start += MAX_USAGE_ROWS) {
      const batch = rows.slice(start, start + MAX_USAGE_ROWS);
      const outcome = await this.postUsage(batch);
      if (outcome === "retry") return 0; // 429 / 5xx / network: keep the counters, no throttle, retry next call
      if (outcome === "ok") accepted += batch.length;
    }
    await store.setMeta(LAST_USAGE_KEY, iso(now));
    return accepted;
  }

  async close(): Promise<void> {
    if (!this.storeReady) return;
    const { store } = await this.storeReady;
    await store.close();
  }

  // ------------------------------------------------------------ internals

  private ready(): Promise<{ store: Store; bundles: BundleManager }> {
    this.storeReady ??= openStore(this.storeSpec).then((store) => ({
      store,
      bundles: new BundleManager(this.#licenseKey, this.publicKey, this.baseUrl, store, this.fetchFn, this.clock),
    }));
    return this.storeReady;
  }

  private async skip(
    store: Store, phone: string, event: string, templateId: string | null, reason: string, now: Date,
  ): Promise<SendResult> {
    await store.insertSend({
      phone, event, template_id: templateId, status: "skipped", reason, created_at: iso(now),
    });
    return { status: "skipped", reason };
  }

  /**
   * Anril is unreachable and no verified bundle is usable, so the rule is unknown: queue the send;
   * runDue looks the rule up once a bundle is available.
   */
  private async parkForRetry(
    store: Store, phone: string, event: string, input: TrackInput, now: Date,
  ): Promise<SendResult> {
    await store.insertSend(queueRow(phone, event, null, input, new Date(now.getTime() + RETRY_DELAY_MS), now));
    return { status: "queued", reason: "anril_unreachable" };
  }

  private isStale(row: StoredSend, now: Date): boolean {
    const created = Date.parse(row.created_at);
    return !Number.isNaN(created) && now.getTime() - created >= RETRY_WINDOW_MS;
  }

  /** Fail a queued row that has been retrying for RETRY_WINDOW. True when it was failed. */
  private async giveUpIfStale(store: Store, row: StoredSend, now: Date): Promise<boolean> {
    if (!this.isStale(row, now)) return false;
    await this.countFailed(store, row);
    await this.finish(store, row.id, "failed", `gave_up: ${row.reason || "anril_unreachable"}`);
    return true;
  }

  private async countFailed(store: Store, row: StoredSend): Promise<void> {
    // a row parked before any rule was known has no template to count against
    if (row.template_id) await store.bumpCounter(utcDay(this.clock()), row.event, row.template_id, 0, 1);
  }

  private async finish(
    store: Store, id: string, status: SendResult["status"], reason?: string,
  ): Promise<SendResult> {
    await store.finishSend(id, status, reason ?? null, status === "sent" ? this.clock() : null);
    return { status, ...(reason ? { reason } : {}) };
  }

  /**
   * Claim queued -> sending (so two runs never double-send), then send once. Only a send that provably
   * never reached Meta (connection failure, 429, 503) goes back to 'queued' for runDue.
   */
  private async deliver(store: Store, row: StoredSend, bundle: Bundle): Promise<SendResult> {
    if (!(await store.claimSend(row.id, this.clock()))) return { status: "skipped", reason: "already_claimed" };
    const rule = ruleFor(bundle, row.event);
    if (!rule) return this.finish(store, row.id, "skipped", "rule_removed_or_off");
    const template = templateFor(bundle, rule.template_id);
    if (!template) return this.finish(store, row.id, "failed", "template_not_approved");
    const ctx = buildContext(row.name, row.phone, row.extra, null);
    const components = buildComponents(template, rule as unknown as JsonRecord, ctx);
    const body = templateBody(row.phone, template.name, template.language || "en", components);
    const outcome = await sendTemplate(this.fetchFn, this.graphVersion, this.phoneNumberId, this.#metaToken, body);
    const gaveUp = !outcome.ok && outcome.retryable === true && this.isStale(row, this.clock());
    if (outcome.retryable && !gaveUp) return this.requeue(store, row, outcome);
    await store.bumpCounter(utcDay(this.clock()), row.event, rule.template_id, outcome.ok ? 1 : 0, outcome.ok ? 0 : 1);
    const reason = gaveUp ? `gave_up: ${outcome.reason ?? ""}` : outcome.reason;
    const result = await this.finish(store, row.id, outcome.ok ? "sent" : "failed", reason);
    return outcome.messageId ? { ...result, messageId: outcome.messageId } : result;
  }

  private async requeue(store: Store, row: StoredSend, outcome: MetaOutcome): Promise<SendResult> {
    await store.retrySend(row.id, new Date(this.clock().getTime() + RETRY_DELAY_MS), outcome.reason ?? null);
    return { status: "queued", ...(outcome.reason ? { reason: outcome.reason } : {}) };
  }

  private async usageThrottled(store: Store, now: Date): Promise<boolean> {
    const last = await store.getMeta(LAST_USAGE_KEY);
    if (!last) return false;
    const lastMs = Date.parse(last);
    return !Number.isNaN(lastMs) && now.getTime() - lastMs < USAGE_INTERVAL_MS;
  }

  private async usageRows(store: Store, now: Date): Promise<UsageRow[]> {
    const days = [utcDay(now), utcDay(new Date(now.getTime() - DAY_MS))];
    const counters: CounterRow[] = await store.counters(days);
    return counters.map((r) => ({
      day: r.day, event: r.event, template_id: r.template_id, sent: r.sent, failed: r.failed,
    }));
  }

  private async postUsage(rows: UsageRow[]): Promise<UsageOutcome> {
    let resp: Response;
    try {
      resp = await this.fetchFn(this.baseUrl + USAGE_PATH, {
        method: "POST",
        headers: { ...anrilHeaders(this.#licenseKey), "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
        signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
      });
    } catch {
      return "retry";
    }
    if (LICENSE_STATUSES.includes(resp.status)) throw await licenseErrorFor(resp);
    if (resp.status === 200) return "ok";
    if (resp.status === 422) {
      // a bad row (e.g. unknown_template) must not wedge reporting forever: log the code only, move on
      console.warn(`anril usage report rejected: ${await errorCodeOf(resp)}`);
      return "rejected";
    }
    return "retry";
  }
}

async function errorCodeOf(resp: Response): Promise<string> {
  try {
    const code = ((await resp.json()) as { code?: unknown } | null)?.code;
    if (typeof code === "string" && /^[a-z_]{1,64}$/.test(code)) return code;
  } catch {
    // fall through
  }
  return "HTTP 422";
}

function queueRow(
  phone: string, event: string, templateId: string | null, input: TrackInput, sendAt: Date, now: Date,
): SendRow {
  const ctx = buildContext(input.name, phone, input.extra, input.pageUrl);
  return {
    phone, event, template_id: templateId, status: "queued",
    send_at: iso(sendAt), created_at: iso(now),
    name: (input.name ?? "").trim() || null, extra: ctx.extra,
  };
}
