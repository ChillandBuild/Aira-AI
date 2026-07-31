import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { comparisonLabel } from "@/components/analytics/ComparisonPicker";
import { ComparePayload } from "@/lib/api";
import { ComparisonHeader, shouldRenderComparisonChart } from "./CompareTab";

const current = {
  start: "2026-07-01",
  end: "2026-07-07",
  summary: {},
  money: {},
  response: {},
  movement: { promoted: 0, demoted: 0, promoted_to_hot: 0, flows: [] },
};

const withoutComparison: ComparePayload = {
  preset: "custom",
  current,
  previous: null,
  summary_text: null,
  metrics: {},
  money_metrics: {},
  response_metrics: {},
  movement_metrics: {},
  series: {},
};

describe("comparison presentation", () => {
  it("labels disabled comparison as no comparison", () => {
    expect(comparisonLabel({ mode: "off", start: "", end: "" })).toBe("No comparison");
  });

  it("labels a complete custom comparison with its exact dates", () => {
    expect(
      comparisonLabel({ mode: "custom", start: "2026-06-01", end: "2026-06-14" }),
    ).toBe("2026-06-01 → 2026-06-14");
  });

  it("renders a current-period header without versus text when previous is absent", () => {
    const html = renderToStaticMarkup(<ComparisonHeader data={withoutComparison} />);

    expect(html).toContain("2026-07-01 → 2026-07-07");
    expect(html).not.toContain("vs");
  });

  it("does not render a comparison chart without a previous period", () => {
    expect(shouldRenderComparisonChart(null)).toBe(false);
  });
});
