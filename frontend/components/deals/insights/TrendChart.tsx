"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatRupees } from "@/components/deals/money";
import { DealSource } from "@/lib/api";
import { SOURCE_LABEL } from "@/lib/deal-filters";
import { COMPARE_COLORS, DayPoint, METRICS, Metric, monthLabel, monthsText, niceStep, plural, runningSeries, SOURCE_COLOR, SOURCE_ORDER } from "./shared";

const L = 48;
const R = 14;
const T = 16;
const B = 26;

export function TrendChart({
  month,
  days,
  lastDay,
  today,
  compares,
  metric,
  mode,
  onMode,
  selectedDay,
  onSelect,
}: {
  month: string;
  days: DayPoint[];
  lastDay: number;
  today: number | null;
  /** Months to compare with (up to MAX_COMPARE), each drawn as its own dashed line. */
  compares: { month: string; days: DayPoint[] }[];
  metric: Metric;
  mode: "running" | "daily";
  onMode: (m: "running" | "daily") => void;
  selectedDay: number | null;
  onSelect: (day: number | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 260 });
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth || 600, h: el.clientHeight || 260 });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const m = METRICS[metric];
  const monthShort = monthLabel(month, true).split(" ")[0];
  const now = runningSeries(days, metric, lastDay, mode);
  const befores = compares.map((c) => runningSeries(c.days, metric, c.days.length, mode));
  const span = Math.max(days.length, ...compares.map((c) => c.days.length));
  // Per day, several months of bars side by side get unreadable, so the grey bar is their average.
  const avgBefore = Array.from({ length: span }, (_, i) => {
    const vals = befores.map((b) => b[i]).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
  });
  const compareName =
    compares.length === 0 ? "" : compares.length === 1 ? monthLabel(compares[0].month) : `Avg of ${monthsText(compares.map((c) => c.month))}`;

  const plotted = mode === "daily" ? [...now, ...avgBefore] : [...now, ...befores.flat()];
  const peak = Math.max(0, ...plotted.filter((v): v is number => v != null));
  // An empty month still gets a readable scale (₹1k / 4 deals); deal counts only use whole steps.
  const floor = metric === "deals" ? 4 : 100000;
  const rawStep = niceStep(Math.max(peak, floor));
  const step = metric === "deals" ? Math.max(1, Math.round(rawStep)) : rawStep;
  const top = Math.max(step, Math.ceil(peak / step) * step);
  const ticks = Math.round(top / step);

  const pw = Math.max(1, size.w - L - R);
  const ph = Math.max(1, size.h - T - B);
  const x = (day: number) => L + ((day - 1) / Math.max(1, span - 1)) * pw;
  const y = (v: number) => T + ph - (v / top) * ph;
  const path = (values: (number | null)[]) =>
    values
      .map((v, i) => (v === null ? "" : `${i > 0 && values[i - 1] !== null ? "L" : "M"}${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`))
      .join("");

  const nowPath = path(now);
  const firstIdx = now.findIndex((v) => v !== null);
  const lastIdx = now.reduce<number>((acc, v, i) => (v !== null ? i : acc), -1);
  const area = firstIdx >= 0 ? `${nowPath}L${x(lastIdx + 1)},${y(0)}L${x(firstIdx + 1)},${y(0)}Z` : "";
  const xLabels = [1, 5, 10, 15, 20, 25, span].filter((d, i, arr) => d <= span && arr.indexOf(d) === i);
  const slot = pw / Math.max(1, span - 1);

  const hoverNow = hover !== null ? now[hover - 1] ?? null : null;
  const hoverBefores = hover !== null ? compares.map((c, i) => ({ month: c.month, value: befores[i][hover - 1] ?? null, color: COMPARE_COLORS[i] })) : [];
  const hoverAnchor = hoverNow ?? hoverBefores.find((b) => b.value !== null)?.value ?? null;
  const selected = selectedDay ? days[selectedDay - 1] : null;
  const selectedValue = selectedDay ? now[selectedDay - 1] : null;
  const title = mode === "daily" ? "per day" : metric === "avg" ? "month so far" : "running total";

  return (
    <section className="flex min-w-0 flex-col rounded-2xl border border-[#e2e8f0] bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-extrabold text-[#0A1528]">
          {m.chartLabel} · {title}
        </h2>
        <div className="flex gap-0.5 rounded-xl border border-[#e2e8f0] bg-[#f8fafc] p-0.5" role="group" aria-label="Chart view">
          {(["running", "daily"] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onMode(key)}
              aria-pressed={mode === key}
              className={cn(
                "rounded-lg px-2.5 py-1 text-[11px] font-bold transition-all",
                mode === key ? "bg-white text-[#0A1528] shadow-sm" : "text-[#64748b] hover:text-[#0A1528]"
              )}
            >
              {key === "running" ? "Running total" : "Per day"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-4 text-[11px] font-bold text-[#64748b]">
        <span className="flex items-center gap-1.5">
          {mode === "daily" ? (
            <i className="h-2.5 w-2.5 rounded-[3px] bg-primary" />
          ) : (
            <i className="w-4 border-t-[2.5px] border-primary" />
          )}
          {monthLabel(month)}
        </span>
        {compares.length > 0 &&
          (mode === "daily" ? (
            <span className="flex items-center gap-1.5">
              <i className="h-2.5 w-2.5 rounded-[3px] bg-[#cbd5e1]" />
              {compareName}
            </span>
          ) : (
            compares.map((c, i) => (
              <span key={c.month} className="flex items-center gap-1.5">
                <i className="w-4 border-t-2 border-dashed" style={{ borderColor: COMPARE_COLORS[i] }} />
                {monthLabel(c.month)}
              </span>
            ))
          ))}
      </div>

      <div ref={box} className="relative mt-1 min-h-[240px] flex-1">
        <svg
          className="absolute inset-0 h-full w-full overflow-visible"
          viewBox={`0 0 ${size.w} ${size.h}`}
          role="img"
          aria-label={`${m.chartLabel} in ${monthLabel(month)}${
            compares.length ? ` compared with ${compares.map((c) => monthLabel(c.month)).join(", ")}` : ""
          }`}
        >
          <defs>
            <linearGradient id="insights-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#038285" stopOpacity="0.2" />
              <stop offset="1" stopColor="#038285" stopOpacity="0" />
            </linearGradient>
          </defs>
          {Array.from({ length: ticks + 1 }, (_, i) => {
            const v = (top / ticks) * i;
            return (
              <g key={i}>
                <line x1={L} x2={size.w - R} y1={y(v)} y2={y(v)} stroke={i ? "#f1f5f9" : "#e2e8f0"} />
                <text x={L - 8} y={y(v) + 3.5} textAnchor="end" fontSize={10} fill="#94a3b8">
                  {i ? m.axis(v) : metric === "deals" ? "0" : "₹0"}
                </text>
              </g>
            );
          })}
          {xLabels.map((d) => (
            <text key={d} x={x(d)} y={size.h - 6} textAnchor="middle" fontSize={10} fill="#94a3b8">
              {d}
            </text>
          ))}
          {today !== null && (
            <g>
              <line x1={x(today)} x2={x(today)} y1={T} y2={T + ph} stroke="#038285" strokeDasharray="2 4" opacity={0.5} />
              <text x={x(today)} y={T - 4} textAnchor="middle" fontSize={10} fontWeight={800} fill="#038285">
                Today
              </text>
            </g>
          )}
          {mode === "daily" ? (
            // Daily values jump around too much for a line; bars read better. With a
            // comparison, each day gets a grey bar (that month, or the months' average) beside the teal one.
            (() => {
              const paired = compares.length > 0;
              const width = Math.min(paired ? 9 : 18, slot * (paired ? 0.36 : 0.64));
              const bar = (v: number | null | undefined, cx: number, key: string, fill: string, opacity = 1) =>
                v ? <rect key={key} x={cx} y={y(v)} width={width} height={Math.max(0, y(0) - y(v))} rx={2.5} fill={fill} opacity={opacity} /> : null;
              return Array.from({ length: span }, (_, i) => {
                const day = i + 1;
                const nowX = paired ? x(day) : x(day) - width / 2;
                return (
                  <g key={day}>
                    {paired && bar(avgBefore[i], x(day) - width, `c${day}`, "#cbd5e1")}
                    {bar(now[i], nowX, `n${day}`, selectedDay === day ? "#0A1528" : "#038285", hover === day || selectedDay === day ? 1 : 0.85)}
                  </g>
                );
              });
            })()
          ) : (
            <>
              {befores.map((b, i) => (
                <path
                  key={compares[i].month}
                  d={path(b)}
                  fill="none"
                  stroke={COMPARE_COLORS[i]}
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  strokeLinejoin="round"
                />
              ))}
              <path d={area} fill="url(#insights-area)" />
              <path d={nowPath} fill="none" stroke="#038285" strokeWidth={2.6} strokeLinejoin="round" />
              {lastIdx >= 0 && (
                <circle cx={x(lastIdx + 1)} cy={y(now[lastIdx] ?? 0)} r={4.5} fill="#038285" stroke="#fff" strokeWidth={2} />
              )}
            </>
          )}
          {selectedDay !== null && (
            <g>
              <line x1={x(selectedDay)} x2={x(selectedDay)} y1={T} y2={T + ph} stroke="#0A1528" strokeWidth={1.5} />
              {selectedValue != null && mode === "running" && <circle cx={x(selectedDay)} cy={y(selectedValue)} r={5} fill="#0A1528" stroke="#fff" strokeWidth={2} />}
            </g>
          )}
          {hover !== null && hoverNow !== null && mode === "running" && (
            <circle cx={x(hover)} cy={y(hoverNow)} r={4.5} fill="#fff" stroke="#038285" strokeWidth={2.5} />
          )}
        </svg>

        <div className="absolute flex" style={{ left: L - slot / 2, width: pw + slot, top: T, height: ph }} onMouseLeave={() => setHover(null)}>
          {Array.from({ length: span }, (_, i) => (
            <div
              key={i}
              className={cn("flex-1", i + 1 <= lastDay && "cursor-pointer")}
              onMouseEnter={() => setHover(i + 1)}
              onClick={() => i + 1 <= lastDay && onSelect(selectedDay === i + 1 ? null : i + 1)}
            />
          ))}
        </div>

        {hover !== null && hoverAnchor !== null && (
          <div
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded-xl bg-[#0A1528] px-2.5 py-2 text-[11px] leading-relaxed text-white shadow-lg"
            style={{ left: x(hover), top: y(hoverAnchor), transform: "translate(-50%, calc(-100% - 12px))" }}
          >
            <b className="text-xs">Day {hover}</b>
            <br />
            {hoverNow !== null ? (
              <>
                {monthShort}: <b>{m.format(hoverNow)}</b>
              </>
            ) : (
              <span className="text-slate-300">{monthShort}: not yet</span>
            )}
            {hoverBefores
              .filter((b) => b.value !== null)
              .map((b) => (
                <span key={b.month} className="flex items-center gap-1.5 text-slate-300">
                  <i className="h-1.5 w-1.5 rounded-full" style={{ background: b.color }} />
                  {monthLabel(b.month, true)}: {m.format(b.value as number)}
                </span>
              ))}
          </div>
        )}
      </div>

      {selected ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-3.5 gap-y-1.5 rounded-xl bg-[#f8fafc] px-3 py-2.5 text-xs text-[#334155]">
          <b className="text-[#0A1528]">
            {monthShort} {selected.day}
          </b>
          <span>
            {selected.count ? (
              <>
                <b className="tabular-nums text-[#0A1528]">{formatRupees(selected.total_paise)}</b> from {plural(selected.count, "deal")}
              </>
            ) : (
              "No sales"
            )}
          </span>
          {SOURCE_ORDER.filter((s) => selected.by_source[s]?.count).map((s: DealSource) => (
            <span key={s} className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-[3px]" style={{ background: SOURCE_COLOR[s] }} />
              {SOURCE_LABEL[s]} {selected.by_source[s]?.count}
            </span>
          ))}
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="ml-auto flex items-center gap-1 font-extrabold text-[#64748b] hover:text-[#0A1528]"
          >
            Close <X size={12} />
          </button>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-[#94a3b8]">Click a day in the calendar or the chart to see what sold.</p>
      )}
    </section>
  );
}
