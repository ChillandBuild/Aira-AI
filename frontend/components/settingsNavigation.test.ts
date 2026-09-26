import { describe, expect, it } from "vitest";
import { getVisibleSettingsItems } from "./settingsNavigation";

describe("getVisibleSettingsItems", () => {
  it("fails open for legacy tenants with no subscription item rows", () => {
    const labels = getVisibleSettingsItems([]).map((item) => item.label);

    expect(labels).toContain("Notifications");
  });

  it("hides notification settings without a messaging entitlement", () => {
    const labels = getVisibleSettingsItems(["telecalling_sim"]).map((item) => item.label);

    expect(labels).not.toContain("Notifications");
  });

  it("keeps notification settings for either messaging entitlement", () => {
    const outboundLabels = getVisibleSettingsItems(["outbound_messaging"]).map((item) => item.label);
    const inboundLabels = getVisibleSettingsItems(["inbound_messaging"]).map((item) => item.label);

    expect(outboundLabels).toContain("Notifications");
    expect(inboundLabels).toContain("Notifications");
  });

  it("always exposes Profile & Business regardless of entitlements", () => {
    const noEntitlements = getVisibleSettingsItems([]).map((item) => item.label);
    const simOnly = getVisibleSettingsItems(["telecalling_sim"]).map((item) => item.label);

    expect(noEntitlements).toContain("Profile & Business");
    expect(simOnly).toContain("Profile & Business");
  });
});
