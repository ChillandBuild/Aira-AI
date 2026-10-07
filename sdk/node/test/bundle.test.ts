import { describe, expect, it } from "vitest";
import { BundleManager, loadPublicKey, loadPublicKeys } from "../src/bundle.js";
import { BundleUnavailable, LicenseError, QuotaExceeded } from "../src/errors.js";
import { SqliteStore } from "../src/store.js";
import { AiraPrivateSend } from "../src/client.js";
import { BASE, FakeClock, LICENSE_KEY, META_TOKEN, bundleData, envelope, json, makeKeys, mockFetch } from "./helpers.js";

const T0 = new Date("2026-10-07T10:00:00.000Z");
const MIN = 60_000;
const HOUR = 60 * MIN;

async function setup(bundleHandler: Parameters<typeof mockFetch>[0]["bundle"], keys = makeKeys()) {
  const clock = new FakeClock(T0);
  const store = await SqliteStore.open(":memory:");
  const { fn, calls } = mockFetch({ bundle: bundleHandler });
  const manager = new BundleManager(LICENSE_KEY, loadPublicKey(keys.publicB64), BASE, store, fn, clock.read);
  return { clock, store, calls, manager, keys };
}

describe("bundle manager", () => {
  it("accepts a good signature and sends the plugin header + bearer key", async () => {
    const keys = makeKeys();
    const { manager, calls } = await setup(() => json(200, envelope(keys, bundleData(T0))), keys);
    const bundle = await manager.current();
    expect(bundle.data.rules).toHaveLength(2);
    expect(calls[0]!.url).toBe(`${BASE}/api/v1/private-send/bundle`);
    expect(calls[0]!.headers.Authorization).toBe(`Bearer ${LICENSE_KEY}`);
    expect(calls[0]!.headers["X-Aira-Plugin"]).toMatch(/^node\/\d+\.\d+\.\d+/);
  });

  it("treats a bad signature as a failed refresh and never uses the bundle", async () => {
    const wrong = makeKeys();
    const keys = makeKeys();
    const { manager } = await setup(() => json(200, envelope(wrong, bundleData(T0))), keys);
    await expect(manager.current()).rejects.toBeInstanceOf(BundleUnavailable);
  });

  it("rejects a tampered payload", async () => {
    const keys = makeKeys();
    const good = envelope(keys, bundleData(T0));
    const tampered = { ...good, payload: Buffer.from(JSON.stringify(bundleData(T0, { offline_grace_hours: 999 }))).toString("base64") };
    const { manager } = await setup(() => json(200, tampered), keys);
    await expect(manager.current()).rejects.toBeInstanceOf(BundleUnavailable);
  });

  it("rejects an already-expired bundle", async () => {
    const keys = makeKeys();
    const expired = bundleData(T0, { expires_at: new Date(T0.getTime() - MIN).toISOString() });
    const { manager } = await setup(() => json(200, envelope(keys, expired)), keys);
    await expect(manager.current()).rejects.toBeInstanceOf(BundleUnavailable);
  });

  it("caches for 5 minutes then refreshes", async () => {
    const keys = makeKeys();
    const { manager, calls, clock } = await setup(() => json(200, envelope(keys, bundleData(T0))), keys);
    await manager.current();
    clock.advance(4 * MIN);
    await manager.current();
    expect(calls).toHaveLength(1);
    clock.advance(2 * MIN);
    await manager.current();
    expect(calls).toHaveLength(2);
  });

  it("offline: keeps the last verified bundle until fetch time + grace hours, then refuses", async () => {
    const keys = makeKeys();
    let online = true;
    const { manager, clock } = await setup(
      () => (online ? json(200, envelope(keys, bundleData(T0))) : json(503, { code: "signing_not_configured" })), keys);
    await manager.current();
    online = false;
    clock.advance(5 * HOUR); // past expires_at (15 min) but inside the 6h grace
    expect((await manager.current()).data.tenant_id).toBe("t1");
    clock.advance(HOUR + MIN); // 6h01m after the last good fetch
    await expect(manager.current()).rejects.toBeInstanceOf(BundleUnavailable);
  });

  it("offline grace also covers network errors and 429", async () => {
    const keys = makeKeys();
    let mode: "ok" | "net" | "429" = "ok";
    const { manager, clock } = await setup(() => {
      if (mode === "net") throw new TypeError("fetch failed");
      return mode === "429" ? json(429, {}) : json(200, envelope(keys, bundleData(T0)));
    }, keys);
    await manager.current();
    clock.advance(10 * MIN);
    mode = "net";
    await expect(manager.current()).resolves.toBeDefined();
    mode = "429";
    clock.advance(MIN);
    await expect(manager.current()).resolves.toBeDefined();
  });

  it("restores a verified bundle from the store after a restart", async () => {
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    const store = await SqliteStore.open(":memory:");
    const ok = mockFetch({ bundle: () => json(200, envelope(keys, bundleData(T0))) });
    await new BundleManager(LICENSE_KEY, loadPublicKey(keys.publicB64), BASE, store, ok.fn, clock.read).current();
    clock.advance(10 * MIN);
    const down = mockFetch({ bundle: () => json(503, {}) });
    const restarted = new BundleManager(LICENSE_KEY, loadPublicKey(keys.publicB64), BASE, store, down.fn, clock.read);
    expect((await restarted.current()).data.tenant_id).toBe("t1");
  });

  for (const [status, code] of [[401, "invalid_key"], [401, "revoked_key"], [403, "feature_disabled"]] as const) {
    it(`${status} ${code} -> LicenseError and the cache is dropped`, async () => {
      const keys = makeKeys();
      let reject = false;
      const { manager, clock, store } = await setup(
        () => (reject ? json(status, { error: "no", code }) : json(200, envelope(keys, bundleData(T0)))), keys);
      await manager.current();
      expect(await store.getMeta("bundle")).not.toBeNull();
      reject = true;
      clock.advance(6 * MIN);
      await expect(manager.current()).rejects.toMatchObject({ name: "LicenseError", code });
      expect(await store.getMeta("bundle")).toBeNull();
      // grace must NOT rescue a rejected license
      clock.advance(MIN);
      await expect(manager.current()).rejects.toBeInstanceOf(LicenseError);
    });
  }

  it("blocked bundle -> track raises QuotaExceeded", async () => {
    const keys = makeKeys();
    const { fn } = mockFetch({
      bundle: () => json(200, envelope(keys, bundleData(T0, { limits: { monthly_cap: 10, used: 11, blocked: true } }))),
    });
    const aira = new AiraPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: "123", airaPublicKey: keys.publicB64,
      store: "sqlite::memory:", airaBaseUrl: BASE, fetch: fn, clock: new FakeClock(T0).read,
    });
    await expect(aira.track("purchased", { phone: "9876543210" })).rejects.toBeInstanceOf(QuotaExceeded);
    await aira.close();
  });

  it("rejects a public key of the wrong length", () => {
    expect(() => loadPublicKey(Buffer.from("short").toString("base64"))).toThrow(/32-byte/);
  });
});

describe("key rotation", () => {
  it("verifies when any key in the list matches", async () => {
    const old = makeKeys();
    const current = makeKeys();
    const clock = new FakeClock(T0);
    const store = await SqliteStore.open(":memory:");
    const { fn } = mockFetch({ bundle: () => json(200, envelope(current, bundleData(T0))) });
    const manager = new BundleManager(
      LICENSE_KEY, loadPublicKeys([old.publicB64, current.publicB64]), BASE, store, fn, clock.read);
    expect((await manager.current()).data.rules).toHaveLength(2);
  });

  it("still rejects a signer that is in no key", async () => {
    const clock = new FakeClock(T0);
    const store = await SqliteStore.open(":memory:");
    const { fn } = mockFetch({ bundle: () => json(200, envelope(makeKeys(), bundleData(T0))) });
    const manager = new BundleManager(
      LICENSE_KEY, loadPublicKeys([makeKeys().publicB64, makeKeys().publicB64]), BASE, store, fn, clock.read);
    await expect(manager.current()).rejects.toBeInstanceOf(BundleUnavailable);
  });

  it("key_id does not pick the key", async () => {
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    const store = await SqliteStore.open(":memory:");
    const { fn } = mockFetch({ bundle: () => json(200, { ...envelope(keys, bundleData(T0)), key_id: "v999" }) });
    const manager = new BundleManager(LICENSE_KEY, loadPublicKeys([keys.publicB64]), BASE, store, fn, clock.read);
    await expect(manager.current()).resolves.toBeDefined();
  });

  it("rejects an empty or malformed key list", () => {
    expect(() => loadPublicKeys([])).toThrow(TypeError);
    expect(() => loadPublicKeys(["short"])).toThrow(/32-byte/);
  });
});

describe("tenant pin", () => {
  it("pins the first verified tenant, then raises tenant_mismatch for another and never caches it", async () => {
    const keys = makeKeys();
    let tenant = "t1";
    const { manager, clock, store } = await setup(
      () => json(200, envelope(keys, bundleData(T0, { tenant_id: tenant }))), keys);
    await manager.current();
    expect(await store.getMeta("pinned_tenant_id")).toBe("t1");
    tenant = "t2";
    clock.advance(6 * MIN);
    const err = await manager.current().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(LicenseError);
    expect((err as LicenseError).code).toBe("tenant_mismatch");
    expect(String((err as Error).message)).not.toMatch(/t1|t2/);
    expect(await store.getMeta("pinned_tenant_id")).toBe("t1");
    expect(JSON.parse((await store.getMeta("bundle"))!).payload).toBe(
      envelope(keys, bundleData(T0, { tenant_id: "t1" })).payload);
  });

  it("track raises tenant_mismatch and sends nothing on a foreign bundle", async () => {
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    let tenant = "t1";
    const { fn, calls } = mockFetch({
      bundle: () => json(200, envelope(keys, bundleData(clock.read(), { tenant_id: tenant }))),
      meta: () => json(200, { messages: [{ id: "wamid.1" }] }),
    });
    const aira = new AiraPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: "123", airaPublicKey: keys.publicB64,
      store: "sqlite::memory:", airaBaseUrl: BASE, fetch: fn, clock: clock.read,
    });
    await aira.track("purchased", { phone: "9876543210" });
    tenant = "t2";
    clock.advance(6 * MIN);
    await expect(aira.track("purchased", { phone: "9123456789" })).rejects.toMatchObject({
      name: "LicenseError", code: "tenant_mismatch",
    });
    expect(calls.filter((c) => c.url.includes("graph.facebook"))).toHaveLength(1);
    await aira.close();
  });

  it("the pin survives a restart (same store)", async () => {
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    const store = await SqliteStore.open(":memory:");
    const make = (tenant: string) => new BundleManager(
      LICENSE_KEY, loadPublicKey(keys.publicB64), BASE, store,
      mockFetch({ bundle: () => json(200, envelope(keys, bundleData(clock.read(), { tenant_id: tenant }))) }).fn, clock.read);
    await make("t1").current();
    clock.advance(HOUR);
    await expect(make("t2").current()).rejects.toMatchObject({ code: "tenant_mismatch" });
  });
});

