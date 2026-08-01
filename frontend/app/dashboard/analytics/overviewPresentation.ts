import type { CompareMoney, CompareResponseTimes } from "@/lib/api";

type Summary = Record<string, number>;

type OverviewPeriod = {
  summary: Summary;
  money: CompareMoney;
  response: CompareResponseTimes;
  daily_segment_mix?: {
    day: string;
    hot: number;
    warm: number;
    cold: number;
    disqualified: number;
  }[];
};

type PreviousOverviewPeriod = Pick<OverviewPeriod, "summary" | "money" | "response">;

export type FunnelStep = {
  label: string;
  count: number;
};

export type LeadTrendPoint = {
  day: string;
  count: number;
};

export type PerformanceCard = {
  label: string;
  value: string;
  delta: number | null;
  scope: "Selected period";
  lowerIsBetter?: boolean;
};

function count(summary: Summary, key: string): number {
  return Number(summary[key] ?? 0);
}

function percentageDelta(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) return null;
  return Math.round(((current - previous) / previous) * 100);
}

function formatMoney(value: number | null): string {
  return value == null ? "—" : `₹${Math.round(value).toLocaleString("en-IN")}`;
}

function formatSeconds(value: number | null): string {
  if (value == null) return "—";
  if (value < 60) return `${Math.round(value)}s`;
  return `${Math.round(value / 60)}m`;
}

export function buildPerformanceCard({
  current,
  previous,
}: {
  current: number | null;
  previous: number | null;
}) {
  return {
    current,
    previous,
    delta: percentageDelta(current, previous),
    scope: "Selected period" as const,
  };
}

export function buildFunnel(summary: Summary): FunnelStep[] {
  const newLeads = count(summary, "new_leads");
  return [
    { label: "New leads", count: newLeads },
    { label: "Hot", count: count(summary, "hot") },
    { label: "Converted", count: count(summary, "converted") },
  ];
}

export function buildOverviewCards({
  current,
  previous,
}: {
  current: OverviewPeriod;
  previous: PreviousOverviewPeriod | null;
}): PerformanceCard[] {
  const currentSummary = current.summary;
  const previousSummary = previous?.summary ?? null;
  const newLeads = count(currentSummary, "new_leads");
  const converted = count(currentSummary, "converted");
  const costPerLead = current.money.cost_per_lead ?? null;
  const replyTime = current.response.p50_seconds ?? null;

  return [
    {
      label: "New leads",
      value: newLeads.toLocaleString(),
      ...buildPerformanceCard({
        current: newLeads,
        previous: previousSummary ? count(previousSummary, "new_leads") : null,
      }),
    },
    {
      label: "Conversions",
      value: converted.toLocaleString(),
      ...buildPerformanceCard({
        current: converted,
        previous: previousSummary ? count(previousSummary, "converted") : null,
      }),
    },
    {
      label: "Cost per lead",
      value: formatMoney(costPerLead),
      lowerIsBetter: true,
      ...buildPerformanceCard({
        current: costPerLead,
        previous: previous?.money.cost_per_lead ?? null,
      }),
    },
    {
      label: "Median reply time",
      value: formatSeconds(replyTime),
      lowerIsBetter: true,
      ...buildPerformanceCard({
        current: replyTime,
        previous: previous?.response.p50_seconds ?? null,
      }),
    },
  ];
}

export function buildTrend(current: OverviewPeriod): LeadTrendPoint[] {
  return (current.daily_segment_mix ?? []).map((point) => ({
    day: point.day,
    count: point.hot + point.warm + point.cold + point.disqualified,
  }));
}
