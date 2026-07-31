"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AreaChart,
  Area,
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
} from "lucide-react";
import {
  api,
  CompareParams,
  ComparePayload,
  MessagingAnalytics,
  TemplatePerformanceRow,
  StaleHotLead,
  getAuthHeaders,
} from "@/lib/api";
import { CompareTab } from "./CompareTab";
import { RangePicker, RangeValue } from "@/components/analytics/RangePicker";
import { ComparisonPicker } from "@/components/analytics/ComparisonPicker";
import {
  canLoadComparison,
  ComparisonSelection,
} from "@/components/analytics/periodSelection";
import {
  attentionLeadHref,
  attentionScopeLabel,
  buildOverviewPresentation,
  FunnelStep,
  PerformanceCard,
} from "./overviewPresentation";

type Tab = "overview" | "channels" | "templates" | "inbound" | "compare";

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

  if (preset === "this_month") start.setUTCDate(1);
  if (preset === "last_month") {
    start.setUTCMonth(start.getUTCMonth() - 1, 1);
    end.setUTCDate(0);
  }
  if (preset === "this_week") start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
  if (preset === "last_week") {
    const daysSinceMonday = (start.getUTCDay() + 6) % 7;
    start.setUTCDate(start.getUTCDate() - daysSinceMonday - 7);
    end.setTime(start.getTime());
    end.setUTCDate(end.getUTCDate() + 6);
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

// ─── Formatters ──────────────────────────────────────────────────────────────

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

const COL_CLASS: Record<number, string> = {
  1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-3",
  4: "grid-cols-4", 5: "grid-cols-5", 6: "grid-cols-6",
};

function SkeletonGrid({ cols = 4, rows = 1 }: { cols?: number; rows?: number }) {
  return (
    <div className="space-y-6">
      <div className={`grid ${COL_CLASS[cols] ?? "grid-cols-4"} gap-4 sm:gap-6`}>
        {Array.from({ length: cols * rows }).map((_, i) => (
          <div key={i} className="h-36 rounded-card bg-surface-mid animate-pulse" />
        ))}
      </div>
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

// ─── Overview Tab ─────────────────────────────────────────────────────────────

function FunnelSteps({ steps }: { steps: FunnelStep[] }) {
  const firstCount = steps[0]?.count ?? 0;
  return (
    <div className="space-y-3">
      {steps.map((step, i) => {
        const prevCount = i === 0 ? step.count : steps[i - 1].count;
        const retentionPct =
          i === 0 || prevCount === 0
            ? null
            : Math.round((step.count / prevCount) * 100);
        const dropPct = retentionPct !== null ? 100 - retentionPct : null;
        const widthPct = firstCount === 0
          ? 0
          : Math.min(Math.round((step.count / firstCount) * 100), 100);

        return (
          <div key={step.label} className="flex items-center gap-3">
            <span className="font-label text-xs text-on-surface-muted w-20 text-right shrink-0">
              {step.label}
            </span>
            <div className="flex-1 bg-surface-mid rounded-full h-6 overflow-hidden">
              <div
                className="h-6 rounded-full bg-primary transition-all"
                style={{ width: `${widthPct}%` }}
              />
            </div>
            <span className="font-display text-sm font-bold text-on-surface w-10 shrink-0">
              {step.count}
            </span>
            {dropPct !== null && (
              <span className="font-label text-xs text-on-surface-muted w-14 shrink-0">
                {dropPct}% drop
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PerformanceKpi({ card }: { card: PerformanceCard }) {
  const improved = card.delta != null
    ? card.lowerIsBetter ? card.delta < 0 : card.delta > 0
    : null;
  const deltaLabel = card.delta == null
    ? null
    : `${card.delta >= 0 ? "+" : ""}${card.delta}% vs comparison`;
  return (
    <div className="flex flex-col gap-1 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-5">
      <p className="font-label text-xs uppercase tracking-wider text-on-surface-muted">{card.label}</p>
      <p className="mt-1 font-display text-2xl font-bold text-on-surface sm:text-3xl">{card.value}</p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-label text-xs">
        <span className="text-on-surface-muted">{card.scope}</span>
        {deltaLabel && (
          <span className={improved ? "text-emerald-600" : card.delta === 0 ? "text-on-surface-muted" : "text-red-600"}>
            {deltaLabel}
          </span>
        )}
      </div>
    </div>
  );
}

function OverviewTab({
  range,
  onRangeChange,
}: {
  range: RangeValue;
  onRangeChange: (range: RangeValue) => void;
}) {
  const [comparison, setComparison] = useState<ComparisonSelection>({
    mode: "off", start: "", end: "",
  });
  const [data, setData] = useState<ComparePayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [staleLeads, setStaleLeads] = useState<StaleHotLead[] | null>(null);
  const [staleErr, setStaleErr] = useState<string | null>(null);
  const [staleRetryKey, setStaleRetryKey] = useState(0);
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
      .catch((e: unknown) => { if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { isCurrent = false; };
  }, [canLoad, params, retryKey]);

  useEffect(() => {
    let isCurrent = true;
    setStaleLeads(null);
    setStaleErr(null);
    api.analytics.staleHotLeads({ min_hours: 24, limit: 10 })
      .then((d) => { if (isCurrent) setStaleLeads(d.leads); })
      .catch((e: unknown) => {
        if (isCurrent) setStaleErr(e instanceof Error ? e.message : "Failed to load the reply queue");
      });
    return () => { isCurrent = false; };
  }, [staleRetryKey]);

  const presentation = data
    ? buildOverviewPresentation({ current: data.current, previous: data.previous })
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-5 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
        <div>
          <p className="mb-3 font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted">
            Reporting period
          </p>
          <RangePicker value={range} onChange={onRangeChange} idPrefix="overview-range" />
        </div>
        <ComparisonPicker value={comparison} onChange={setComparison} />
      </div>

      <SectionCard title="Needs attention">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-label text-xs font-semibold uppercase tracking-wider text-red-600">
              {attentionScopeLabel()}
            </p>
            <p className="mt-1 font-body text-sm text-on-surface-muted">
              Hot leads still waiting on a reply.
            </p>
          </div>
          <a
            href={attentionLeadHref(staleLeads?.[0]?.id)}
            className="rounded-xl bg-primary px-4 py-2 font-label text-xs font-semibold text-white transition-opacity hover:opacity-90"
          >
            Open reply queue
          </a>
        </div>
        {staleErr && (
          <ErrorBox message={staleErr} onRetry={() => setStaleRetryKey((key) => key + 1)} />
        )}
        {!staleErr && staleLeads === null && (
          <p className="font-label text-sm text-on-surface-muted">Checking the queue…</p>
        )}
        {staleLeads?.length === 0 && (
          <p className="font-label text-sm text-emerald-700">No hot leads are waiting.</p>
        )}
        {staleLeads && staleLeads.length > 0 && (
          <div className="space-y-1">
            {staleLeads.map((lead) => (
              <a
                key={lead.id}
                href={attentionLeadHref(lead.id)}
                className="flex items-center justify-between rounded-lg px-3 py-2 transition-colors hover:bg-surface-low/60"
              >
                <span className="font-body text-sm text-on-surface">
                  {lead.name || lead.phone}
                </span>
                <span className="font-label text-xs text-on-surface-muted">
                  {lead.last_outbound_at ? "no reply since last message" : "never contacted"}
                </span>
              </a>
            ))}
          </div>
        )}
      </SectionCard>

      {!canLoad && (
        <p className="font-label text-sm text-on-surface-muted">
          Pick a valid start and end date for each custom period.
        </p>
      )}
      {err && <ErrorBox message={err} onRetry={() => setRetryKey((key) => key + 1)} />}
      {!data && !err && canLoad && <SkeletonGrid cols={5} />}

      {data && presentation && (
        <>
          <div>
            <h2 className="font-display text-lg font-bold text-primary">Selected-period performance</h2>
            <p className="mt-1 font-label text-xs text-on-surface-muted">
              {data.current.start} → {data.current.end}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5 xl:gap-4">
            {presentation.cards.map((card) => <PerformanceKpi key={card.label} card={card} />)}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
            <SectionCard title="Selected-period pipeline">
              <FunnelSteps steps={presentation.funnel} />
            </SectionCard>
            <SectionCard title="New leads by day">
              <div role="img" aria-label="New leads in the selected period chart">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={presentation.trend} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                    <defs>
                      <linearGradient id="leadGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#5b21b6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#5b21b6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                    <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#a8a29e" }} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
                    <Area type="monotone" dataKey="count" stroke="#5b21b6" fill="url(#leadGrad)" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          </div>
        </>
      )}
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

function ChannelsTab({ range }: { range: RangeValue }) {
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [data, setData] = useState<MessagingAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
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

  return (
    <div className="space-y-6">
      {/* Channel switcher */}
      <div className="flex gap-2 flex-wrap">
        {CHANNEL_OPTIONS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setChannel(id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg font-label text-sm font-semibold transition-colors ring-1 ${
              channel === id
                ? "bg-primary-light text-primary ring-primary-muted"
                : "bg-surface text-on-surface-muted ring-[#c4c7c7]/15 hover:text-on-surface"
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {!canLoad && (
        <p className="font-label text-sm text-on-surface-muted">Pick a valid custom reporting period.</p>
      )}
      {err && <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />}
      {!data && !err && canLoad && <SkeletonGrid cols={4} />}

      {data && (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
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
          </div>

          {/* Charts */}
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
        </>
      )}
    </div>
  );
}

// ─── Page shell ───────────────────────────────────────────────────────────────

function pct(part: number, whole: number): string {
  if (!whole) return "—";
  return `${Math.round((part / whole) * 100)}%`;
}

function TemplatesTab() {
  const [rows, setRows] = useState<TemplatePerformanceRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    setErr(null);
    setRows(null);
    api.analytics
      .templatePerformance()
      .then(setRows)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : "Failed to load"));
  }, [retryKey]);

  if (err) return <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />;
  if (!rows) return <SkeletonGrid cols={4} />;

  const totals = rows.reduce(
    (acc, r) => ({
      sent: acc.sent + r.sent,
      read: acc.read + r.read,
      replied: acc.replied + r.replied,
      hot: acc.hot + r.hot_leads,
    }),
    { sent: 0, read: 0, replied: 0, hot: 0 },
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <KpiCard label="Total Sent" value={totals.sent.toLocaleString()} />
        <KpiCard label="Read Rate" value={pct(totals.read, totals.sent)} sub={`${totals.read.toLocaleString()} read`} />
        <KpiCard label="Reply Rate" value={pct(totals.replied, totals.sent)} sub={`${totals.replied.toLocaleString()} replied`} />
        <KpiCard label="Hot Leads" value={totals.hot.toLocaleString()} />
      </div>

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
    </div>
  );
}

// ─── Inbound Tab ─────────────────────────────────────────────────────────────

function InboundTab({ range }: { range: RangeValue }) {
  const [data, setData] = useState<InboundAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const rangeQuery = useMemo(() => reportingQuery(range), [range]);
  const canLoad = canLoadComparison(range, { mode: "off", start: "", end: "" });

  useEffect(() => {
    if (!canLoad) {
      setData(null);
      setErr(null);
      return;
    }
    setData(null);
    setErr(null);
    fetchAnalytics<InboundAnalytics>(`/api/v1/analytics/inbound?${rangeQuery}`)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load"));
  }, [canLoad, rangeQuery, retryKey]);

  if (err) return <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />;
  if (!canLoad) return <p className="font-label text-sm text-on-surface-muted">Pick a valid custom reporting period.</p>;
  if (!data) return <div className="p-8 text-center text-on-surface-muted">Loading…</div>;

  const segMax = Math.max(data.by_segment.A, data.by_segment.B, data.by_segment.C, data.by_segment.D, 1);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4">
        <KpiCard label="New Leads Today" value={data.kpis.today.total.toLocaleString()} sub={`Organic ${data.kpis.today.organic} · Ad ${data.kpis.today.ad}`} />
        <KpiCard label="New Leads (range)" value={data.kpis.range.total.toLocaleString()} sub={`Organic ${data.kpis.range.organic} · Ad ${data.kpis.range.ad}`} />
        <KpiCard label="Ad Share" value={`${data.kpis.range.total ? Math.round((data.kpis.range.ad / data.kpis.range.total) * 100) : 0}%`} sub="of inbound in range" />
      </div>

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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-6">
        <SectionCard title="By Segment (inbound only)">
          <div className="space-y-3">
            {([["A", "Hot"], ["B", "Warm"], ["C", "Cold"], ["D", "Disqualified"]] as const).map(([k, label]) => (
              <div key={k} className="flex items-center gap-3">
                <span className="font-label text-xs text-on-surface-muted w-24 shrink-0">{label}</span>
                <div className="flex-1 bg-surface-mid rounded-full h-4 overflow-hidden">
                  <div className="h-4 rounded-full bg-primary" style={{ width: `${Math.round((data.by_segment[k] / segMax) * 100)}%` }} />
                </div>
                <span className="font-label text-xs w-8 text-right shrink-0">{data.by_segment[k]}</span>
              </div>
            ))}
          </div>
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
      </div>
    </div>
  );
}

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "compare", label: "Compare" },
  { id: "channels", label: "Channels" },
  { id: "inbound", label: "Inbound" },
  { id: "templates", label: "Templates" },
];

export default function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [range, setRange] = useState<RangeValue>({
    preset: "last_7d", start: "", end: "",
  });

  return (
    <div className="min-w-0 space-y-5 sm:space-y-6">
      <div className="flex min-w-0 flex-col gap-3 border-b border-[#e8e3db] pb-4">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
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
      </div>

      {(activeTab === "channels" || activeTab === "inbound") && (
        <div className="rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
          <p className="mb-3 font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted">
            Reporting period
          </p>
          <RangePicker value={range} onChange={setRange} idPrefix={`${activeTab}-range`} />
        </div>
      )}

      {activeTab === "overview" && <OverviewTab range={range} onRangeChange={setRange} />}
      {activeTab === "compare" && <CompareTab />}
      {activeTab === "channels" && <ChannelsTab range={range} />}
      {activeTab === "inbound" && <InboundTab range={range} />}
      {activeTab === "templates" && <TemplatesTab />}
    </div>
  );
}
