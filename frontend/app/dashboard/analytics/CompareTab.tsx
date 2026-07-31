"use client";

import { useEffect, useState, useMemo } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Download } from "lucide-react";
import {
  api, CompareParams, ComparePayload, ComparePeriod, ComparePoint, CompareMetric, CompareMovement,
} from "@/lib/api";
import { RangePicker, RangeValue } from "@/components/analytics/RangePicker";
import { ComparisonPicker } from "@/components/analytics/ComparisonPicker";
import { canLoadComparison, ComparisonSelection } from "@/components/analytics/periodSelection";

const CURRENT_COLOR = "#5b21b6";
const PREVIOUS_COLOR = "#a8a29e";

const SERIES_OPTIONS: { id: string; label: string }[] = [
  { id: "leads_inbound", label: "Inbound Leads" },
  { id: "leads_outbound", label: "Outbound Leads" },
  { id: "messages_in", label: "Messages Received" },
  { id: "messages_out", label: "Messages Sent" },
];

const TABLE_ROWS: { key: string; label: string }[] = [
  { key: "new_leads", label: "New leads" },
  { key: "inbound_leads", label: "— came to us" },
  { key: "outbound_leads", label: "— we reached out" },
  { key: "hot", label: "Hot leads" },
  { key: "warm", label: "Warm leads" },
  { key: "cold", label: "Cold leads" },
  { key: "disqualified", label: "Disqualified" },
  { key: "avg_score", label: "Average score" },
  { key: "messages_in", label: "Messages received" },
  { key: "messages_out", label: "Messages sent" },
  { key: "ai_replies", label: "— sent by AI" },
  { key: "human_replies", label: "— sent by a human" },
  { key: "converted", label: "Conversions" },
  { key: "engagement_rate", label: "Engagement rate (% of leads replied to)" },
];

// Past a few hundred percent a percentage stops communicating: "+13700%" is
// correct and unreadable. Show a multiple instead, matching the summary text.
const BIG_CHANGE_PCT = 300;

function formatDelta(pct: number): string {
  if (Math.abs(pct) < BIG_CHANGE_PCT) return `${pct >= 0 ? "+" : ""}${pct}%`;
  // pct = (cur - prev) / prev * 100, so the multiple is pct/100 + 1.
  return `${Math.round(Math.abs(pct) / 100 + 1)}×`;
}

/** How a change should be coloured.
 *  `higher` — more is good (leads, replies answered).
 *  `lower`  — less is good (cost per lead, reply time).
 *  `neutral`— neither direction is good or bad. Ad spend is the case that
 *             matters: spending less is not a win and spending more is not a
 *             failure, so painting it green or red editorialises a decision
 *             the owner made deliberately. */
type DeltaSense = "higher" | "lower" | "neutral";

/** The arrow always follows the number; only the colour follows the sense. */
function DeltaBadge({
  pct,
  sense = "higher",
}: {
  pct: number | null;
  sense?: DeltaSense;
}) {
  if (pct === null) {
    return <span className="font-label text-xs text-on-surface-muted">—</span>;
  }
  const up = pct >= 0;
  const tone =
    sense === "neutral"
      ? "text-on-surface-muted"
      : (sense === "lower" ? !up : up)
        ? "text-emerald-600"
        : "text-red-600";
  return (
    <span className={`font-label text-xs font-bold ${tone}`}>
      {up ? "▲" : "▼"} {formatDelta(pct)}
    </span>
  );
}

function money(n: number | null | undefined): string {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function seconds(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 60) return `${Math.round(n)}s`;
  if (n < 3600) return `${Math.round(n / 60)}m`;
  return `${(n / 3600).toFixed(1)}h`;
}

function StatCard({
  label,
  value,
  sub,
  delta,
  sense,
}: {
  label: string;
  value: string;
  sub?: string;
  delta?: number | null;
  sense?: DeltaSense;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15">
      <p className="font-label text-xs uppercase tracking-wider text-on-surface-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold text-on-surface">{value}</p>
      <div className="flex items-center gap-2">
        {delta !== undefined && <DeltaBadge pct={delta ?? null} sense={sense} />}
        {sub && <span className="font-label text-xs text-on-surface-muted">{sub}</span>}
      </div>
    </div>
  );
}

const SEGMENT_LABEL: Record<string, string> = {
  A: "Hot", B: "Warm", C: "Cold", D: "Disqualified",
};

function MovementFlows({ flows }: { flows: CompareMovement["flows"] }) {
  if (flows.length === 0) {
    return (
      <p className="font-label text-sm text-on-surface-muted">
        No leads changed segment in this period.
      </p>
    );
  }
  const max = Math.max(...flows.map((f) => f.total), 1);
  const RANK: Record<string, number> = { D: 0, C: 1, B: 2, A: 3 };

  return (
    <div className="space-y-2.5">
      {flows.map((f) => {
        const up = (RANK[f.to] ?? 0) > (RANK[f.from] ?? 0);
        return (
          <div key={`${f.from}-${f.to}`} className="flex items-center gap-3">
            <span className="w-36 shrink-0 font-label text-xs text-on-surface-muted">
              {SEGMENT_LABEL[f.from] ?? f.from} → {SEGMENT_LABEL[f.to] ?? f.to}
            </span>
            <div className="h-4 flex-1 overflow-hidden rounded-full bg-surface-mid">
              <div
                className={`h-4 rounded-full ${up ? "bg-emerald-500" : "bg-red-400"}`}
                style={{ width: `${Math.round((f.total / max) * 100)}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right font-label text-xs font-semibold text-on-surface">
              {f.total}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const SEGMENT_MIX_COLORS = {
  hot: "#10b981", warm: "#3b82f6", cold: "#f59e0b", disqualified: "#f87171",
} as const;

function SegmentMixChart({
  points,
}: {
  points: ComparePeriod["daily_segment_mix"];
}) {
  if (!points || points.length === 0) {
    return (
      <p className="font-label text-sm text-on-surface-muted">
        No lead activity in this period.
      </p>
    );
  }
  return (
    <div role="img" aria-label="Lead quality mix per day">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="hot" stackId="mix" fill={SEGMENT_MIX_COLORS.hot} name="Hot" />
          <Bar dataKey="warm" stackId="mix" fill={SEGMENT_MIX_COLORS.warm} name="Warm" />
          <Bar dataKey="cold" stackId="mix" fill={SEGMENT_MIX_COLORS.cold} name="Cold" />
          <Bar dataKey="disqualified" stackId="mix" fill={SEGMENT_MIX_COLORS.disqualified} name="Disqualified" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function LeadHeatmap({ points }: { points: ComparePeriod["heatmap"] }) {
  const lookup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const p of points ?? []) m[`${p.dow}-${p.hour}`] = p.total;
    return m;
  }, [points]);
  const max = Math.max(1, ...(points ?? []).map((p) => p.total));

  if (!points || points.length === 0) {
    return (
      <p className="font-label text-sm text-on-surface-muted">
        No inbound leads in this period.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: "40px repeat(24, 20px)" }}>
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <div key={h} className="text-center font-label text-[9px] text-on-surface-muted">
            {h % 3 === 0 ? h : ""}
          </div>
        ))}
        {DOW_LABELS.map((label, dow) => (
          <div key={label} className="contents">
            <div className="flex items-center font-label text-[9px] text-on-surface-muted">{label}</div>
            {Array.from({ length: 24 }, (_, hour) => {
              const count = lookup[`${dow}-${hour}`] ?? 0;
              const intensity = count === 0 ? 0 : 0.15 + 0.85 * (count / max);
              return (
                <div
                  key={hour}
                  title={`${label} ${hour}:00 — ${count} lead${count === 1 ? "" : "s"}`}
                  className="h-5 w-5 rounded-sm"
                  style={{ backgroundColor: `rgba(91, 33, 182, ${intensity})` }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ComparisonHeader({ data }: { data: ComparePayload }) {
  const hasComparison = data.previous !== null;
  return (
    <div className="rounded-card bg-surface p-5 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
      <p className="font-display text-lg font-bold leading-snug text-on-surface sm:text-xl">
        {hasComparison ? data.summary_text ?? "Period comparison" : "Selected period"}
      </p>
      <p className="mt-2 font-label text-xs text-on-surface-muted">
        {data.current.start} → {data.current.end}
        {data.previous !== null && `  vs  ${data.previous.start} → ${data.previous.end}`}
      </p>
    </div>
  );
}

export function shouldRenderComparisonChart(previous: ComparePeriod | null): boolean {
  return previous !== null;
}

function ComparisonChart({
  points,
  currentLabel,
  previousLabel,
}: {
  points: ComparePoint[];
  currentLabel: string;
  previousLabel?: string;
}) {
  return (
    <div role="img" aria-label="Period comparison chart">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone" dataKey="current" name={currentLabel}
            stroke={CURRENT_COLOR} strokeWidth={2.5} dot={false} connectNulls
          />
          {previousLabel && (
            <Line
              type="monotone" dataKey="previous" name={previousLabel}
              stroke={PREVIOUS_COLOR} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ComparisonTable({
  metrics,
  hasComparison,
}: {
  metrics: Record<string, CompareMetric>;
  hasComparison: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-surface-mid">
            {["Metric", "This period", ...(hasComparison ? ["Previous", "Change"] : [])].map((h) => (
              <th
                key={h}
                className="pb-3 pr-4 font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {TABLE_ROWS.map((row) => {
            const metric = metrics[row.key];
            if (!metric) return null;
            return (
              <tr key={row.key} className="border-b border-surface-mid/50">
                <td className="py-3 pr-4 font-body text-sm text-on-surface">{row.label}</td>
                <td className="py-3 pr-4 font-display text-sm font-bold text-on-surface">
                  {metric.current.toLocaleString()}
                </td>
                {hasComparison && (
                  <>
                    <td className="py-3 pr-4 font-label text-sm text-on-surface-muted">
                      {metric.previous.toLocaleString()}
                    </td>
                    <td className="py-3 pr-4">
                      <DeltaBadge pct={metric.delta_pct} />
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function CompareTab() {
  const [range, setRange] = useState<RangeValue>({
    preset: "last_14d", start: "", end: "",
  });
  const [comparison, setComparison] = useState<ComparisonSelection>({
    mode: "off", start: "", end: "",
  });
  const [seriesId, setSeriesId] = useState<string>("leads_inbound");
  const [data, setData] = useState<ComparePayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const canLoad = canLoadComparison(range, comparison);

  const params = useMemo<CompareParams>(() => {
    const reporting = { preset: range.preset, start: range.start, end: range.end };
    if (comparison.mode === "custom") {
      return {
        ...reporting,
        comparison: "custom",
        comparison_start: comparison.start,
        comparison_end: comparison.end,
      };
    }
    return { ...reporting, comparison: comparison.mode };
  }, [range.preset, range.start, range.end, comparison.mode, comparison.start, comparison.end]);

  useEffect(() => {
    // Clear before bailing out, otherwise switching to Custom leaves the
    // previous range's report on screen under a "pick a date" prompt --
    // stale numbers presented as if they were the current selection.
    if (!canLoad) {
      setData(null);
      setErr(null);
      return;
    }
    let isCurrent = true;
    setData(null);
    setErr(null);
    api.analytics
      .compare(params)
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => {
        if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load");
      });
    return () => { isCurrent = false; };
  }, [canLoad, params]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-col gap-5">
          <div>
            <p className="mb-3 font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted">
              Reporting period
            </p>
            <RangePicker value={range} onChange={setRange} idPrefix="reporting-range" />
          </div>
          <ComparisonPicker value={comparison} onChange={setComparison} />
        </div>
        <button
          onClick={() => api.analytics.exportCompareCsv(params)}
          disabled={!data || !canLoad || comparison.mode === "off"}
          className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-primary px-4 font-label text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {!canLoad && (
        <p className="font-label text-sm text-on-surface-muted">
          Pick a valid start and end date for each custom period.
        </p>
      )}

      {err && (
        <div className="rounded-xl bg-red-50 p-4 font-label text-sm text-red-700 ring-1 ring-red-200">
          {err}
        </div>
      )}

      {!data && !err && canLoad && (
        <div className="h-36 animate-pulse rounded-card bg-surface-mid" />
      )}

      {data && (
        <>
          <ComparisonHeader data={data} />

          {(() => {
            const previous = data.previous;
            const hasComparison = shouldRenderComparisonChart(previous);
            return (
              <>

          {/* Money — the question an owner actually asks. Cost metrics use
              sense="lower" so a rise never renders as good news; ad spend is
              neutral because neither spending more nor less is a result. */}
          {(data.current.money.spend ?? 0) > 0 && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
              <StatCard
                label="Ad spend"
                value={money(data.current.money.spend)}
                delta={hasComparison ? data.money_metrics.spend?.delta_pct : undefined}
                sense="neutral"
                sub={previous ? `was ${money(previous.money.spend)}` : undefined}
              />
              <StatCard
                label="Cost per lead"
                value={money(data.current.money.cost_per_lead)}
                delta={hasComparison ? data.money_metrics.cost_per_lead?.delta_pct : undefined}
                sense="lower"
                sub={previous ? `was ${money(previous.money.cost_per_lead)}` : undefined}
              />
              <StatCard
                label="Cost per hot lead"
                value={money(data.current.money.cost_per_hot_lead)}
                delta={hasComparison ? data.money_metrics.cost_per_hot_lead?.delta_pct : undefined}
                sense="lower"
                sub={previous ? `was ${money(previous.money.cost_per_hot_lead)}` : undefined}
              />
              <StatCard
                label="Ad-attributed leads"
                value={(data.current.money.ad_leads ?? 0).toLocaleString()}
                delta={hasComparison ? data.money_metrics.ad_leads?.delta_pct : undefined}
                sub={`${data.current.money.ad_hot_leads ?? 0} hot`}
              />
            </div>
          )}

          {/* Response speed — previously hardcoded to null and never shown. */}
          {(data.current.response.inbound_total ?? 0) > 0 && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
              <StatCard
                label="Typical reply time"
                value={seconds(data.current.response.p50_seconds)}
                delta={hasComparison ? data.response_metrics.p50_seconds?.delta_pct : undefined}
                sense="lower"
                sub="median"
              />
              <StatCard
                label="Slowest 10%"
                value={seconds(data.current.response.p90_seconds)}
                delta={hasComparison ? data.response_metrics.p90_seconds?.delta_pct : undefined}
                sense="lower"
                sub="90th percentile"
              />
              <StatCard
                label="Messages answered"
                value={(data.current.response.answered ?? 0).toLocaleString()}
                sub={`of ${(data.current.response.inbound_total ?? 0).toLocaleString()} received`}
              />
              <StatCard
                label="Leads warmed up"
                value={data.current.movement.promoted.toLocaleString()}
                delta={hasComparison ? data.movement_metrics.promoted?.delta_pct : undefined}
                sub={`${data.current.movement.promoted_to_hot} became hot`}
              />
            </div>
          )}

          {/* What the AI did -- straight from lead_stage_events. */}
          {data.current.movement.flows.length > 0 && (
            <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
              <h2 className="font-display text-base font-bold text-primary">
                What the AI did with your leads
              </h2>
              <p className="mb-4 mt-1 font-label text-xs text-on-surface-muted">
                The AI moved {data.current.movement.promoted} leads up and{" "}
                {data.current.movement.demoted} down.{" "}
                {data.current.movement.promoted_to_hot} became hot leads.
              </p>
              <MovementFlows flows={data.current.movement.flows} />
            </div>
          )}

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="font-display text-base font-bold text-primary">
              Lead quality mix, day by day
            </h2>
            <p className="mb-4 mt-1 font-label text-xs text-on-surface-muted">
              How many leads landed in each segment on the day they arrived.
            </p>
            <SegmentMixChart points={data.current.daily_segment_mix} />
          </div>

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="font-display text-base font-bold text-primary">
              When leads reach out (IST)
            </h2>
            <p className="mb-4 mt-1 font-label text-xs text-on-surface-muted">
              Inbound leads by day of week and hour.
            </p>
            <LeadHeatmap points={data.current.heatmap} />
          </div>

          {hasComparison && previous && (
            <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
              <div className="mb-4 flex flex-wrap gap-2">
                {SERIES_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setSeriesId(option.id)}
                    className={`rounded-lg px-3 py-1.5 font-label text-xs font-semibold ring-1 transition-colors ${
                      seriesId === option.id
                        ? "bg-primary-light text-primary ring-primary-muted"
                        : "bg-surface text-on-surface-muted ring-[#c4c7c7]/15 hover:text-on-surface"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <ComparisonChart
                points={data.series[seriesId] ?? []}
                currentLabel={`${data.current.start} → ${data.current.end}`}
                previousLabel={`${previous.start} → ${previous.end}`}
              />
            </div>
          )}

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="mb-4 font-display text-base font-bold text-primary">
              {hasComparison ? "Every number, side by side" : "Selected-period metrics"}
            </h2>
            <ComparisonTable metrics={data.metrics} hasComparison={hasComparison} />
          </div>
              </>
            );
          })()}

        </>
      )}
    </div>
  );
}
