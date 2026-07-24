"use client";
import { useMemo, type ReactNode } from "react";
import { MetaAdsAnalytics } from "@/lib/api";
import { useMetaAdsAnalytics } from "@/hooks/useApi";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, AreaChart, Area, ScatterChart, Scatter, ZAxis, PieChart, Pie, Cell, Legend,
} from "recharts";

type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};

const VIOLET = "#5b21b6";
const VIOLET_SHADES = ["#5b21b6", "#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];
const RED = "#e5484d";
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function Card({ title, children, sub }: { title: string; children: ReactNode; sub?: string }) {
  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-primary mb-1">{title}</h2>
      {sub && <p className="font-label text-xs text-on-surface-muted mb-4">{sub}</p>}
      {children}
    </div>
  );
}

export function MetaAdsAnalyticsTab({ dateFrom, dateTo, setDateFrom, setDateTo }: Props) {
  const { data } = useMetaAdsAnalytics({ date_from: dateFrom || undefined, date_to: dateTo || undefined });
  const a: MetaAdsAnalytics | undefined = data?.data;

  // Heatmap max for shading intensity
  const heatMax = useMemo(() => Math.max(1, ...(a?.heatmap ?? []).map((h) => h.qualified)), [a]);
  const heatLookup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const h of a?.heatmap ?? []) m[`${h.dow}-${h.hour}`] = h.qualified;
    return m;
  }, [a]);

  // Leaderboard: worst (first) gets red, rest violet
  const leaderboard = a?.leaderboard ?? [];

  return (
    <div className="space-y-6">
      {/* Date filters */}
      <div className="flex flex-wrap items-end gap-2.5">
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {([
          { label: "SPEND", value: money(a?.kpis.spend), highlight: false },
          { label: "MESSAGES", value: (a?.kpis.messages ?? 0).toLocaleString("en-IN"), highlight: false },
          { label: "QUALIFIED", value: (a?.kpis.qualified ?? 0).toLocaleString("en-IN"), highlight: false },
          { label: "COST / HOT LEAD", value: money(a?.kpis.cost_per_hot), highlight: true },
        ] as { label: string; value: string; highlight: boolean }[]).map((k) => (
          <div key={k.label} className={cnCard(k.highlight)}>
            <div className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">{k.label}</div>
            <div className={`text-xl font-bold mt-1 ${k.highlight ? "text-primary" : "text-on-surface"}`}>{k.value}</div>
          </div>
        ))}
        <div className="rounded-card p-4 bg-surface-low/40 ring-1 ring-[#c4c7c7]/15 opacity-70">
          <div className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">ROAS</div>
          <div className="text-xs mt-1 text-on-surface-muted">Needs revenue tracking — not built yet</div>
        </div>
      </div>

      {/* Funnel + Leaderboard */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Lead funnel" sub="Where ad-driven leads drop off">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={a?.funnel ?? []} layout="vertical" margin={{ left: 20, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#a8a29e" }} />
              <YAxis type="category" dataKey="stage" tick={{ fontSize: 11, fill: "#78716c" }} width={70} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} fill={VIOLET} name="Leads" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Creative leaderboard" sub="Cost per hot lead — lower is better">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={leaderboard} layout="vertical" margin={{ left: 20, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#a8a29e" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#78716c" }} width={90} />
              <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Bar dataKey="cost_per_hot" radius={[0, 4, 4, 0]} name="Cost/hot">
                {leaderboard.map((_, i) => <Cell key={i} fill={i === 0 ? RED : VIOLET} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Trend: qualified line (primary) + spend area (separate, same time axis, own scale) */}
      <Card title="Qualified leads per day" sub="Ad-driven qualified leads over time">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={a?.trend ?? []} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#a8a29e" }} />
            <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} allowDecimals={false} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
            <Line type="monotone" dataKey="qualified" stroke={VIOLET} strokeWidth={2} dot={false} name="Qualified leads" />
          </LineChart>
        </ResponsiveContainer>
        <p className="font-label text-[11px] text-on-surface-muted mt-2 mb-1">Spend per day (₹)</p>
        <ResponsiveContainer width="100%" height={80}>
          <AreaChart data={a?.trend ?? []} margin={{ top: 0, right: 8, bottom: 0, left: -10 }}>
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fontSize: 9, fill: "#a8a29e" }} width={40} />
            <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
            <Area type="monotone" dataKey="spend" stroke="#c4b5fd" fill="#ede9fe" name="Spend" />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Heatmap */}
      <Card title="When leads qualify" sub="Qualified leads by day × hour (IST) — darker = more">
        <div className="overflow-x-auto">
          <div className="min-w-[560px]">
            <div className="grid" style={{ gridTemplateColumns: `40px repeat(24, 1fr)`, gap: 2 }}>
              <div />
              {Array.from({ length: 24 }).map((_, h) => (
                <div key={h} className="text-[8px] text-center text-on-surface-muted">{h % 3 === 0 ? h : ""}</div>
              ))}
              {DOW.map((label, dow) => (
                <FragmentRow key={dow} label={label} dow={dow} heatLookup={heatLookup} heatMax={heatMax} />
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Quadrant + Donut */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Spend efficiency" sub="Bottom-left = scale up · top-right = cut or fix">
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 10, right: 16, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
              <XAxis type="number" dataKey="spend" name="Spend" tick={{ fontSize: 10, fill: "#a8a29e" }}
                tickFormatter={(v) => money(v)} />
              <YAxis type="number" dataKey="cost_per_hot" name="Cost/hot" tick={{ fontSize: 10, fill: "#a8a29e" }}
                tickFormatter={(v) => money(v)} />
              <ZAxis type="number" dataKey="hot" range={[60, 400]} name="Hot" />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v) => money(Number(v))}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Scatter data={(a?.quadrant ?? []).filter((q) => q.cost_per_hot != null)} fill={VIOLET} fillOpacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Spend distribution" sub="Where budget is going">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={a?.spend_distribution ?? []} dataKey="spend" nameKey="name"
                innerRadius={55} outerRadius={90} paddingAngle={2}>
                {(a?.spend_distribution ?? []).map((_, i) => (
                  <Cell key={i} fill={VIOLET_SHADES[i % VIOLET_SHADES.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}

function cnCard(highlight?: boolean) {
  return `rounded-card p-4 bg-surface ring-1 ${highlight ? "ring-primary/40" : "ring-[#c4c7c7]/15"} shadow-card`;
}

function FragmentRow({ label, dow, heatLookup, heatMax }:
  { label: string; dow: number; heatLookup: Record<string, number>; heatMax: number }) {
  return (
    <>
      <div className="text-[9px] text-on-surface-muted flex items-center">{label}</div>
      {Array.from({ length: 24 }).map((_, hour) => {
        const v = heatLookup[`${dow}-${hour}`] ?? 0;
        const alpha = v === 0 ? 0.04 : 0.15 + 0.85 * (v / heatMax);
        return (
          <div key={hour} title={`${label} ${hour}:00 — ${v} qualified`}
            className="h-4 rounded-sm" style={{ backgroundColor: `rgba(91,33,182,${alpha})` }} />
        );
      })}
    </>
  );
}
