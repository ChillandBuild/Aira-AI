import { describe, expect, it } from "vitest";

import { buildFunnel, buildOverviewCards, buildTrend } from "./overviewPresentation";

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

describe("overview presentation — buildOverviewCards", () => {
  it("derives the four cards without treating missing money or reply data as zero", () => {
    const cards = buildOverviewCards({
      current: {
        summary: { new_leads: 10, hot: 3, warm: 2, cold: 4, disqualified: 1, converted: 2 },
        money: {},
        response: {},
      },
      previous: null,
    });

    expect(cards).toMatchObject([
      { label: "New leads", value: "10", delta: null },
      { label: "Conversions", value: "2", delta: null },
      { label: "Cost per lead", value: "—", delta: null },
      { label: "Median reply time", value: "—", delta: null },
    ]);
  });

  it("keeps a zero-lead period well-defined", () => {
    const cards = buildOverviewCards({
      current: {
        summary: { new_leads: 0, hot: 0, warm: 0, converted: 0 },
        money: { cost_per_lead: 0 },
        response: { p50_seconds: 0 },
      },
      previous: null,
    });

    expect(cards.map((card) => card.value)).toEqual(["0", "0", "₹0", "0s"]);
  });

  it("emits deltas only when a previous payload exists", () => {
    const cards = buildOverviewCards({
      current: {
        summary: { new_leads: 12, hot: 4, warm: 2, converted: 3 },
        money: { cost_per_lead: 100 },
        response: { p50_seconds: 60 },
      },
      previous: {
        summary: { new_leads: 8, hot: 2, warm: 2, converted: 2 },
        money: { cost_per_lead: 125 },
        response: { p50_seconds: 120 },
      },
    });

    expect(cards.map((card) => card.delta)).toEqual([50, 50, -20, -50]);
  });
});

describe("overview presentation — buildTrend", () => {
  it("sums all four segments per day", () => {
    const trend = buildTrend({
      summary: {},
      money: {},
      response: {},
      daily_segment_mix: [
        { day: "2026-08-01", hot: 3, warm: 2, cold: 4, disqualified: 1 },
        { day: "2026-08-02", hot: 0, warm: 0, cold: 0, disqualified: 0 },
      ],
    });

    expect(trend).toEqual([
      { day: "2026-08-01", count: 10 },
      { day: "2026-08-02", count: 0 },
    ]);
  });

  it("returns an empty array when there's no daily segment mix", () => {
    expect(buildTrend({ summary: {}, money: {}, response: {} })).toEqual([]);
  });
});
