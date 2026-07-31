import { describe, expect, it } from "vitest";

import {
  attentionLeadHref,
  attentionScopeLabel,
  buildOverviewPresentation,
  buildPerformanceCard,
} from "./overviewPresentation";

describe("overview presentation", () => {
  it("does not emit a delta when the client selected no comparison", () => {
    expect(buildPerformanceCard({ current: 294, previous: null })).toMatchObject({
      delta: null,
      scope: "Selected period",
    });
  });

  it("labels a rolling queue independently from the reporting period", () => {
    expect(attentionScopeLabel()).toBe("Last 24 hours");
  });

  it("opens the selected stale lead in its conversation", () => {
    expect(attentionLeadHref("lead 42")).toBe("/dashboard/conversations?lead=lead%2042");
  });

  it("derives selected-period cards without treating missing money or reply data as zero", () => {
    const presentation = buildOverviewPresentation({
      current: {
        summary: {
          new_leads: 10,
          hot: 3,
          warm: 2,
          cold: 4,
          disqualified: 1,
          converted: 2,
        },
        money: {},
        response: {},
        daily_segment_mix: [],
      },
      previous: null,
    });

    expect(presentation.cards).toMatchObject([
      { label: "New leads", value: "10", delta: null },
      { label: "Qualified rate", value: "50%", delta: null },
      { label: "Conversions", value: "2", delta: null },
      { label: "Cost per lead", value: "—", delta: null },
      { label: "Median reply time", value: "—", delta: null },
    ]);
  });

  it("keeps a zero-lead qualified rate well-defined", () => {
    const presentation = buildOverviewPresentation({
      current: {
        summary: { new_leads: 0, hot: 0, warm: 0, converted: 0 },
        money: { cost_per_lead: 0 },
        response: { p50_seconds: 0 },
        daily_segment_mix: [],
      },
      previous: null,
    });

    expect(presentation.cards.map((card) => card.value)).toEqual([
      "0",
      "—",
      "0",
      "₹0",
      "0s",
    ]);
  });

  it("emits deltas only when a previous payload exists", () => {
    const presentation = buildOverviewPresentation({
      current: {
        summary: { new_leads: 12, hot: 4, warm: 2, converted: 3 },
        money: { cost_per_lead: 100 },
        response: { p50_seconds: 60 },
        daily_segment_mix: [],
      },
      previous: {
        summary: { new_leads: 8, hot: 2, warm: 2, converted: 2 },
        money: { cost_per_lead: 125 },
        response: { p50_seconds: 120 },
      },
    });

    expect(presentation.cards.map((card) => card.delta)).toEqual([
      50,
      0,
      50,
      -20,
      -50,
    ]);
  });
});
