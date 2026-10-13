"use client";
import { cn } from "@/lib/utils";
import { formatRupees } from "@/components/deals/money";
import { shortRupees } from "@/lib/deal-filters";
import { DayPoint, firstWeekday, METRICS, Metric, monthLabel, plural, WEEKDAYS } from "./shared";

const SHADES = ["#9fd2d3", "#3fa3a5", "#038285"];

/** Weekday with the most revenue, once there are enough sale days for it to mean something. */
function bestWeekday(days: DayPoint[], month: string): string | null {
  const saleDays = days.filter((d) => d.count > 0);
  if (saleDays.length < 4) return null;
  const offset = firstWeekday(month);
  const sums = Array(7).fill(0);
  for (const d of saleDays) sums[(offset + d.day - 1) % 7] += d.total_paise;
  const best = sums.indexOf(Math.max(...sums));
  return WEEKDAYS[best];
}

export function SalesCalendar({
  month,
  days,
  metric,
  lastDay,
  today,
  selectedDay,
  onSelect,
}: {
  month: string;
  days: DayPoint[];
  metric: Metric;
  /** Last day that has happened (the whole month for a past month). */
  lastDay: number;
  today: number | null;
  selectedDay: number | null;
  onSelect: (day: number | null) => void;
}) {
  const m = METRICS[metric];
  const past = days.filter((d) => d.day <= lastDay);
  const peak = Math.max(0, ...past.map(m.dayValue));
  const best = past.reduce<DayPoint | null>((a, d) => (m.dayValue(d) > (a ? m.dayValue(a) : 0) ? d : a), null);
  const weekday = bestWeekday(past, month);
  const lead = firstWeekday(month);
  const monthName = monthLabel(month).split(" ")[0];

  return (
    <section className="min-w-0 rounded-2xl border border-[#e2e8f0] bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-extrabold text-[#0A1528]">
            {monthName} · {m.chartLabel.toLowerCase()} by day
          </h2>
          <p className="mt-0.5 text-xs text-[#64748b]">
            {best ? `Best day ${monthName.slice(0, 3)} ${best.day}` : "No sales yet this month"}
            {weekday && ` · ${weekday} bring in the most money`}
          </p>
        </div>
        <span className="flex items-center gap-1 text-[11px] text-[#64748b]" aria-hidden="true">
          Less
          <i className="h-3 w-3 rounded-[3px] bg-[#f1f5f9]" />
          {SHADES.map((s) => (
            <i key={s} className="h-3 w-3 rounded-[3px]" style={{ background: s }} />
          ))}
          More
        </span>
      </div>

      <div className="mt-3 grid grid-cols-7 gap-[3px] sm:gap-1.5">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="px-1 pb-0.5 text-[10px] font-extrabold uppercase tracking-wider text-[#94a3b8]">
            {d}
          </div>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <div key={`lead-${i}`} />
        ))}
        {days.map((d) => {
          const future = d.day > lastDay;
          if (future) {
            return (
              <div
                key={d.day}
                className="min-h-[48px] rounded-lg border border-dashed border-[#e2e8f0] p-1.5 text-[11px] font-extrabold text-slate-300 sm:min-h-[60px] sm:rounded-xl"
              >
                {d.day}
              </div>
            );
          }
          const value = m.dayValue(d);
          const level = d.count && peak ? Math.min(2, Math.floor((value / peak) * 3 - 1e-9)) : -1;
          const dark = level >= 1;
          const selected = selectedDay === d.day;
          return (
            <button
              key={d.day}
              type="button"
              onClick={() => onSelect(selected ? null : d.day)}
              aria-pressed={selected}
              aria-label={`${monthName} ${d.day}: ${d.count ? `${formatRupees(d.total_paise)}, ${plural(d.count, "deal")}` : "no sales"}`}
              title={d.count ? `${formatRupees(d.total_paise)} · ${plural(d.count, "deal")}` : "No sales"}
              style={level >= 0 ? { background: SHADES[level] } : undefined}
              className={cn(
                "flex min-h-[48px] min-w-0 flex-col justify-between rounded-lg p-1.5 text-left transition-all hover:-translate-y-px hover:shadow-md sm:min-h-[60px] sm:rounded-xl sm:p-2",
                level < 0 && "bg-[#f1f5f9]",
                selected && "ring-2 ring-[#0A1528]",
                selectedDay !== null && !selected && "opacity-60"
              )}
            >
              <span className={cn("text-[11px] font-extrabold", dark ? "text-white" : "text-[#64748b]")}>
                {d.day}
                {today === d.day && <span className="hidden font-bold sm:inline"> · today</span>}
              </span>
              {d.count > 0 && (
                <span className={cn("min-w-0", dark ? "text-white" : "text-[#0A1528]")}>
                  <span className="block truncate text-[10px] font-extrabold tabular-nums sm:text-xs">
                    {metric === "deals" ? (
                      <>
                        <span className="sm:hidden">{d.count}</span>
                        <span className="hidden sm:inline">{plural(d.count, "deal")}</span>
                      </>
                    ) : (
                      shortRupees(value)
                    )}
                  </span>
                  <span className="hidden truncate text-[10px] font-semibold opacity-80 sm:block">
                    {metric === "deals" ? shortRupees(d.total_paise) : plural(d.count, "deal")}
                  </span>
                </span>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
