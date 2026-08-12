import { describe, expect, test } from "vitest";
import { MetaSignupCoordinator, buildMetaLoginOptions } from "./metaSignupMode";

describe("Meta signup mode", () => {
  test("launches coexistence with WhatsApp Business App onboarding enabled", () => {
    expect(buildMetaLoginOptions("config-123", "coexistence")).toEqual({
      config_id: "config-123",
      response_type: "code",
      override_default_response_type: true,
      extras: {
        setup: {},
        featureType: "whatsapp_business_app_onboarding",
        sessionInfoVersion: "3",
      },
    });
  });

  test("rejects standard completion after connect-without-switching was selected", () => {
    const coordinator = new MetaSignupCoordinator();
    coordinator.begin("coexistence");
    const popup = {};

    expect(() => coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "waba-1", phone_number_id: "phone-1" },
    }, popup)).toThrow(
      "Meta did not open the connect-without-switching flow"
    );
  });

  test("coordinates an event arriving before the OAuth code", () => {
    const coordinator = new MetaSignupCoordinator();
    const attemptId = coordinator.begin("coexistence");
    const popup = {};

    expect(coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
      data: { waba_id: "waba-1", phone_number_id: "phone-1", business_id: "business-1" },
    }, popup)).toBeNull();
    expect(coordinator.receiveCode(attemptId!, "oauth-code")).toEqual({
      code: "oauth-code",
      session: {
        waba_id: "waba-1",
        phone_number_id: "phone-1",
        business_id: "business-1",
        is_coexistence: true,
      },
    });
  });

  test("coordinates the OAuth code arriving before the event", () => {
    const coordinator = new MetaSignupCoordinator();
    const attemptId = coordinator.begin("standard");
    const popup = {};

    expect(coordinator.receiveCode(attemptId!, "oauth-code")).toBeNull();
    expect(coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "waba-1", phone_number_id: "phone-1" },
    }, popup)).toEqual({
      code: "oauth-code",
      session: {
        waba_id: "waba-1",
        phone_number_id: "phone-1",
        business_id: undefined,
        is_coexistence: false,
      },
    });
  });

  test("ignores an old OAuth callback after a mismatched flow and retry", () => {
    const coordinator = new MetaSignupCoordinator();
    const staleAttemptId = coordinator.begin("coexistence");
    const stalePopup = {};
    expect(() => coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "old-waba", phone_number_id: "old-phone" },
    }, stalePopup)).toThrow();

    const currentAttemptId = coordinator.begin("standard");
    expect(coordinator.receiveCode(staleAttemptId!, "stale-code")).toBeNull();
    expect(coordinator.receiveCode(currentAttemptId!, "current-code")).toBeNull();
    expect(coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "old-waba", phone_number_id: "old-phone" },
    }, stalePopup)).toBeNull();
    const currentPopup = {};
    expect(coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "new-waba", phone_number_id: "new-phone" },
    }, currentPopup)?.code).toBe("current-code");
  });

  test("prevents a second signup launch while one is active", () => {
    const coordinator = new MetaSignupCoordinator();
    expect(coordinator.begin("standard")).toBe(1);
    expect(coordinator.begin("coexistence")).toBeNull();
  });

  test("ignores malformed Meta messages", () => {
    const coordinator = new MetaSignupCoordinator();
    coordinator.begin("coexistence");
    expect(coordinator.receiveMessage({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
      data: { waba_id: 123, phone_number_id: "phone-1" },
    }, {})).toBeNull();
  });

  test("accepts Meta's JSON-string message format without throwing on invalid JSON", () => {
    const coordinator = new MetaSignupCoordinator();
    const attemptId = coordinator.begin("standard");
    expect(coordinator.receiveCode(attemptId!, "oauth-code")).toBeNull();
    expect(coordinator.receiveMessage("{invalid-json", {})).toBeNull();
    expect(coordinator.receiveMessage(JSON.stringify({
      type: "WA_EMBEDDED_SIGNUP",
      event: "FINISH",
      data: { waba_id: "waba-1", phone_number_id: "phone-1" },
    }), {})?.code).toBe("oauth-code");
  });
});
