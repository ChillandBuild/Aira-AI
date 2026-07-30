"use client";

import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Download } from "lucide-react";
import { api, ComparePayload, ComparePoint, CompareMetric } from "@/lib/api";
import { RangePicker, RangeValue } from "@/components/analytics/RangePicker";

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
];

// Past a few hundred percent a percentage stops communicating: "+13700%" is
// correct and unreadable. Show a multiple instead, matching the summary text.
const BIG_CHANGE_PCT = 300;

function formatDelta(pct: number): string {
  if (Math.abs(pct) < BIG_CHANGE_PCT) return `${pct >= 0 ? "+" : ""}${pct}%`;
  // pct = (cur - prev) / prev * 100, so the multiple is pct/100 + 1.
  return `${Math.round(Math.abs(pct) / 100 + 1)}×`;
}

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="font-label text-xs text-on-surface-muted">—</span>;
  }
  const up = pct >= 0;
  return (
    <span className={`font-label text-xs font-bold ${up ? "text-emerald-600" : "text-red-600"}`}>
      {up ? "▲" : "▼"} {formatDelta(pct)}
    </span>
  );
}

function ComparisonHeader({ data }: { data: ComparePayload }) {
  return (
    <div className="rounded-card bg-surface p-5 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
      <p className="font-display text-lg font-bold leading-snug text-on-surface sm:text-xl">
        {data.summary_text}
      </p>
      <p className="mt-2 font-label text-xs text-on-surface-muted">
        {data.current.start} → {data.current.end}
        {"  vs  "}
        {data.previous.start} → {data.previous.end}
      </p>
    </div>
  );
}

function ComparisonChart({
  points,
  currentLabel,
  previousLabel,
}: {
  points: ComparePoint[];
  currentLabel: string;
  previousLabel: string;
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
          <Line
            type="monotone" dataKey="previous" name={previousLabel}
            stroke={PREVIOUS_COLOR} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ComparisonTable({ metrics }: { metrics: Record<string, CompareMetric> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-surface-mid">
            {["Metric", "This period", "Previous", "Change"].map((h) => (
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
                <td className="py-3 pr-4 font-label text-sm text-on-surface-muted">
                  {metric.previous.toLocaleString()}
                </td>
                <td className="py-3 pr-4">
                  <DeltaBadge pct={metric.delta_pct} />
                </td>
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
  const [seriesId, setSeriesId] = useState<string>("leads_inbound");
  const [data, setData] = useState<ComparePayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isIncompleteCustom =
    range.preset === "custom" && (!range.start || !range.end);

  useEffect(() => {
    if (isIncompleteCustom) return;
    let isCurrent = true;
    setData(null);
    setErr(null);
    api.analytics
      .compare({ preset: range.preset, start: range.start, end: range.end })
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => {
        if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load");
      });
    return () => { isCurrent = false; };
  }, [range.preset, range.start, range.end, isIncompleteCustom]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <RangePicker value={range} onChange={setRange} />
        <button
          onClick={() =>
            api.analytics.exportCompareCsv({
              preset: range.preset, start: range.start, end: range.end,
            })
          }
          disabled={!data}
          className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-primary px-4 font-label text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {isIncompleteCustom && (
        <p className="font-label text-sm text-on-surface-muted">
          Pick a start and end date to compare.
        </p>
      )}

      {err && (
        <div className="rounded-xl bg-red-50 p-4 font-label text-sm text-red-700 ring-1 ring-red-200">
          {err}
        </div>
      )}

      {!data && !err && !isIncompleteCustom && (
        <div className="h-36 animate-pulse rounded-card bg-surface-mid" />
      )}

      {data && (
        <>
          <ComparisonHeader data={data} />

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
              previousLabel={`${data.previous.start} → ${data.previous.end}`}
            />
          </div>

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="mb-4 font-display text-base font-bold text-primary">
              Every number, side by side
            </h2>
            <ComparisonTable metrics={data.metrics} />
          </div>
        </>
      )}
    </div>
  );
}
