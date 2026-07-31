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

export type PerformanceCard = {
  label: string;
  value: string;
  delta: number | null;
  scope: "Selected period";
  lowerIsBetter?: boolean;
};

export type FunnelStep = {
  label: string;
  count: number;
};

export type LeadTrendPoint = {
  day: string;
  count: number;
};

function percentage(part: number, whole: number): number | null {
  if (whole <= 0) return null;
  return Math.round((part / whole) * 100);
}

function percentageDelta(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) return null;
  return Math.round(((current - previous) / previous) * 100);
}

function count(summary: Summary, key: string): number {
  return Number(summary[key] ?? 0);
}

function qualifiedRate(summary: Summary): number | null {
  return percentage(
    count(summary, "hot") + count(summary, "warm"),
    count(summary, "new_leads"),
  );
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

export function buildOverviewPresentation({
  current,
  previous,
}: {
  current: OverviewPeriod;
  previous: PreviousOverviewPeriod | null;
}): {
  cards: PerformanceCard[];
  funnel: FunnelStep[];
  trend: LeadTrendPoint[];
} {
  const currentSummary = current.summary;
  const previousSummary = previous?.summary ?? null;
  const currentQualifiedRate = qualifiedRate(currentSummary);
  const previousQualifiedRate = previousSummary ? qualifiedRate(previousSummary) : null;

  const newLeads = count(currentSummary, "new_leads");
  const qualified = count(currentSummary, "hot") + count(currentSummary, "warm");
  const hot = count(currentSummary, "hot");
  const converted = count(currentSummary, "converted");
  const costPerLead = current.money.cost_per_lead ?? null;
  const replyTime = current.response.p50_seconds ?? null;

  const cards: PerformanceCard[] = [
    {
      label: "New leads",
      value: newLeads.toLocaleString(),
      ...buildPerformanceCard({
        current: newLeads,
        previous: previousSummary ? count(previousSummary, "new_leads") : null,
      }),
    },
    {
      label: "Qualified rate",
      value: currentQualifiedRate == null ? "—" : `${currentQualifiedRate}%`,
      ...buildPerformanceCard({ current: currentQualifiedRate, previous: previousQualifiedRate }),
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

  const trend = (current.daily_segment_mix ?? []).map((point) => ({
    day: point.day,
    count: point.hot + point.warm + point.cold + point.disqualified,
  }));

  return {
    cards,
    funnel: [
      { label: "New leads", count: newLeads },
      { label: "Qualified", count: qualified },
      { label: "Hot", count: hot },
      { label: "Converted", count: converted },
    ],
    trend,
  };
}
