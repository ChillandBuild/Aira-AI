import { describe, expect, test } from "vitest";
import { buildDisconnectTarget } from "./disconnect";
import type { Setting } from "./channels";

function setting(key: string): Setting {
  return { key, display_value: "x", is_secret: false, is_set: true, updated_at: "2026-08-11T00:00:00Z" };
}

const whatsappConfigured = [
  "meta_phone_number_id", "meta_waba_id", "meta_access_token",
  "meta_webhook_verify_token", "meta_app_secret",
].map(setting);

describe("buildDisconnectTarget", () => {
  test("a whole-Meta disconnect lists only the channels that are actually connected", () => {
    const target = buildDisconnectTarget("meta", whatsappConfigured);
    expect(target.label).toBe("Meta Business");
    expect(target.stops).toEqual(["WhatsApp Cloud API stops receiving and sending messages"]);
  });

  test("WhatsApp warns that other Meta channels share its token", () => {
    expect(buildDisconnectTarget("whatsapp", whatsappConfigured).sharesMetaToken).toBe(true);
  });

  test("Meta Ads is described as reporting, never as messaging", () => {
    const configured = ["meta_ads_account_id", "meta_ads_access_token"].map(setting);
    expect(buildDisconnectTarget("meta_ads", configured).stops).toEqual([
      "Meta Ads stops importing ad performance data",
    ]);
  });

  test("Telegram carries no shared-token warning", () => {
    const target = buildDisconnectTarget("telegram", []);
    expect(target.sharesMetaToken).toBe(false);
    expect(target.stops).toEqual(["Telegram Bot stops receiving and sending messages"]);
  });
});
