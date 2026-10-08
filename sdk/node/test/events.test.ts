/** Custom event slugs: any ^[a-z][a-z0-9_]{1,39}$ is accepted; the bundle decides whether a rule exists. */
import { afterEach, describe, expect, it } from "vitest";
import { AnrilPrivateSend } from "../src/client.js";
import { normalizeEvent } from "../src/core.js";
import { BASE, FakeClock, LICENSE_KEY, META_TOKEN, bundleData, envelope, json, makeKeys, mockFetch } from "./helpers.js";

const T0 = new Date("2026-10-07T10:00:00.000Z");
const PHONE_ID = "109876543210";

describe("normalizeEvent: custom slugs", () => {
  it.each([
    ["refund", "refund"],
    ["Refund", "refund"],
    ["  KYC_done  ", "kyc_done"],
    ["cart_abandoned_2", "cart_abandoned_2"],
    ["ab", "ab"],
    ["a" + "b".repeat(39), "a" + "b".repeat(39)],
  ])("accepts %j as %j", (raw, expected) => {
    expect(normalizeEvent(raw)).toBe(expected);
  });

  it.each([
    "a", "1abc", "_abc", "abc-def", "abc def", "refund!", "a" + "b".repeat(40), "é", "ab\ncd", "  ", "-", "__",
  ])("rejects %j", (raw) => {
    expect(normalizeEvent(raw)).toBeNull();
  });

  it.each([
    ["order", "purchased"], ["Sign Up", "signed_up"], ["ORDER-PLACED", "purchased"], ["lead", "interested"],
    [null, "interested"], ["", "interested"],
  ])("alias %j still maps to %j", (raw, expected) => {
    expect(normalizeEvent(raw as string | null)).toBe(expected);
  });
});

describe("track with custom events", () => {
  const open: AnrilPrivateSend[] = [];
  afterEach(async () => {
    while (open.length) await open.pop()!.close();
  });

  function build(extraRules: object[] = []) {
    const keys = makeKeys();
    const clock = new FakeClock(T0);
    const base = bundleData(clock.read());
    const { fn, calls } = mockFetch({
      bundle: () => json(200, envelope(keys, { ...base, rules: [...base.rules, ...extraRules] })),
      usage: () => json(200, { ok: true, accepted: 1 }),
      meta: () => json(200, { messages: [{ id: "wamid.1" }] }),
    });
    const anril = new AnrilPrivateSend({
      licenseKey: LICENSE_KEY, metaToken: META_TOKEN, phoneNumberId: PHONE_ID, anrilPublicKey: keys.publicB64,
      store: "sqlite::memory:", anrilBaseUrl: BASE, fetch: fn, clock: clock.read,
    });
    open.push(anril);
    return { anril, calls };
  }

  it("skips a custom event with no rule as no_rule", async () => {
    const { anril } = build();
    expect(await anril.track("refund", { phone: "9876543210" })).toEqual({ status: "skipped", reason: "no_rule" });
  });

  it("sends a custom event that has a rule", async () => {
    const { anril } = build([
      { id: "r9", event: "refund", template_id: "tp1", variables: null, button_param: null, enabled: true },
    ]);
    expect((await anril.track("Refund", { phone: "9876543210" })).status).toBe("sent");
  });

  it("still throws unknown event for junk", async () => {
    const { anril } = build();
    await expect(anril.track("not a slug!", { phone: "9876543210" })).rejects.toThrow("unknown event");
  });
});
