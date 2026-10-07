import { chmodSync, mkdtempSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiraPrivateSend } from "../src/client.js";
import { LicenseError } from "../src/errors.js";
import { SqliteStore } from "../src/store.js";
import {
  BASE, FakeClock, LICENSE_KEY, META_TOKEN, bundleData, envelope, json, makeKeys, mockFetch, type Call,
} from "./helpers.js";

const T0 = new Date("2026-10-07T10:00:00.000Z");
const MIN = 60_000;
const PHONE_ID = "109876543210";
const META_URL = `https://graph.facebook.com/v21.0/${PHONE_ID}/messages`;

const open: AiraPrivateSend[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  while (open.length) await open.pop()!.close();
});

function build(opts: { metaStatus?: number; usageStatus?: number; usageBody?: object; bundle?: object } = {}) {
  const keys = makeKeys();
  const clock = new FakeClock(T0);
  let metaCount = 0;
  const { fn, calls } = mockFetch({
    bundle: () => json(200, envelope(keys, opts.bundle ?? bundleData(clock.read()))),
    usage: () => json(opts.usageStatus ?? 200, opts.usageBody ?? { ok: true, accepted: 1 }),
    meta: () => {
      metaCount += 1;
      return opts.metaStatus && opts.metaStatus >= 400
        ? json(opts.metaStatus, { error: { code: 131047, message: "Re-engagement message" } })
        : json(200, { messages: [{ id: `wamid.${metaCount}` }] });
    },
  });
  const aira = new AiraPrivateSend({
    licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, airaPublicKey: keys.publicB64,
    store: "sqlite::memory:", airaBaseUrl: BASE, fetch: fn, clock: clock.read,
  });
  open.push(aira);
  const metaCalls = (): Call[] => calls.filter((c) => c.url.startsWith("https://graph.facebook.com"));
  const usageCalls = (): Call[] => calls.filter((c) => c.url.includes("/usage"));
  return { aira, clock, calls, metaCalls, usageCalls };
}

describe("track: immediate send", () => {
  it("sends once with the exact Meta POST body the backend builds", async () => {
    const { aira, metaCalls } = build();
    const res = await aira.track("purchase", { phone: "98765 43210", name: "Ravi Kumar" });
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
        id: "r1", event: "purchased", template_id: "tp1", delay_minutes: 0, enabled: true, button_param: null,
        variables: [{ source: "extra", key: "Plan", fallback: "x" }, { source: "page_url", fallback: "-" }],
      }],
    });
    const { aira, metaCalls } = build({ bundle });
    await aira.track("purchased", { phone: "9876543210", extra: { Plan: "Gold" }, pageUrl: "https://shop.example.com/p" });
    const body = JSON.parse(metaCalls()[0]!.body!);
    expect(body.template.components[0].parameters.map((p: { text: string }) => p.text)).toEqual(["Gold", "https://shop.example.com/p"]);
  });

  it("rejects an unknown event and an invalid phone", async () => {
    const { aira } = build();
    await expect(aira.track("nonsense", { phone: "9876543210" })).rejects.toThrow(/unknown event/);
    await expect(aira.track("purchased", { phone: "abc" })).rejects.toThrow(/invalid phone/);
  });

  it("records a Meta failure as failed with the reason, and does not retry", async () => {
    const { aira, metaCalls, clock } = build({ metaStatus: 400 });
    const res = await aira.track("purchased", { phone: "9876543210" });
    expect(res).toEqual({ status: "failed", reason: "meta_131047: Re-engagement message" });
    clock.advance(30 * MIN);
    expect(await aira.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(1);
  });

  it("skips with no_rule when the event has no rule", async () => {
    const { aira, metaCalls } = build();
    expect(await aira.track("interested", { phone: "9876543210" })).toEqual({ status: "skipped", reason: "no_rule" });
    expect(metaCalls()).toHaveLength(0);
  });
});

describe("dedupe and opt-out", () => {
  it("skips the same phone+event within 24h, allows again after", async () => {
    const { aira, clock, metaCalls } = build();
    await aira.track("purchased", { phone: "9876543210" });
    clock.advance(23 * 60 * MIN);
    expect(await aira.track("purchased", { phone: "+91 98765 43210" })).toEqual({ status: "skipped", reason: "duplicate" });
    clock.advance(61 * MIN);
    expect((await aira.track("purchased", { phone: "9876543210" })).status).toBe("sent");
    expect(metaCalls()).toHaveLength(2);
  });

  it("does not dedupe a different phone", async () => {
    const { aira } = build();
    await aira.track("purchased", { phone: "9876543210" });
    expect((await aira.track("purchased", { phone: "9876543211" })).status).toBe("sent");
  });

  it("opted-out numbers are skipped, in any phone spelling", async () => {
    const { aira, metaCalls } = build();
    await aira.optOut("98765-43210");
    expect(await aira.track("purchased", { phone: "+919876543210" })).toEqual({ status: "skipped", reason: "opted_out" });
    expect(metaCalls()).toHaveLength(0);
    await expect(aira.optOut("abc")).rejects.toThrow(/invalid phone/);
  });

  it("an opt-out added while a message is queued stops it", async () => {
    const { aira, clock, metaCalls } = build();
    expect(await aira.track("signed_up", { phone: "9876543210" })).toEqual({ status: "queued" });
    await aira.optOut("9876543210");
    clock.advance(31 * MIN);
    expect(await aira.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(0);
  });
});

describe("delayed queue", () => {
  it("queues a delayed rule and runDue sends it only once the delay is up", async () => {
    const { aira, clock, metaCalls } = build();
    expect(await aira.track("signed_up", { phone: "9876543210", name: "Asha" })).toEqual({ status: "queued" });
    expect(metaCalls()).toHaveLength(0);
    clock.advance(29 * MIN);
    expect(await aira.runDue()).toBe(0);
    clock.advance(2 * MIN);
    expect(await aira.runDue()).toBe(1);
    expect(await aira.runDue()).toBe(0);
    expect(metaCalls()).toHaveLength(1);
    expect(JSON.parse(metaCalls()[0]!.body!).template.components[0].parameters[0].text).toBe("Asha");
  });

  it("a queued message also blocks a duplicate track", async () => {
    const { aira } = build();
    await aira.track("signed_up", { phone: "9876543210" });
    expect(await aira.track("signed_up", { phone: "9876543210" })).toEqual({ status: "skipped", reason: "duplicate" });
  });
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
    const aira = new AiraPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, airaPublicKey: keys.publicB64,
      store, airaBaseUrl: BASE, fetch: fn, clock: clock.read,
    });
    const id = await store.insertSend({
      phone: "+919876543210", event: "purchased", template_id: "tp1", status: "queued",
      send_at: new Date(T0.getTime() - MIN).toISOString().replace("Z", "000Z"), created_at: T0.toISOString().replace("Z", "000Z"),
    });
    expect(await store.claimSend(id, T0)).toBe(true); // crash right after claiming
    clock.advance(16 * MIN);
    expect(await aira.runDue()).toBe(0);
    expect(calls.filter((c) => c.url.includes("graph.facebook"))).toHaveLength(0);
    expect(await store.failStuck(new Date(clock.now.getTime() + 999 * MIN))).toBe(0); // already failed
    const stuck = await store.dueSends(new Date(clock.now.getTime() + 999 * MIN), 10);
    expect(stuck).toHaveLength(0);
    await aira.close();
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
    const { aira, usageCalls } = build();
    await aira.track("purchased", { phone: "9876543210", name: "Ravi Kumar" });
    await aira.track("purchased", { phone: "9876543211", name: "Asha" });
    expect(await aira.reportUsage()).toBe(1);
    const [call] = usageCalls();
    expect(call!.url).toBe(`${BASE}/api/v1/private-send/usage`);
    expect(call!.headers.Authorization).toBe(`Bearer ${LICENSE_KEY}`);
    expect(call!.headers["X-Aira-Plugin"]).toMatch(/^node\//);
    expect(call!.body).toBe('{"rows":[{"day":"2026-10-07","event":"purchased","template_id":"tp1","sent":2,"failed":0}]}');
    expect(call!.body).not.toMatch(/Ravi|Asha|98765|\+91/);
  });

  it("counts failures too, and reports today and yesterday", async () => {
    const { aira, clock, usageCalls } = build({ metaStatus: 400 });
    await aira.track("purchased", { phone: "9876543210" });
    clock.advance(24 * 60 * MIN + MIN);
    await aira.track("purchased", { phone: "9876543210" });
    await aira.reportUsage();
    expect(JSON.parse(usageCalls()[0]!.body!).rows).toEqual([
      { day: "2026-10-07", event: "purchased", template_id: "tp1", sent: 0, failed: 1 },
      { day: "2026-10-08", event: "purchased", template_id: "tp1", sent: 0, failed: 1 },
    ]);
  });

  it("throttles to once per 15 minutes unless forced", async () => {
    const { aira, clock, usageCalls } = build();
    await aira.track("purchased", { phone: "9876543210" });
    expect(await aira.reportUsage()).toBe(1);
    clock.advance(10 * MIN);
    expect(await aira.reportUsage()).toBe(0);
    expect(await aira.reportUsage({ force: true })).toBe(1);
    clock.advance(16 * MIN);
    expect(await aira.reportUsage()).toBe(1);
    expect(usageCalls()).toHaveLength(3);
  });

  it("reports nothing when there is nothing to report, and retries after an Aira error", async () => {
    const { aira, usageCalls } = build({ usageStatus: 503 });
    expect(await aira.reportUsage()).toBe(0);
    expect(usageCalls()).toHaveLength(0);
    await aira.track("purchased", { phone: "9876543210" });
    expect(await aira.reportUsage()).toBe(0);
    expect(await aira.reportUsage()).toBe(0); // failed report does not start the throttle window
    expect(usageCalls()).toHaveLength(2);
  });

  it("a 401 on usage raises LicenseError", async () => {
    const { aira } = build({ usageStatus: 401 });
    await aira.track("purchased", { phone: "9876543210" });
    await expect(aira.reportUsage()).rejects.toBeInstanceOf(LicenseError);
  });
});

describe("secrets", () => {
  it("never shows the license key or Meta token when printed", () => {
    const { aira } = build();
    const shown = `${aira} ${JSON.stringify(aira)}`;
    expect(shown).not.toContain(LICENSE_KEY);
    expect(shown).not.toContain(META_TOKEN);
  });

  it("only talks to the Aira host and graph.facebook.com", async () => {
    const { aira, calls } = build();
    await aira.track("purchased", { phone: "9876543210" });
    await aira.reportUsage();
    for (const c of calls) expect(new URL(c.url).host).toMatch(/^(aira\.test|graph\.facebook\.com)$/);
  });
});

describe("usage error handling", () => {
  for (const status of [429, 500, 502, 503]) {
    it(`${status} keeps the counters and does not start the throttle`, async () => {
      const { aira, usageCalls } = build({ usageStatus: status });
      await aira.track("purchased", { phone: "9876543210" });
      expect(await aira.reportUsage()).toBe(0);
      expect(await aira.reportUsage()).toBe(0); // no throttle: it tried again at once
      expect(usageCalls()).toHaveLength(2);
      expect(JSON.parse(usageCalls()[1]!.body!).rows[0].sent).toBe(1);
    });
  }

  it("422 logs the error code only, does not throw, and does not wedge reporting", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { aira, clock, usageCalls } = build({
      usageStatus: 422, usageBody: { error: "template tp1 is not yours", code: "unknown_template" },
    });
    await aira.track("purchased", { phone: "9876543210", name: "Ravi" });
    expect(await aira.reportUsage()).toBe(0);
    const logged = warn.mock.calls.map((c) => c.join(" ")).join(" ");
    expect(logged).toContain("unknown_template");
    expect(logged).not.toMatch(/tp1|9876543210|Ravi|not yours/);
    clock.advance(MIN);
    expect(await aira.reportUsage()).toBe(0); // throttled, not an error loop
    expect(usageCalls()).toHaveLength(1);
  });
});

describe("constructor validation", () => {
  const base = { licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: "123", airaPublicKey: makeKeys().publicB64, store: "sqlite::memory:" };
  const make = (o: object) => new AiraPrivateSend({ ...base, ...o });

  for (const url of [
    "http://aira.example.com", "ftp://aira.example.com", "aira.example.com", "https://", "",
    "http://localhost.evil.com", "http://localhost@evil.com", "http://127.0.0.1.evil.com",
  ]) {
    it(`rejects airaBaseUrl ${JSON.stringify(url)}`, () => {
      expect(() => make({ airaBaseUrl: url })).toThrow(TypeError);
    });
  }

  for (const url of ["https://aira.example.com", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost"]) {
    it(`accepts airaBaseUrl ${url}`, () => {
      expect(() => make({ airaBaseUrl: url })).not.toThrow();
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
    await store.addOptOut("+919876543210");
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
