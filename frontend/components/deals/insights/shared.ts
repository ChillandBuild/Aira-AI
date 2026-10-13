import { DealSource, DealStats } from "@/lib/api";
import { formatRupees } from "@/components/deals/money";
import { shortRupees } from "@/lib/deal-filters";

export const SOURCE_ORDER: DealSource[] = ["whatsapp", "indiamart", "form", "walk_in", "call", "justdial", "manual"];

export const SOURCE_COLOR: Record<DealSource, string> = {
  whatsapp: "#22c55e",
  indiamart: "#ef4444",
  form: "#038285",
  walk_in: "#f59e0b",
  call: "#6366f1",
  justdial: "#0ea5e9",
  manual: "#94a3b8",
};

export type Metric = "revenue" | "deals" | "avg";

/** One calendar day of the viewed month, filled in even when nothing sold. */
export interface DayPoint {
  day: number;
  count: number;
  total_paise: number;
  by_source: DealStats["by_day"][number]["by_source"];
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const SHORT_MONTHS = MONTH_NAMES.map((m) => m.slice(0, 3));
export const WEEKDAYS = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"];

export function parseMonth(month: string): { year: number; mon: number } {
  const [year, mon] = month.split("-").map(Number);
  return { year, mon };
}

export function monthKey(year: number, mon: number): string {
  return `${year}-${String(mon).padStart(2, "0")}`;
}

export function shiftMonth(month: string, by: number): string {
  const { year, mon } = parseMonth(month);
  const index = year * 12 + (mon - 1) + by;
  return monthKey(Math.floor(index / 12), (index % 12) + 1);
}

export function monthLabel(month: string, short = false): string {
  const { year, mon } = parseMonth(month);
  return `${(short ? SHORT_MONTHS : MONTH_NAMES)[mon - 1]} ${year}`;
}

export function daysInMonth(month: string): number {
  const { year, mon } = parseMonth(month);
  return new Date(Date.UTC(year, mon, 0)).getUTCDate();
}

/** Monday-first weekday index (0 = Mon) of the 1st of the month. */
export function firstWeekday(month: string): number {
  const { year, mon } = parseMonth(month);
  return (new Date(Date.UTC(year, mon - 1, 1)).getUTCDay() + 6) % 7;
}

/** Every day of the month, in order; days without a sale come back as zeros. */
export function fillDays(stats: DealStats | null, month: string): DayPoint[] {
  const byDate = new Map((stats?.by_day ?? []).map((d) => [Number(d.date.slice(8)), d]));
  return Array.from({ length: daysInMonth(month) }, (_, i) => {
    const hit = byDate.get(i + 1);
    return { day: i + 1, count: hit?.count ?? 0, total_paise: hit?.total_paise ?? 0, by_source: hit?.by_source ?? {} };
  });
}

export interface Totals {
  count: number;
  total_paise: number;
  avg_paise: number;
}

/** Totals over days 1..upTo (the "same days" comparison while a month is still running). */
export function totalsUpTo(days: DayPoint[], upTo: number): Totals {
  let count = 0;
  let total = 0;
  for (const d of days) {
    if (d.day > upTo) break;
    count += d.count;
    total += d.total_paise;
  }
  return { count, total_paise: total, avg_paise: count ? total / count : 0 };
}

export const METRICS: Record<Metric, {
  label: string;
  chartLabel: string;
  value: (t: Totals) => number;
  dayValue: (d: DayPoint) => number;
  format: (v: number) => string;
  axis: (v: number) => string;
}> = {
  revenue: {
    label: "Revenue won",
    chartLabel: "Revenue",
    value: (t) => t.total_paise,
    dayValue: (d) => d.total_paise,
    format: (v) => formatRupees(v),
    axis: (v) => shortRupees(v),
  },
  deals: {
    label: "Deals won",
    chartLabel: "Deals won",
    value: (t) => t.count,
    dayValue: (d) => d.count,
    format: (v) => String(Math.round(v)),
    axis: (v) => String(Math.round(v * 10) / 10),
  },
  avg: {
    label: "Average sale",
    chartLabel: "Average sale",
    value: (t) => t.avg_paise,
    dayValue: (d) => (d.count ? d.total_paise / d.count : 0),
    format: (v) => formatRupees(v),
    axis: (v) => shortRupees(v),
  },
};

/** Running series for the chart: cumulative total, or the month-to-date average for "avg". */
export function runningSeries(days: DayPoint[], metric: Metric, upTo: number, mode: "running" | "daily"): (number | null)[] {
  let count = 0;
  let total = 0;
  return days.map((d) => {
    if (d.day > upTo) return null;
    count += d.count;
    total += d.total_paise;
    if (mode === "daily") return METRICS[metric].dayValue(d);
    if (metric === "deals") return count;
    if (metric === "avg") return count ? total / count : null;
    return total;
  });
}

/** A round step (1, 2, 2.5 or 5 × 10ⁿ) that splits `max` into about four gridlines. */
export function niceStep(max: number): number {
  const rough = max / 4;
  if (rough <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * mag >= rough) return m * mag;
  return 10 * mag;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Percentage change, or null when there is nothing to compare against. */
export function percentChange(now: number, before: number): number | null {
  if (!before) return null;
  return Math.round(((now - before) / before) * 100);
}
