import { describe, expect, it } from "vitest";

import { canLoadComparison } from "./periodSelection";

describe("canLoadComparison", () => {
  it("loads a report without comparison when its reporting range is complete", () => {
    expect(
      canLoadComparison(
        { preset: "custom", start: "2026-07-01", end: "2026-07-07" },
        { mode: "off", start: "", end: "" },
      ),
    ).toBe(true);
  });

  it("waits for both comparison dates in custom mode", () => {
    expect(
      canLoadComparison(
        { preset: "last_7d", start: "", end: "" },
        { mode: "custom", start: "2026-06-01", end: "" },
      ),
    ).toBe(false);
  });

  it("waits for a chronological reporting range", () => {
    expect(
      canLoadComparison(
        { preset: "custom", start: "2026-07-07", end: "2026-07-01" },
        { mode: "off", start: "", end: "" },
      ),
    ).toBe(false);
  });

  it("waits for a chronological custom comparison range", () => {
    expect(
      canLoadComparison(
        { preset: "last_7d", start: "", end: "" },
        { mode: "custom", start: "2026-06-05", end: "2026-06-01" },
      ),
    ).toBe(false);
  });
});
