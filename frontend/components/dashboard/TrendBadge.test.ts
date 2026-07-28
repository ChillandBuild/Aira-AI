import { describe, it, expect } from "vitest";
import { TrendBadge } from "./TrendBadge";

describe("TrendBadge", () => {
  it("returns null when pct is null", () => {
    const res = TrendBadge({ pct: null, label: "vs last week" });
    expect(res).toBeNull();
  });

  it("returns up badge representation for positive pct", () => {
    const res = TrendBadge({ pct: 12, label: "vs last week" });
    expect(res).not.toBeNull();
    expect(res?.props?.children[0]?.props?.children).toEqual(["↑", " ", 12, "%"]);
    expect(res?.props?.children[1]?.props?.children).toBe("vs last week");
  });

  it("returns down badge representation for negative pct", () => {
    const res = TrendBadge({ pct: -8, label: "vs last week" });
    expect(res).not.toBeNull();
    expect(res?.props?.children[0]?.props?.children).toEqual(["↓", " ", 8, "%"]);
  });

  it("returns flat badge representation for zero pct", () => {
    const res = TrendBadge({ pct: 0, label: "vs last week" });
    expect(res).not.toBeNull();
    expect(res?.props?.children[0]?.props?.children).toEqual(["→", " ", 0, "%"]);
  });
});
