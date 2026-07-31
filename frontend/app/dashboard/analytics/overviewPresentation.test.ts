import { describe, expect, it } from "vitest";

import { buildFunnel } from "./overviewPresentation";

describe("overview presentation — buildFunnel", () => {
  it("returns three steps with correct counts", () => {
    const funnel = buildFunnel({
      new_leads: 10,
      hot: 3,
      warm: 2,
      cold: 4,
      disqualified: 1,
      converted: 2,
    });

    expect(funnel).toEqual([
      { label: "New leads", count: 10 },
      { label: "Hot", count: 3 },
      { label: "Converted", count: 2 },
    ]);
  });

  it("returns all-zero steps for a zero-lead period", () => {
    const funnel = buildFunnel({});

    expect(funnel).toEqual([
      { label: "New leads", count: 0 },
      { label: "Hot", count: 0 },
      { label: "Converted", count: 0 },
    ]);
  });

  it("handles partial summary data (missing keys default to 0)", () => {
    const funnel = buildFunnel({ new_leads: 5 });

    expect(funnel).toEqual([
      { label: "New leads", count: 5 },
      { label: "Hot", count: 0 },
      { label: "Converted", count: 0 },
    ]);
  });
});
