import { describe, expect, it } from "vitest";
import { getVisibleSettingsItems } from "./settingsNavigation";

describe("getVisibleSettingsItems", () => {
  it("fails open for legacy tenants with no subscription item rows", () => {
    const labels = getVisibleSettingsItems([], "telecmi").map((item) => item.label);

    expect(labels).toContain("Business Hours");
    expect(labels).toContain("Notifications");
    expect(labels).toContain("Telecalling Credentials");
  });

  it("hides notification settings without a messaging entitlement", () => {
    const labels = getVisibleSettingsItems(["telecalling_sim"], "sim_basic").map((item) => item.label);

    expect(labels).not.toContain("Business Hours");
    expect(labels).not.toContain("Notifications");
  });

  it("keeps notification settings for either messaging entitlement", () => {
    const outboundLabels = getVisibleSettingsItems(["outbound_messaging"], "telecmi").map((item) => item.label);
    const inboundLabels = getVisibleSettingsItems(["inbound_messaging"], "telecmi").map((item) => item.label);

    expect(outboundLabels).toContain("Business Hours");
    expect(inboundLabels).toContain("Notifications");
  });

  it("only exposes TeleCMI credentials once the provider is confirmed", () => {
    const loadingLabels = getVisibleSettingsItems([], null).map((item) => item.label);
    const simLabels = getVisibleSettingsItems([], "sim_basic").map((item) => item.label);
    const telecmiLabels = getVisibleSettingsItems([], "telecmi").map((item) => item.label);

    expect(loadingLabels).not.toContain("Telecalling Credentials");
    expect(simLabels).not.toContain("Telecalling Credentials");
    expect(telecmiLabels).toContain("Telecalling Credentials");
  });
});
