import { describe, expect, it } from "vitest";
import { capForTier, capUsagePercent, formatCount, relTime, tierForCap, usedTowardCap } from "./operator";

describe("relTime", () => {
  it("returns '—' for null", () => {
    expect(relTime(null)).toBe("—");
  });

  it("formats past seconds", () => {
    const iso = new Date(Date.now() - 30_000).toISOString();
    expect(relTime(iso)).toBe("30s ago");
  });

  it("formats past minutes", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(relTime(iso)).toBe("5m ago");
  });

  it("formats past hours", () => {
    const iso = new Date(Date.now() - 3 * 3_600_000).toISOString();
    expect(relTime(iso)).toBe("3h ago");
  });

  it("formats past days", () => {
    const iso = new Date(Date.now() - 2 * 86_400_000).toISOString();
    expect(relTime(iso)).toBe("2d ago");
  });

  it("formats future timestamps as 'in Xs'", () => {
    const iso = new Date(Date.now() + 45_000).toISOString();
    expect(relTime(iso)).toBe("in 45s");
  });

  it("formats future minutes as 'in Xm'", () => {
    const iso = new Date(Date.now() + 10 * 60_000).toISOString();
    expect(relTime(iso)).toBe("in 10m");
  });
});

describe("tierForCap", () => {
  it("maps null to no cap", () => expect(tierForCap(null)).toBe("none"));
  it("maps 10000 to starter", () => expect(tierForCap(10_000)).toBe("starter"));
  it("maps 50000 to growth", () => expect(tierForCap(50_000)).toBe("growth"));
  it("maps any other number to custom", () => expect(tierForCap(25_000)).toBe("custom"));
});

describe("capForTier", () => {
  it("returns fixed caps for starter and growth", () => {
    expect(capForTier("starter", "")).toBe(10_000);
    expect(capForTier("growth", "ignored")).toBe(50_000);
  });
  it("returns null for no cap", () => expect(capForTier("none", "")).toBeNull());
  it("parses a valid custom cap", () => expect(capForTier("custom", " 25000 ")).toBe(25_000));
  it("rejects empty, zero, negative and fractional custom caps", () => {
    for (const bad of ["", "0", "-5", "1.5", "abc"]) expect(capForTier("custom", bad)).toBeUndefined();
  });
});

describe("capUsagePercent", () => {
  it("is 0 with no cap", () => expect(capUsagePercent(500, null)).toBe(0));
  it("rounds the share used", () => expect(capUsagePercent(41_200, 50_000)).toBe(82));
  it("clamps at 100", () => expect(capUsagePercent(60_000, 50_000)).toBe(100));
});

describe("formatCount", () => {
  it("shows a dash when Meta has not counted the day yet", () => expect(formatCount(null)).toBe("—"));
  it("formats a number", () => expect(formatCount(41200)).toBe((41200).toLocaleString()));
});

describe("usedTowardCap", () => {
  it("uses the larger of reported and Meta", () => expect(usedTowardCap(100, 130)).toBe(130));
  it("falls back to reported when Meta is null", () => expect(usedTowardCap(100, null)).toBe(100));
});
