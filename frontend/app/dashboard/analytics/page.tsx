"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  MessageCircle,
  AtSign,
  Tv2,
  Send,
  Filter,
  RefreshCw,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  api,
  MessagingAnalytics,
  TemplatePerformanceRow,
  getAuthHeaders,
} from "@/lib/api";
import { CompareTab } from "./CompareTab";
import { RangePicker, RangeValue } from "@/components/analytics/RangePicker";
import {
  canLoadComparison,
} from "@/components/analytics/periodSelection";

type Tab = "overview" | "channels" | "templates" | "inbound";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://aira-ai-5tfr.onrender.com";

type InboundAnalytics = Awaited<ReturnType<typeof api.analytics.inbound>>;

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function istToday(): Date {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day)));
}

function presetDates(preset: RangeValue["preset"]): { start: string; end: string } | null {
  if (preset === "custom" || preset === "last_7d" || preset === "last_30d") return null;
  const end = istToday();
  const start = new Date(end);

  if (preset === "yesterday") {
    start.setUTCDate(start.getUTCDate() - 1);
    end.setUTCDate(end.getUTCDate() - 1);
  }
  if (preset === "last_14d") start.setUTCDate(start.getUTCDate() - 13);

  return { start: isoDate(start), end: isoDate(end) };
}

function reportingQuery(range: RangeValue): string {
  const params = new URLSearchParams();
  params.set("timezone", "Asia/Kolkata");
  if (range.preset === "custom") {
    params.set("start", range.start);
    params.set("end", range.end);
  } else if (range.preset === "last_7d" || range.preset === "last_30d") {
    params.set("range", range.preset === "last_7d" ? "7d" : "30d");
  } else {
    const dates = presetDates(range.preset);
    if (dates) {
      params.set("start", dates.start);
      params.set("end", dates.end);
    }
  }
  return params.toString();
}

async function fetchAnalytics<T>(path: string): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_URL}${path}`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Failed to load" }));
    throw new Error(body.detail || "Failed to load");
  }
  return response.json();
}

// ─── Shared primitives ────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
      <p className="font-label text-xs text-on-surface-muted uppercase tracking-wider">{label}</p>
      <p className={`mt-1 font-display text-2xl font-bold text-on-surface sm:text-3xl ${valueClass ?? ""}`}>{value}</p>
      {sub && <p className="font-label text-xs text-on-surface-muted">{sub}</p>}
    </div>
  );
}



function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl bg-red-50 text-red-700 font-label text-sm p-4 ring-1 ring-red-200 flex items-center justify-between">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="ml-4 px-3 py-1 rounded-lg bg-red-100 hover:bg-red-200 text-red-700 font-label text-xs font-bold transition-colors">
          Retry
        </button>
      )}
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
      <h2 className="mb-4 font-display text-base font-bold text-primary sm:mb-5">{title}</h2>
      {children}
    </div>
  );
}

// ─── Channels Tab ─────────────────────────────────────────────────────────────

type ChannelFilter = "all" | "whatsapp" | "instagram" | "facebook" | "telegram";

const CHANNEL_OPTIONS: { id: ChannelFilter; label: string; Icon: React.ElementType }[] = [
  { id: "all", label: "All", Icon: MessageCircle },
  { id: "whatsapp", label: "WhatsApp", Icon: MessageCircle },
  { id: "instagram", label: "Instagram", Icon: AtSign },
  { id: "facebook", label: "Facebook", Icon: Tv2 },
  { id: "telegram", label: "Telegram", Icon: Send },
];

function ReplySourceBar({ breakdown }: { breakdown: MessagingAnalytics["reply_source_breakdown"] }) {
  const total =
    breakdown.ai + breakdown.knowledge + breakdown.reengagement + breakdown.manual;
  if (total === 0) return <p className="font-label text-xs text-on-surface-muted">No data</p>;

  const segments = [
    { label: "AI", value: breakdown.ai, color: "bg-primary" },
    { label: "Knowledge Base", value: breakdown.knowledge, color: "bg-blue-400" },
    { label: "Re-engagement", value: breakdown.reengagement, color: "bg-amber-400" },
    { label: "Manual", value: breakdown.manual, color: "bg-[#a8a29e]" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex h-8 rounded-lg overflow-hidden gap-px">
        {segments.map(({ label, value, color }) => {
          const pct = Math.round((value / total) * 100);
          if (pct === 0) return null;
          return (
            <div
              key={label}
              title={`${label}: ${pct}%`}
              className={`${color} flex items-center justify-center transition-all`}
              style={{ width: `${pct}%` }}
            >
              <span className="font-label text-xs text-white font-semibold">{pct}%</span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4">
        {segments.map(({ label, value, color }) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-full ${color} shrink-0`} />
            <span className="font-label text-xs text-on-surface-muted">{label}: {value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChannelsTab({ range, setRange }: { range: RangeValue; setRange: (r: RangeValue) => void }) {
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [data, setData] = useState<MessagingAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const rangeQuery = useMemo(() => reportingQuery(range), [range]);
  const canLoad = canLoadComparison(range, { mode: "off", start: "", end: "" });

  useEffect(() => {
    if (!canLoad) {
      setData(null);
      setErr(null);
      return;
    }
    let isCurrent = true;
    setData(null);
    setErr(null);
    fetchAnalytics<MessagingAnalytics>(
      `/api/v1/analytics/messaging?channel=${encodeURIComponent(channel)}&${rangeQuery}`,
    )
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => { if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { isCurrent = false; };
  }, [canLoad, channel, rangeQuery, retryKey]);

  const handleDownloadCsv = () => {
    if (!data) return;
    const csvContent = "data:text/csv;charset=utf-8," +
      ["Day,Inbound,Outbound", ...data.daily_messages.map(d => `${d.day},${d.inbound},${d.outbound}`)].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `channels_analytics_${channel}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* ── Filter Panel ───────────────────────────────────────── */}
      <div className={cn(
        "overflow-hidden transition-all duration-300 ease-in-out",
        showFilters ? "max-h-64 opacity-100 mb-4" : "max-h-0 opacity-0 mb-0"
      )}>
        <div className="rounded-2xl border border-surface-mid/80 bg-white/95 p-4 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-50 text-violet-700 ring-1 ring-violet-100">
              <Filter size={13} />
            </span>
            <span className="font-label text-[13px] font-bold text-on-surface">Channel Filters</span>
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex flex-col gap-1.5">
              <span className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
                Reporting Period
              </span>
              <div className="w-full sm:w-[390px]">
                <RangePicker value={range} onChange={setRange} idPrefix="channels-range" />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
                Channel
              </span>
              <div className="flex gap-1.5 flex-wrap">
                {CHANNEL_OPTIONS.map(({ id, label, Icon }) => (
                  <button
                    key={id}
                    onClick={() => setChannel(id)}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-label text-xs font-semibold transition-colors ring-1 ${
                      channel === id
                        ? "bg-primary-light text-primary ring-primary-muted"
                        : "bg-surface text-on-surface-muted ring-[#c4c7c7]/15 hover:text-on-surface"
                    }`}
                  >
                    <Icon size={12} />
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {!canLoad && (
        <p className="font-label text-sm text-on-surface-muted">Pick a valid custom reporting period.</p>
      )}

      {err && <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />}

      {canLoad && !err && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-5">
          <div className="md:col-span-4 grid grid-cols-2 lg:grid-cols-4 gap-4">
            {!data ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-5 h-24 animate-pulse">
                  <div className="h-3 w-1/2 bg-surface-mid/60 rounded" />
                  <div className="h-6 w-3/4 bg-surface-mid/60 rounded mt-2" />
                </div>
              ))
            ) : (
              <>
                <KpiCard label="Sent Today" value={data.sent_today.toLocaleString()} />
                <KpiCard label="Received Today" value={data.received_today.toLocaleString()} />
                <KpiCard
                  label="AI Reply Rate"
                  value={data.ai_reply_rate !== null ? `${Math.round(data.ai_reply_rate * 100)}%` : "—"}
                />
                <KpiCard
                  label="AI + KB vs Manual"
                  value={`${data.reply_source_breakdown.ai + data.reply_source_breakdown.knowledge}`}
                  sub={`Manual: ${data.reply_source_breakdown.manual}`}
                />
              </>
            )}
          </div>
          <div className="flex flex-col justify-start gap-2 p-1">
            <div className="flex gap-2">
              <button
                onClick={() => setShowFilters((p) => !p)}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-label text-xs font-bold border transition-all shadow-sm",
                  showFilters
                    ? "bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100"
                    : "bg-white border-surface-mid text-on-surface hover:border-violet-300 hover:text-violet-700"
                )}
              >
                <Filter size={12} />
                <span>Filters</span>
              </button>
              <button
                onClick={() => setRetryKey((k) => k + 1)}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all shadow-sm"
              >
                <RefreshCw size={12} className={!data ? "animate-spin" : ""} />
                <span>Refresh</span>
              </button>
            </div>
            <button
              onClick={handleDownloadCsv}
              disabled={!data}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-xl font-label text-xs font-bold hover:bg-primary/90 transition-all disabled:opacity-40 shadow-sm"
            >
              <Download size={12} />
              <span>Download CSV</span>
            </button>
          </div>
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
          <SectionCard title="Message Volume">
            <div role="img" aria-label="Message volume chart">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.daily_messages} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
                  <Line type="monotone" dataKey="inbound" stroke="#3b82f6" strokeWidth={2} dot={false} name="Inbound" />
                  <Line type="monotone" dataKey="outbound" stroke="#10b981" strokeWidth={2} dot={false} name="Outbound" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          <SectionCard title="Reply Source Split">
            <ReplySourceBar breakdown={data.reply_source_breakdown} />
          </SectionCard>
        </div>
      )}
    </div>
  );
}

// ─── Templates Tab ────────────────────────────────────────────────────────────

function pct(part: number, whole: number): string {
  if (!whole) return "—";
  return `${Math.round((part / whole) * 100)}%`;
}

function TemplatesTab({ range, setRange }: { range: RangeValue; setRange: (r: RangeValue) => void }) {
  const [rows, setRows] = useState<TemplatePerformanceRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const rangeQuery = useMemo(() => reportingQuery(range), [range]);

  useEffect(() => {
    setErr(null);
    setRows(null);
    api.analytics
      .templatePerformance(rangeQuery)
      .then(setRows)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : "Failed to load"));
  }, [retryKey, rangeQuery]);

  const totals = (rows ?? []).reduce(
    (acc, r) => ({
      sent: acc.sent + r.sent,
      read: acc.read + r.read,
      replied: acc.replied + r.replied,
      hot: acc.hot + r.hot_leads,
    }),
    { sent: 0, read: 0, replied: 0, hot: 0 },
  );

  const handleDownloadCsv = () => {
    if (!rows) return;
    const csvContent = "data:text/csv;charset=utf-8," +
      ["Template,Broadcasts,Sent,Read,Replied,Hot Leads,Last Sent", ...rows.map(r => `"${r.template_name}",${r.broadcasts},${r.sent},${r.read},${r.replied},${r.hot_leads},"${r.last_sent ?? ''}"`)].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `template_performance.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {showFilters ? (
        <div className="rounded-2xl border border-surface-mid/80 bg-white/95 p-4 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-50 text-violet-700 ring-1 ring-violet-100">
              <Filter size={13} />
            </span>
            <div>
              <span className="block font-label text-[13px] font-bold text-on-surface">Reporting period</span>
              <span className="block font-body text-[10px] text-on-surface-muted">Choose the template performance period.</span>
            </div>
          </div>
          <RangePicker value={range} onChange={setRange} idPrefix="templates-range" />
        </div>
      ) : null}
      {/* KPI Cards & Actions Grid */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-5">
        <div className="md:col-span-4 grid grid-cols-2 lg:grid-cols-4 gap-4">
          {!rows ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-5 h-24 animate-pulse">
                <div className="h-3 w-1/2 bg-surface-mid/60 rounded" />
                <div className="h-6 w-3/4 bg-surface-mid/60 rounded mt-2" />
              </div>
            ))
          ) : (
            <>
              <KpiCard label="Total Sent" value={totals.sent.toLocaleString()} />
              <KpiCard label="Read Rate" value={pct(totals.read, totals.sent)} sub={`${totals.read.toLocaleString()} read`} />
              <KpiCard label="Reply Rate" value={pct(totals.replied, totals.sent)} sub={`${totals.replied.toLocaleString()} replied`} />
              <KpiCard label="Hot Leads" value={totals.hot.toLocaleString()} />
            </>
          )}
        </div>
        <div className="flex flex-col justify-start gap-2 p-1">
          <div className="flex gap-2">
            <button
              onClick={() => setShowFilters((p) => !p)}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-label text-xs font-bold border transition-all shadow-sm",
                showFilters
                  ? "bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100"
                  : "bg-white border-surface-mid text-on-surface hover:border-violet-300 hover:text-violet-700"
              )}
            >
              <Filter size={12} />
              <span>Filters</span>
            </button>
            <button
              onClick={() => setRetryKey((k) => k + 1)}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all shadow-sm"
            >
              <RefreshCw size={12} className={!rows ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
          </div>
          <button
            onClick={handleDownloadCsv}
            disabled={!rows}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-xl font-label text-xs font-bold hover:bg-primary/90 transition-all disabled:opacity-40 shadow-sm"
          >
            <Download size={12} />
            <span>Download CSV</span>
          </button>
        </div>
      </div>

      {err && <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />}

      {rows && (
        <SectionCard title="Template Performance">
          {rows.length === 0 ? (
            <p className="font-label text-sm text-on-surface-muted">
              No broadcasts sent yet. Performance appears here once templates go out.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-surface-mid">
                    {["Template", "Broadcasts", "Sent", "Read", "Replied", "Hot Leads", "Last Sent"].map((h) => (
                      <th key={h} className="pb-3 pr-4 font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.template_name} className="border-b border-surface-mid/50 hover:bg-surface-low transition-colors">
                      <td className="py-3 pr-4 font-body text-sm font-semibold text-on-surface">{r.template_name}</td>
                      <td className="py-3 pr-4 font-label text-sm text-on-surface">{r.broadcasts}</td>
                      <td className="py-3 pr-4 font-label text-sm text-on-surface">{r.sent.toLocaleString()}</td>
                      <td className="py-3 pr-4 font-label text-sm text-on-surface">
                        {r.read.toLocaleString()} <span className="text-on-surface-muted">({pct(r.read, r.sent)})</span>
                      </td>
                      <td className="py-3 pr-4 font-label text-sm text-on-surface">
                        {r.replied.toLocaleString()} <span className="text-on-surface-muted">({pct(r.replied, r.sent)})</span>
                      </td>
                      <td className="py-3 pr-4 font-label text-sm font-bold text-emerald-600">{r.hot_leads.toLocaleString()}</td>
                      <td className="py-3 font-label text-sm text-on-surface-muted">
                        {r.last_sent ? new Date(r.last_sent).toLocaleDateString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      )}
    </div>
  );
}

// ─── Inbound Tab ─────────────────────────────────────────────────────────────

function InboundTab({ range, setRange }: { range: RangeValue; setRange: (r: RangeValue) => void }) {
  const [data, setData] = useState<InboundAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const rangeQuery = useMemo(() => reportingQuery(range), [range]);
  const canLoad = canLoadComparison(range, { mode: "off", start: "", end: "" });

  useEffect(() => {
    if (!canLoad) {
      setData(null);
      setErr(null);
      return;
    }
    let isCurrent = true;
    setData(null);
    setErr(null);
    fetchAnalytics<InboundAnalytics>(`/api/v1/analytics/inbound?${rangeQuery}`)
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e) => { if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { isCurrent = false; };
  }, [canLoad, rangeQuery, retryKey]);

  const handleDownloadCsv = () => {
    if (!data) return;
    const csvContent = "data:text/csv;charset=utf-8," +
      ["Day,Organic,Ad", ...data.daily.map(d => `${d.day},${d.organic},${d.ad}`)].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `inbound_analytics.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* ── Filter Panel ───────────────────────────────────────── */}
      <div className={cn(
        "overflow-hidden transition-all duration-300 ease-in-out",
        showFilters ? "max-h-64 opacity-100 mb-4" : "max-h-0 opacity-0 mb-0"
      )}>
        <div className="rounded-2xl border border-surface-mid/80 bg-white/95 p-4 shadow-sm">
          <div className="mb-2.5 flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-50 text-violet-700 ring-1 ring-violet-100">
              <Filter size={13} />
            </span>
            <span className="font-label text-[13px] font-bold text-on-surface">Inbound Filters</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
              Reporting Period
            </span>
            <div className="w-full sm:w-[390px]">
              <RangePicker value={range} onChange={setRange} idPrefix="inbound-range" />
            </div>
          </div>
        </div>
      </div>

      {!canLoad && (
        <p className="font-label text-sm text-on-surface-muted">Pick a valid custom reporting period.</p>
      )}

      {err && <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />}

      {canLoad && !err && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-5">
          <div className="md:col-span-4 grid grid-cols-2 lg:grid-cols-3 gap-4">
            {!data ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-5 h-24 animate-pulse">
                  <div className="h-3 w-1/2 bg-surface-mid/60 rounded" />
                  <div className="h-6 w-3/4 bg-surface-mid/60 rounded mt-2" />
                </div>
              ))
            ) : (
              <>
                <KpiCard label="New Leads Today" value={data.kpis.today.total.toLocaleString()} sub={`Organic ${data.kpis.today.organic} · Ad ${data.kpis.today.ad}`} />
                <KpiCard label="New Leads (range)" value={data.kpis.range.total.toLocaleString()} sub={`Organic ${data.kpis.range.organic} · Ad ${data.kpis.range.ad}`} />
                <KpiCard label="Ad Share" value={`${data.kpis.range.total ? Math.round((data.kpis.range.ad / data.kpis.range.total) * 100) : 0}%`} sub="of inbound in range" />
              </>
            )}
          </div>
          <div className="flex flex-col justify-start gap-2 p-1">
            <div className="flex gap-2">
              <button
                onClick={() => setShowFilters((p) => !p)}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl font-label text-xs font-bold border transition-all shadow-sm",
                  showFilters
                    ? "bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100"
                    : "bg-white border-surface-mid text-on-surface hover:border-violet-300 hover:text-violet-700"
                )}
              >
                <Filter size={12} />
                <span>Filters</span>
              </button>
              <button
                onClick={() => setRetryKey((k) => k + 1)}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all shadow-sm"
              >
                <RefreshCw size={12} className={!data ? "animate-spin" : ""} />
                <span>Refresh</span>
              </button>
            </div>
            <button
              onClick={handleDownloadCsv}
              disabled={!data}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-xl font-label text-xs font-bold hover:bg-primary/90 transition-all disabled:opacity-40 shadow-sm"
            >
              <Download size={12} />
              <span>Download CSV</span>
            </button>
          </div>
        </div>
      )}

      {data && (
        <>
          <SectionCard title="Daily Inbound — Organic vs Ad">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.daily}>
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="organic" stackId="a" fill="#10b981" name="Organic" />
                <Bar dataKey="ad" stackId="a" fill="#5b21b6" name="Ad" />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>

          <SectionCard title="By Channel">
            <div className="space-y-2">
              {([["whatsapp", "WhatsApp"], ["instagram", "Instagram"], ["facebook", "Facebook"], ["telegram", "Telegram"]] as const).map(([k, label]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span className="text-on-surface-muted">{label}</span>
                  <span className="font-medium">{data.by_channel[k]}</span>
                </div>
              ))}
            </div>
          </SectionCard>
        </>
      )}
    </div>
  );
}

// ─── Page shell ───────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: "channels", label: "Channels" },
  { id: "overview", label: "Overview" },
  { id: "inbound", label: "Inbound" },
  { id: "templates", label: "Templates" },
];

export default function AnalyticsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab: Tab = (rawTab === "overview" || rawTab === "channels" || rawTab === "inbound" || rawTab === "templates")
    ? rawTab
    : "channels";

  const setActiveTab = (newTab: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    if (newTab === "channels") params.delete("tab");
    else params.set("tab", newTab);
    router.replace(`/dashboard/analytics?${params.toString()}`, { scroll: false });
  };

  const [range, setRange] = useState<RangeValue>({
    preset: "last_7d", start: "", end: "",
  });
  return (
    <div className="min-w-0">
      <div className="-mx-1 mb-5 overflow-x-auto px-1 pb-1">
        <nav className="flex w-max gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              aria-pressed={activeTab === tab.id}
              className={`shrink-0 rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-5 sm:text-sm ${
                activeTab === tab.id
                  ? "bg-surface text-primary shadow-card"
                  : "text-on-surface-muted hover:text-on-surface"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === "overview" && (
        <CompareTab
          range={range}
          setRange={setRange}
        />
      )}
      {activeTab === "channels" && <ChannelsTab range={range} setRange={setRange} />}
      {activeTab === "inbound" && <InboundTab range={range} setRange={setRange} />}
      {activeTab === "templates" && <TemplatesTab range={range} setRange={setRange} />}
    </div>
  );
}
