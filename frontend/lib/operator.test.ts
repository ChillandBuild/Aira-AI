import { describe, expect, it } from "vitest";
import { relTime } from "./operator";

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
