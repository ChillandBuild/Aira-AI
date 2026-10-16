import { describe, expect, it } from "vitest";
import type { AdBreakdownValues } from "@/lib/api";
import { BREAKDOWN_TABS, cheapestSentence, costPerClick, groupLabel, pickCheapest } from "./ad-breakdown";

function values(overrides: Partial<AdBreakdownValues> = {}): AdBreakdownValues {
  return {
    inline_link_clicks: 10,
    spend: 200,
    cost_per_inline_link_click: 20,
    impressions: 1000,
    inline_link_click_ctr: 1,
    ...overrides,
  };
}

describe("BREAKDOWN_TABS", () => {
  it("lists the five breakdowns in order", () => {
    expect(BREAKDOWN_TABS.map((tab) => tab.key)).toEqual(["placement", "age", "gender", "region", "device"]);
    expect(BREAKDOWN_TABS[1]).toEqual({ key: "age", label: "Age", noun: "age group" });
  });
});

describe("groupLabel: placement", () => {
  it.each([
    ["instagram · instagram_reels", "Instagram Reels"],
    ["facebook · feed", "Facebook Feed"],
    ["facebook · facebook_reels", "Facebook Reels"],
    ["messenger · messenger_inbox", "Messenger Inbox"],
    ["audience_network · an_classic", "Audience Network Native"],
    ["instagram · story", "Instagram Stories"],
    ["instagram · explore_home", "Instagram Explore home"],
    ["facebook · right_hand_column", "Facebook Right column"],
    ["facebook · instream_video", "Facebook In-stream videos"],
    ["facebook · banner", "Facebook Banner"],
    ["threads · feed", "Threads Feed"],
    ["whatsapp · status", "WhatsApp Status"],
    ["tiktok · feed", "Tiktok Feed"],
  ])("maps %s to %s", (raw, expected) => {
    expect(groupLabel(raw, "placement")).toBe(expected);
  });

  it("shows just the platform when there is no position part", () => {
    expect(groupLabel("instagram", "placement")).toBe("Instagram");
  });
});

describe("groupLabel: gender and device", () => {
  it("maps gender values", () => {
    expect(groupLabel("male", "gender")).toBe("Men");
    expect(groupLabel("female", "gender")).toBe("Women");
    expect(groupLabel("unknown", "gender")).toBe("Unknown");
  });

  it("maps device values", () => {
    expect(groupLabel("android_smartphone", "device")).toBe("Android phone");
    expect(groupLabel("android_tablet", "device")).toBe("Android tablet");
    expect(groupLabel("iphone", "device")).toBe("iPhone");
    expect(groupLabel("ipad", "device")).toBe("iPad");
    expect(groupLabel("desktop", "device")).toBe("Computer");
    expect(groupLabel("other", "device")).toBe("Other");
    expect(groupLabel("smart_watch", "device")).toBe("Smart watch");
  });
});

describe("groupLabel: age, region and empty values", () => {
  it("leaves age and region unchanged", () => {
    expect(groupLabel("25-34", "age")).toBe("25-34");
    expect(groupLabel("65+", "age")).toBe("65+");
    expect(groupLabel("Tamil Nadu", "region")).toBe("Tamil Nadu");
  });

  it("returns Unknown for empty, null-ish or Unknown input", () => {
    expect(groupLabel("", "region")).toBe("Unknown");
    expect(groupLabel("   ", "age")).toBe("Unknown");
    expect(groupLabel("Unknown", "region")).toBe("Unknown");
    expect(groupLabel(null as unknown as string, "placement")).toBe("Unknown");
    expect(groupLabel(undefined as unknown as string, "device")).toBe("Unknown");
  });
});

describe("costPerClick", () => {
  it("uses Meta's cost per chat click when present", () => {
    expect(costPerClick(values({ cost_per_inline_link_click: 18, spend: 200, inline_link_clicks: 10 }))).toBe(18);
  });

  it("falls back to spend divided by clicks", () => {
    expect(costPerClick(values({ cost_per_inline_link_click: null, spend: 300, inline_link_clicks: 12 }))).toBe(25);
  });

  it("returns null when it cannot be worked out", () => {
    expect(costPerClick(values({ cost_per_inline_link_click: null, spend: 300, inline_link_clicks: 0 }))).toBeNull();
    expect(costPerClick(values({ cost_per_inline_link_click: null, spend: null, inline_link_clicks: 4 }))).toBeNull();
  });
});

describe("pickCheapest", () => {
  const row = (label: string, overrides: Partial<AdBreakdownValues>) => ({ label, values: values(overrides) });

  it("picks the index of the lowest cost among rows with enough clicks", () => {
    const rows = [
      row("A", { inline_link_clicks: 20, cost_per_inline_link_click: 30 }),
      row("B", { inline_link_clicks: 8, cost_per_inline_link_click: 12 }),
      row("C", { inline_link_clicks: 15, cost_per_inline_link_click: 22 }),
    ];
    expect(pickCheapest(rows)).toBe(1);
  });

  it("ignores rows below the minimum click count", () => {
    const rows = [
      row("A", { inline_link_clicks: 4, cost_per_inline_link_click: 5 }),
      row("B", { inline_link_clicks: 9, cost_per_inline_link_click: 25 }),
      row("C", { inline_link_clicks: 9, cost_per_inline_link_click: 30 }),
    ];
    expect(pickCheapest(rows)).toBe(1);
  });

  it("honours a custom minimum", () => {
    const rows = [
      row("A", { inline_link_clicks: 4, cost_per_inline_link_click: 5 }),
      row("B", { inline_link_clicks: 9, cost_per_inline_link_click: 25 }),
    ];
    expect(pickCheapest(rows, 3)).toBe(0);
  });

  it("skips rows with no cost", () => {
    const rows = [
      row("A", { inline_link_clicks: 10, cost_per_inline_link_click: null, spend: null }),
      row("B", { inline_link_clicks: 10, cost_per_inline_link_click: 40 }),
      row("C", { inline_link_clicks: 10, cost_per_inline_link_click: 35 }),
    ];
    expect(pickCheapest(rows)).toBe(2);
  });

  it("returns null when fewer than two rows qualify", () => {
    expect(pickCheapest([])).toBeNull();
    expect(pickCheapest([row("A", { inline_link_clicks: 10 })])).toBeNull();
    expect(pickCheapest([
      row("A", { inline_link_clicks: 10, cost_per_inline_link_click: 10 }),
      row("B", { inline_link_clicks: 2, cost_per_inline_link_click: 5 }),
    ])).toBeNull();
    expect(pickCheapest([
      row("A", { inline_link_clicks: 10, cost_per_inline_link_click: 10 }),
      row("B", { inline_link_clicks: 10, cost_per_inline_link_click: null, spend: null }),
    ])).toBeNull();
  });
});

describe("cheapestSentence", () => {
  it("returns null when there is no overall cost", () => {
    expect(cheapestSentence("Instagram Reels", 15, null)).toBeNull();
  });

  it("returns null when the group is not cheaper than the whole ad", () => {
    expect(cheapestSentence("Facebook Feed", 25, 20)).toBeNull();
    expect(cheapestSentence("Facebook Feed", 20, 20)).toBeNull();
  });

  it("builds the callout with rounded rupee amounts", () => {
    expect(cheapestSentence("Instagram Reels", 14.4, 21.6)).toBe(
      "Cheapest chat clicks for this ad: Instagram Reels, ₹14 each vs ₹22 for the whole ad.",
    );
  });

  it("uses en-IN grouping for large amounts", () => {
    expect(cheapestSentence("Feed", 1234.4, 15000)).toBe(
      "Cheapest chat clicks for this ad: Feed, ₹1,234 each vs ₹15,000 for the whole ad.",
    );
  });
});
