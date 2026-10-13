"use client";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { formatRupees } from "@/components/deals/money";
import { DayPoint, METRICS, Metric, percentChange, plural, runningSeries, Totals } from "./shared";

function Delta({ now, before }: { now: number; before: number }) {
  const change = percentChange(now, before);
  if (change === null) {
    return <span className="rounded-full bg-[#f1f5f9] px-1.5 py-px text-[11px] font-extrabold text-[#64748b]">{now ? "new" : "–"}</span>;
  }
  return (
    <span
      className={cn(
        "rounded-full px-1.5 py-px text-[11px] font-extrabold tabular-nums",
        change > 0 ? "bg-emerald-50 text-emerald-600" : change < 0 ? "bg-rose-50 text-rose-600" : "bg-[#f1f5f9] text-[#64748b]"
      )}
    >
      {change > 0 ? "▲ " : change < 0 ? "▼ " : ""}
      {Math.abs(change)}%
    </span>
  );
}

function Sparkline({ values, active }: { values: (number | null)[]; active: boolean }) {
  const points = values.map((v, i) => [i, v] as const).filter(([, v]) => v !== null) as [number, number][];
  if (points.length < 2) return <div className="mt-2 h-[26px]" />;
  const max = Math.max(...points.map(([, v]) => v)) || 1;
  const min = Math.min(0, ...points.map(([, v]) => v));
  const span = values.length - 1 || 1;
  const line = points.map(([i, v]) => `${((i / span) * 100).toFixed(1)},${(24 - ((v - min) / (max - min || 1)) * 22).toFixed(1)}`).join(" ");
  return (
    <svg className="mt-2 block h-[26px] w-full" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        points={line}
        fill="none"
        stroke={active ? "#038285" : "#94a3b8"}
        strokeWidth={1.6}
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

const DOTS: Record<Metric, string> = { revenue: "bg-emerald-500", deals: "bg-primary", avg: "bg-indigo-500" };

export function KpiStrip({
  metric,
  onMetric,
  now,
  before,
  compareText,
  compareTitle,
  days,
  upTo,
  lostCount,
  openCount,
  openTotal,
  lostHref,
  openHref,
}: {
  metric: Metric;
  onMetric: (m: Metric) => void;
  now: Totals;
  before: Totals | null;
  compareText: string | null;
  /** Full month names behind a short "vs avg of 3 months". */
  compareTitle?: string;
  days: DayPoint[];
  upTo: number;
  lostCount: number;
  openCount: number;
  openTotal: number;
  lostHref: string;
  openHref: string;
}) {
  const closed = now.count + lostCount;
  const wonShare = closed ? (now.count / closed) * 100 : 0;
  const subs: Record<Metric, string> = { revenue: plural(now.count, "deal") + " paid", deals: "paid deals", avg: "per won deal" };

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-5">
      {(Object.keys(METRICS) as Metric[]).map((key) => {
        const m = METRICS[key];
        const selected = metric === key;
        const value = m.value(now);
        return (
          <button
            key={key}
            type="button"
            onClick={() => onMetric(key)}
            aria-pressed={selected}
            className={cn(
              "relative flex min-w-0 flex-col rounded-2xl border bg-white px-4 py-3.5 text-left transition-all",
              selected ? "border-primary ring-[3px] ring-primary/10" : "border-[#e2e8f0] hover:border-slate-300"
            )}
          >
            {selected && (
              <span className="absolute right-3 top-3 rounded-full bg-primary/10 px-2 py-px text-[10px] font-extrabold text-primary">
                Showing
              </span>
            )}
            <span className="flex items-center gap-1.5 text-xs font-bold text-[#334155]">
              <i className={cn("h-2 w-2 rounded-full", DOTS[key])} />
              {m.label}
            </span>
            <span className="mt-1 truncate font-display text-2xl font-extrabold tabular-nums tracking-tight text-[#0A1528]">
              {key === "avg" && !now.count ? "—" : m.format(value)}
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-[#64748b]">
              {before && compareText ? (
                <>
                  <Delta now={value} before={m.value(before)} />
                  <span title={compareTitle}>{compareText}</span>
                </>
              ) : (
                subs[key]
              )}
            </span>
            <Sparkline values={runningSeries(days, key, upTo, "running")} active={selected} />
          </button>
        );
      })}

      <div className="flex min-w-0 flex-col rounded-2xl border border-[#e2e8f0] bg-white px-4 py-3.5">
        <span className="flex items-center gap-1.5 text-xs font-bold text-[#334155]">
          <i className="h-2 w-2 rounded-full bg-rose-500" />
          Closed as won
        </span>
        <span className="mt-1 font-display text-2xl font-extrabold tabular-nums tracking-tight text-[#0A1528]">
          {now.count} <span className="text-sm font-bold text-[#64748b]">of {closed}</span>
        </span>
        <span className="mt-0.5 text-[11px] text-[#64748b]">
          {lostCount} lost{closed ? ` · ${Math.round(wonShare)}% won` : ""}
        </span>
        <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-[#f1f5f9]">
          <i className="block h-full bg-emerald-500" style={{ width: `${wonShare}%` }} />
          <i className="block h-full bg-rose-500" style={{ width: `${closed ? 100 - wonShare : 0}%` }} />
        </div>
        <Link href={lostHref} className="mt-auto pt-2 text-[11px] font-extrabold text-primary hover:opacity-70">
          See lost deals →
        </Link>
      </div>

      <div className="col-span-2 flex min-w-0 flex-col rounded-2xl border border-[#e2e8f0] bg-white px-4 py-3.5 sm:col-span-1">
        <span className="flex items-center gap-1.5 text-xs font-bold text-[#334155]">
          <i className="h-2 w-2 rounded-full bg-amber-400" />
          Open right now
        </span>
        <span className="mt-1 truncate font-display text-2xl font-extrabold tabular-nums tracking-tight text-[#0A1528]">
          {formatRupees(openTotal)}
        </span>
        <span className="mt-0.5 text-[11px] text-[#64748b]">{plural(openCount, "deal")} · any month</span>
        <Link href={openHref} className="mt-auto pt-2 text-[11px] font-extrabold text-primary hover:opacity-70">
          Chase unpaid →
        </Link>
      </div>
    </div>
  );
}
