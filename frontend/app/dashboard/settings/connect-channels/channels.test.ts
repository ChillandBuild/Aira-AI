import { describe, expect, test } from "vitest";
import { META_CHANNELS, STANDALONE_CHANNELS, resolveConnectionSource } from "./channels";
import type { Setting } from "./channels";

function setting(key: string, display_value: string, is_set = true): Setting {
  return { key, display_value, is_secret: false, is_set, updated_at: "2026-08-11T00:00:00Z" };
}

describe("resolveConnectionSource", () => {
  test("returns embedded when the channel is explicitly marked embedded", () => {
    const settings = [setting("instagram_connection_source", "embedded")];
    expect(resolveConnectionSource("instagram", settings)).toBe("embedded");
  });

  test("explicit manual wins over the embedded fallback signal", () => {
    const settings = [
      setting("instagram_connection_source", "manual"),
      { ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true },
    ];
    expect(resolveConnectionSource("instagram", settings)).toBe("manual");
  });

  test("falls back to embedded for legacy tenants that have a Meta business token", () => {
    const settings = [{ ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true }];
    expect(resolveConnectionSource("whatsapp", settings)).toBe("embedded");
  });

  test("falls back to manual when no marker and no Meta business token exist", () => {
    expect(resolveConnectionSource("whatsapp", [setting("meta_waba_id", "123")])).toBe("manual");
  });

  test("non-Meta channels are always manual", () => {
    const settings = [{ ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true }];
    expect(resolveConnectionSource("telegram", settings)).toBe("manual");
    expect(resolveConnectionSource("razorpay", settings)).toBe("manual");
  });
});

describe("channel grouping", () => {
  test("splits the four Meta channels from the standalone ones", () => {
    expect(META_CHANNELS.map(c => c.id)).toEqual(["whatsapp", "instagram", "facebook", "meta_ads"]);
    // astro_bridge is ops-entered in the operator console, not a tenant self-service
    // channel, so it is not in CHANNELS. See operator/client/[id]/views/config.tsx.
    expect(STANDALONE_CHANNELS.map(c => c.id)).toEqual(["telegram", "razorpay"]);
  });
});
