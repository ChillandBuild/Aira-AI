import { chmodSync, mkdtempSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnrilPrivateSend } from "../src/client.js";
import { BundleUnavailable, LicenseError } from "../src/errors.js";
import { SqliteStore } from "../src/store.js";
import {
  BASE, FakeClock, LICENSE_KEY, META_TOKEN, bundleData, envelope, json, makeKeys, mockFetch, type Call,
} from "./helpers.js";

const T0 = new Date("2026-10-07T10:00:00.000Z");
const MIN = 60_000;
const PHONE_ID = "109876543210";
const META_URL = `https://graph.facebook.com/v21.0/${PHONE_ID}/messages`;

const open: AnrilPrivateSend[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  while (open.length) await open.pop()!.close();
});

/** Flip these mid-test to make Meta or Anril unreachable. */
interface Control {
  metaDown: "no" | "connect" | "read-timeout" | 503;
  bundleDown: boolean;
}

function build(opts: { metaStatus?: number; usageStatus?: number; usageBody?: object; bundle?: object } = {}) {
  const keys = makeKeys();
  const clock = new FakeClock(T0);
  const control: Control = { metaDown: "no", bundleDown: false };
  let metaCount = 0;
  const { fn, calls } = mockFetch({
    bundle: () => (control.bundleDown ? json(503, {}) : json(200, envelope(keys, opts.bundle ?? bundleData(clock.read())))),
    usage: () => json(opts.usageStatus ?? 200, opts.usageBody ?? { ok: true, accepted: 1 }),
    meta: () => {
      if (control.metaDown === "connect") throw Object.assign(new TypeError("fetch failed"), { cause: { code: "ECONNREFUSED" } });
      if (control.metaDown === "read-timeout") throw Object.assign(new Error("timed out"), { name: "TimeoutError" });
      if (control.metaDown === 503) return json(503, {});
      metaCount += 1;
      return opts.metaStatus && opts.metaStatus >= 400
        ? json(opts.metaStatus, { error: { code: 131047, message: "Re-engagement message" } })
        : json(200, { messages: [{ id: `wamid.${metaCount}` }] });
    },
  });
  const anril = new AnrilPrivateSend({
    licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, anrilPublicKey: keys.publicB64,
    store: "sqlite::memory:", anrilBaseUrl: BASE, fetch: fn, clock: clock.read,
  });
  open.push(anril);
  const metaCalls = (): Call[] => calls.filter((c) => c.url.startsWith("https://graph.facebook.com"));
  const usageCalls = (): Call[] => calls.filter((c) => c.url.includes("/usage"));
  return { anril, clock, calls, metaCalls, usageCalls, control };
}

describe("track: immediate send", () => {
  it("sends once with the exact Meta POST body the backend builds", async () => {
    const { anril, metaCalls } = build();
    const res = await anril.track("purchase", { phone: "98765 43210", name: "Ravi Kumar" });
    expect(res).toEqual({ status: "sent", messageId: "wamid.1" });
    const [call] = metaCalls();
    expect(call!.url).toBe(META_URL);
    expect(call!.method).toBe("POST");
    expect(call!.headers.Authorization).toBe(`Bearer ${META_TOKEN}`);
    expect(JSON.parse(call!.body!)).toEqual({
      messaging_product: "whatsapp",
      to: "+919876543210",
      type: "template",
      template: {
        name: "loan_ready",
        language: { code: "en" },
        components: [{ type: "body", parameters: [{ type: "text", text: "Ravi" }] }],
      },
    });
  });

  it("uses extra and pageUrl in the context", async () => {
    const bundle = bundleData(T0, {
      templates: [{ id: "tp1", name: "t", language: "en", body_text: "{{1}} {{2}}", buttons: [] }],
      rules: [{
        id: "r1", event: "purchased", template_id: "tp1", enabled: true, button_param: null,
        variables: [{ source: "extra", key: "Plan", fallback: "x" }, { source: "page_url", fallback: "-" }],
      }],
    });
    const { anril, metaCalls } = build({ bundle });
    await anril.track("purchased", { phone: "9876543210", extra: { Plan: "Gold" }, pageUrl: "https://shop.example.com/p" });
    const body = JSON.parse(metaCalls()[0]!.body!);
    expect(body.template.components[0].parameters.map((p: { text: string }) => p.text)).toEqual(["Gold", "https://shop.example.com/p"]);
  });

  it("rejects an unknown event and an invalid phone", async () => {
    const { anril } = build();
    await expect(anril.track("non-sense!", { phone: "9876543210" })).rejects.toThrow(/unknown event/);
    await expect(anril.track("purchased", { phone: "abc" })).rejects.toThrow(/invalid phone/);
  });

  it("records a Meta failure as failed with the reason, and does not retry", async () => {
    const { anril, metaCalls, clock } = build({ metaStatus: 400 });
    const res = await anril.track("purchased", { phone: "9876543210" });
    expect(res).toEqual({ status: "failed", reason: "meta_131047: Re-engagement message" });
    clock.advance(30 * MIN);
    expect(await anril.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(1);
  });

  it("skips with no_rule when the event has no rule", async () => {
    const { anril, metaCalls } = build();
    expect(await anril.track("interested", { phone: "9876543210" })).toEqual({ status: "skipped", reason: "no_rule" });
    expect(metaCalls()).toHaveLength(0);
  });
});

describe("instant, no checks", () => {
  it("the same event twice sends twice", async () => {
    const { anril, clock, metaCalls } = build();
    expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    expect((await anril.track("purchased", { phone: "+91 98765 43210" })).status).toBe("sent");
    expect(metaCalls()).toHaveLength(2);
    clock.advance(25 * 60 * MIN);
    expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    expect(metaCalls()).toHaveLength(3);
  });

  it("every event sends at once (signed_up used to be a 30 minute delayed rule)", async () => {
    const { anril, metaCalls } = build();
    const res = await anril.track("signed_up", { phone: "9876543210", name: "Asha" });
    expect(res.status).toBe("sent");
    expect(JSON.parse(metaCalls()[0]!.body!).template.components[0].parameters[0].text).toBe("Asha");
  });

  it("a matched event is on the wire before any runDue call", async () => {
    const { anril, metaCalls } = build();
    await anril.track("purchased", { phone: "9876543210" });
    expect(metaCalls()).toHaveLength(1);
    expect(await anril.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(1);
  });

  it("has no optOut API", () => {
    const { anril } = build();
    expect((anril as unknown as Record<string, unknown>).optOut).toBeUndefined();
  });
});

describe("retry path (Meta or Anril unreachable)", () => {

  it("a refused connection to Meta queues the send; runDue sends it a minute later, once", async () => {
    const { anril, clock, metaCalls, control } = build();
    control.metaDown = "connect";
    expect(await anril.track("purchased", { phone: "9876543210", name: "Asha" })).toEqual({
      status: "queued", reason: "network_error: TypeError",
    });
    control.metaDown = "no";
    expect(await anril.runDue()).toBe(0); // not due for a minute
    clock.advance(MIN);
    expect(await anril.runDue()).toBe(1);
    expect(await anril.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(2); // the refused attempt, then the one retry
    expect(JSON.parse(metaCalls()[1]!.body!).template.components[0].parameters[0].text).toBe("Asha");
  });

  it("Meta 503 is retried", async () => {
    const { anril, clock, control } = build();
    control.metaDown = 503;
    expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("queued");
    control.metaDown = "no";
    clock.advance(MIN);
    expect(await anril.runDue()).toBe(1);
  });

  it("a Meta rejection (400) and a read timeout are final, never retried", async () => {
    const rejected = build({ metaStatus: 400 });
    expect((await rejected.anril.track("purchased", { phone: "9876543210" })).status).toBe("failed");
    rejected.clock.advance(5 * MIN);
    expect(await rejected.anril.runDue()).toBe(0);
    expect(rejected.metaCalls()).toHaveLength(1);

    const slow = build();
    slow.control.metaDown = "read-timeout";
    expect((await slow.anril.track("purchased", { phone: "9876543210" })).status).toBe("failed");
    slow.control.metaDown = "no";
    slow.clock.advance(5 * MIN);
    expect(await slow.anril.runDue()).toBe(0);
    expect(slow.metaCalls()).toHaveLength(1); // the one attempt; never repeated
  });

  it("gives up an hour after the event and counts one failure", async () => {
    const { anril, clock, control, usageCalls } = build();
    control.metaDown = "connect";
    await anril.track("purchased", { phone: "9876543210" });
    for (let i = 0; i < 59; i += 1) {
      clock.advance(MIN);
      expect(await anril.runDue()).toBe(0);
    }
    clock.advance(MIN);
    expect(await anril.runDue()).toBe(0);
    control.metaDown = "no";
    clock.advance(5 * MIN);
    expect(await anril.runDue()).toBe(0); // given up: not sent late
    await anril.reportUsage({ force: true });
    expect(JSON.parse(usageCalls()[0]!.body!).rows).toEqual([
      { day: "2026-10-07", event: "purchased", template_id: "tp1", sent: 0, failed: 1 },
    ]);
  });

  it("Anril unreachable with no usable bundle parks the send; runDue sends once a bundle is back", async () => {
    const { anril, clock, metaCalls, control } = build();
    control.bundleDown = true;
    expect(await anril.track("purchased", { phone: "9876543210", name: "Asha" })).toEqual({
      status: "queued", reason: "anril_unreachable",
    });
    expect(metaCalls()).toHaveLength(0);
    clock.advance(MIN);
    await expect(anril.runDue()).rejects.toBeInstanceOf(BundleUnavailable); // still down; row stays queued
    control.bundleDown = false;
    expect(await anril.runDue()).toBe(1);
    expect(JSON.parse(metaCalls()[0]!.body!).template.components[0].parameters[0].text).toBe("Asha");
  });

  it("a parked send gives up after an hour even while Anril is down", async () => {
    const { anril, clock, metaCalls, control } = build();
    control.bundleDown = true;
    await anril.track("purchased", { phone: "9876543210" });
    clock.advance(61 * MIN);
    expect(await anril.runDue()).toBe(0); // no bundle needed to give up
    control.bundleDown = false;
    clock.advance(MIN);
    expect(await anril.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(0);
  });
});

describe("old store files", () => {
  it("a store with opt_outs and dedupe history still opens, and both are ignored", async () => {
    const path = join(mkdtempSync(join(tmpdir(), "aps-")), "old.db");
    const { default: Database } = await import("better-sqlite3");
    const old = new Database(path);
    old.exec(`
      CREATE TABLE sends (id TEXT PRIMARY KEY, phone TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT,
        status TEXT NOT NULL, reason TEXT, send_at TEXT, sent_at TEXT, created_at TEXT NOT NULL, name TEXT,
        extra TEXT, claimed_at TEXT);
      CREATE INDEX sends_dedupe ON sends (phone, event, created_at);
      CREATE INDEX sends_due ON sends (status, send_at);
      CREATE TABLE opt_outs (phone TEXT PRIMARY KEY);
      CREATE TABLE counters (day TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT NOT NULL,
        sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, event, template_id));
      CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      INSERT INTO opt_outs (phone) VALUES ('+919876543210');
      INSERT INTO sends (id, phone, event, template_id, status, created_at)
        VALUES ('old', '+919876543210', 'purchased', 'tp1', 'sent', '2026-10-07T10:00:00.000000Z');
    `);
    old.close();
    const keys = makeKeys();
    const { fn, calls } = mockFetch({
      bundle: () => json(200, envelope(keys, bundleData(T0))),
      meta: () => json(200, { messages: [{ id: "wamid.old" }] }),
    });
    const anril = new AnrilPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, anrilPublicKey: keys.publicB64,
      store: `sqlite:${path}`, anrilBaseUrl: BASE, fetch: fn, clock: () => new Date(T0),
    });
    open.push(anril);
    expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    expect(calls.filter((c) => c.url.startsWith("https://graph.facebook.com"))).toHaveLength(1);
  });
});

describe("old bundles (quiet hours / delay)", () => {
  const oldQuiet = { start: "00:00", end: "23:59", tz: "Asia/Kolkata", categories: ["UTILITY", "MARKETING"] };

  it("an old bundle with quiet_hours and delay_minutes is accepted and ignored: sends at once", async () => {
    const data = bundleData(T0);
    const old = {
      ...data,
      quiet_hours: oldQuiet,
      rules: data.rules.map((r) => ({ ...r, delay_minutes: 30 })),
    };
    const { anril, metaCalls } = build({ bundle: old });
    expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    expect((await anril.track("signed_up", { phone: "9123456789" })).status).toBe("sent");
    expect(metaCalls()).toHaveLength(2);
  });

  for (const quiet of ["garbage", { start: "25:99", tz: "Nowhere/Land" }, ["x"]]) {
    it(`a malformed quiet_hours (${JSON.stringify(quiet)}) no longer rejects the bundle`, async () => {
      const { anril } = build({ bundle: { ...bundleData(T0), quiet_hours: quiet } });
      expect((await anril.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    });
  }
});

describe("stuck sending rows", () => {
  it("rows stuck in sending > 15 min become failed/interrupted and are never retried", async () => {
    const store = await SqliteStore.open(":memory:");
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    const { fn, calls } = mockFetch({
      bundle: () => json(200, envelope(keys, bundleData(clock.read()))),
      meta: () => json(200, { messages: [{ id: "x" }] }),
    });
    const anril = new AnrilPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, anrilPublicKey: keys.publicB64,
      store, anrilBaseUrl: BASE, fetch: fn, clock: clock.read,
    });
    const id = await store.insertSend({
      phone: "+919876543210", event: "purchased", template_id: "tp1", status: "queued",
      send_at: new Date(T0.getTime() - MIN).toISOString().replace("Z", "000Z"), created_at: T0.toISOString().replace("Z", "000Z"),
    });
    expect(await store.claimSend(id, T0)).toBe(true); // crash right after claiming
    clock.advance(16 * MIN);
    expect(await anril.runDue()).toBe(0);
    expect(calls.filter((c) => c.url.includes("graph.facebook"))).toHaveLength(0);
    expect(await store.failStuck(new Date(clock.now.getTime() + 999 * MIN))).toBe(0); // already failed
    const stuck = await store.dueSends(new Date(clock.now.getTime() + 999 * MIN), 10);
    expect(stuck).toHaveLength(0);
    await anril.close();
  });

  it("claimSend is atomic: a second claim of the same row fails", async () => {
    const store = await SqliteStore.open(":memory:");
    const id = await store.insertSend({
      phone: "+919876543210", event: "purchased", template_id: "tp1", status: "queued",
      send_at: "2026-10-07T10:00:00.000000Z", created_at: "2026-10-07T10:00:00.000000Z",
    });
    expect(await store.claimSend(id, T0)).toBe(true);
    expect(await store.claimSend(id, T0)).toBe(false);
    await store.close();
  });
});

describe("usage reporting", () => {
  it("posts counters only: the body has no phone and no name (exact JSON)", async () => {
    const { anril, usageCalls } = build();
    await anril.track("purchased", { phone: "9876543210", name: "Ravi Kumar" });
    await anril.track("purchased", { phone: "9876543211", name: "Asha" });
    expect(await anril.reportUsage()).toBe(1);
    const [call] = usageCalls();
    expect(call!.url).toBe(`${BASE}/api/v1/private-send/usage`);
    expect(call!.headers.Authorization).toBe(`Bearer ${LICENSE_KEY}`);
    expect(call!.headers["X-Anril-Plugin"]).toMatch(/^node\//);
    expect(call!.body).toBe('{"rows":[{"day":"2026-10-07","event":"purchased","template_id":"tp1","sent":2,"failed":0}]}');
    expect(call!.body).not.toMatch(/Ravi|Asha|98765|\+91/);
  });

  it("counts failures too, and reports today and yesterday", async () => {
    const { anril, clock, usageCalls } = build({ metaStatus: 400 });
    await anril.track("purchased", { phone: "9876543210" });
    clock.advance(24 * 60 * MIN + MIN);
    await anril.track("purchased", { phone: "9876543210" });
    await anril.reportUsage();
    expect(JSON.parse(usageCalls()[0]!.body!).rows).toEqual([
      { day: "2026-10-07", event: "purchased", template_id: "tp1", sent: 0, failed: 1 },
      { day: "2026-10-08", event: "purchased", template_id: "tp1", sent: 0, failed: 1 },
    ]);
  });

  it("throttles to once per 15 minutes unless forced", async () => {
    const { anril, clock, usageCalls } = build();
    await anril.track("purchased", { phone: "9876543210" });
    expect(await anril.reportUsage()).toBe(1);
    clock.advance(10 * MIN);
    expect(await anril.reportUsage()).toBe(0);
    expect(await anril.reportUsage({ force: true })).toBe(1);
    clock.advance(16 * MIN);
    expect(await anril.reportUsage()).toBe(1);
    expect(usageCalls()).toHaveLength(3);
  });

  it("reports nothing when there is nothing to report, and retries after an Anril error", async () => {
    const { anril, usageCalls } = build({ usageStatus: 503 });
    expect(await anril.reportUsage()).toBe(0);
    expect(usageCalls()).toHaveLength(0);
    await anril.track("purchased", { phone: "9876543210" });
    expect(await anril.reportUsage()).toBe(0);
    expect(await anril.reportUsage()).toBe(0); // failed report does not start the throttle window
    expect(usageCalls()).toHaveLength(2);
  });

  it("a 401 on usage raises LicenseError", async () => {
    const { anril } = build({ usageStatus: 401 });
    await anril.track("purchased", { phone: "9876543210" });
    await expect(anril.reportUsage()).rejects.toBeInstanceOf(LicenseError);
  });
});

describe("secrets", () => {
  it("never shows the license key or Meta token when printed", () => {
    const { anril } = build();
    const shown = `${anril} ${JSON.stringify(anril)}`;
    expect(shown).not.toContain(LICENSE_KEY);
    expect(shown).not.toContain(META_TOKEN);
  });

  it("only talks to the Anril host and graph.facebook.com", async () => {
    const { anril, calls } = build();
    await anril.track("purchased", { phone: "9876543210" });
    await anril.reportUsage();
    for (const c of calls) expect(new URL(c.url).host).toMatch(/^(anril\.test|graph\.facebook\.com)$/);
  });
});

describe("usage error handling", () => {
  for (const status of [429, 500, 502, 503]) {
    it(`${status} keeps the counters and does not start the throttle`, async () => {
      const { anril, usageCalls } = build({ usageStatus: status });
      await anril.track("purchased", { phone: "9876543210" });
      expect(await anril.reportUsage()).toBe(0);
      expect(await anril.reportUsage()).toBe(0); // no throttle: it tried again at once
      expect(usageCalls()).toHaveLength(2);
      expect(JSON.parse(usageCalls()[1]!.body!).rows[0].sent).toBe(1);
    });
  }

  it("422 logs the error code only, does not throw, and does not wedge reporting", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { anril, clock, usageCalls } = build({
      usageStatus: 422, usageBody: { error: "template tp1 is not yours", code: "unknown_template" },
    });
    await anril.track("purchased", { phone: "9876543210", name: "Ravi" });
    expect(await anril.reportUsage()).toBe(0);
    const logged = warn.mock.calls.map((c) => c.join(" ")).join(" ");
    expect(logged).toContain("unknown_template");
    expect(logged).not.toMatch(/tp1|9876543210|Ravi|not yours/);
    clock.advance(MIN);
    expect(await anril.reportUsage()).toBe(0); // throttled, not an error loop
    expect(usageCalls()).toHaveLength(1);
  });
});

describe("constructor validation", () => {
  const base = { licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: "123", anrilPublicKey: makeKeys().publicB64, store: "sqlite::memory:" };
  const make = (o: object) => new AnrilPrivateSend({ ...base, ...o });

  for (const url of [
    "http://anril.example.com", "ftp://anril.example.com", "anril.example.com", "https://", "",
    "http://localhost.evil.com", "http://localhost@evil.com", "http://127.0.0.1.evil.com",
  ]) {
    it(`rejects anrilBaseUrl ${JSON.stringify(url)}`, () => {
      expect(() => make({ anrilBaseUrl: url })).toThrow(TypeError);
    });
  }

  for (const url of ["https://anril.example.com", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost"]) {
    it(`accepts anrilBaseUrl ${url}`, () => {
      expect(() => make({ anrilBaseUrl: url })).not.toThrow();
    });
  }

  for (const id of ["", "12a", "../x", "123/messages", "12 3", "123\n", "v21.0"]) {
    it(`rejects phoneNumberId ${JSON.stringify(id)}`, () => {
      expect(() => make({ phoneNumberId: id })).toThrow();
    });
  }

  for (const version of ["21.0", "v21", "v21.0.1", "v21.0/../x", "V21.0", "v21.0\n", "", "vx.y"]) {
    it(`rejects graphVersion ${JSON.stringify(version)}`, () => {
      expect(() => make({ graphVersion: version })).toThrow(TypeError);
    });
  }

  it("accepts graphVersion v22.1", () => {
    expect(() => make({ graphVersion: "v22.1" })).not.toThrow();
  });
});

describe.skipIf(process.platform === "win32")("sqlite file permissions", () => {
  it("a new db file and its WAL sidecars are owner-only", async () => {
    const dir = mkdtempSync(join(tmpdir(), "aps-"));
    const path = join(dir, "new.db");
    const store = await SqliteStore.open(path);
    await store.setMeta("k", "v");
    expect(statSync(path).mode & 0o777).toBe(0o600);
    for (const suffix of ["-wal", "-shm"]) {
      try {
        expect(statSync(path + suffix).mode & 0o777).toBe(0o600);
      } catch (err) {
        if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
      }
    }
    await store.close();
  });

  it("an existing db file keeps its permissions", async () => {
    const dir = mkdtempSync(join(tmpdir(), "aps-"));
    const path = join(dir, "old.db");
    await (await SqliteStore.open(path)).close();
    chmodSync(path, 0o640);
    await (await SqliteStore.open(path)).close();
    expect(statSync(path).mode & 0o777).toBe(0o640);
  });
});
