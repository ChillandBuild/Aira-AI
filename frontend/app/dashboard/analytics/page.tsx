"use client";

import { useEffect, useState } from "react";
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
  AnalyticsOverviewExtended,
  MessagingAnalytics,
  FunnelAnalyticsExtended,
  TemplatePerformanceRow,
} from "@/lib/api";
import { CompareTab } from "./CompareTab";

type DateRange = "today" | "7d" | "30d";
type Tab = "overview" | "channels" | "templates" | "inbound" | "compare";

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

function FunnelSteps({
  funnel,
}: {
  funnel: AnalyticsOverviewExtended["funnel"];
}) {
  const steps = [
    { label: "Inquiries", count: funnel.inquiries },
    { label: "Engaged", count: funnel.engaged },
    { label: "Hot", count: funnel.hot },
    { label: "Converted", count: funnel.converted },
  ];

  return (
    <div className="space-y-3">
      {steps.map((step, i) => {
        const prevCount = i === 0 ? step.count : steps[i - 1].count;
        const retentionPct =
          i === 0 || prevCount === 0
            ? null
            : Math.round((step.count / prevCount) * 100);
        const dropPct = retentionPct !== null ? 100 - retentionPct : null;
        const widthPct =
          funnel.inquiries === 0 ? 0 : Math.round((step.count / funnel.inquiries) * 100);

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

function SegmentBars({
  bySegment,
  total,
}: {
  bySegment: Record<"A" | "B" | "C" | "D", number>;
  total: number;
}) {
  const segs: { key: "A" | "B" | "C" | "D"; label: string; color: string }[] = [
    { key: "A", label: "Hot (A)", color: "bg-emerald-500" },
    { key: "B", label: "Warm (B)", color: "bg-blue-500" },
    { key: "C", label: "Cold (C)", color: "bg-amber-500" },
    { key: "D", label: "Disqualified (D)", color: "bg-red-400" },
  ];

  return (
    <div className="space-y-3">
      {segs.map(({ key, label, color }) => {
        const count = bySegment[key] ?? 0;
        const pct = total === 0 ? 0 : Math.round((count / total) * 100);
        return (
          <div key={key} className="flex items-center gap-3">
            <span className="font-label text-xs text-on-surface-muted w-28 shrink-0">{label}</span>
            <div className="flex-1 bg-surface-mid rounded-full h-4 overflow-hidden">
              <div
                className={`h-4 rounded-full ${color} transition-all`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="font-label text-xs text-on-surface w-8 text-right shrink-0">{count}</span>
            <span className="font-label text-xs text-on-surface-muted w-8 shrink-0">{pct}%</span>
          </div>
        );
      })}
    </div>
  );
}

function OverviewTab({ range }: { range: DateRange }) {
  const [data, setData] = useState<AnalyticsOverviewExtended | null>(null);
  const [funnel, setFunnel] = useState<FunnelAnalyticsExtended | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    setData(null);
    setErr(null);
    api.analytics
      .overviewExtended(range)
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => { if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { isCurrent = false; };
  }, [range, retryKey]);

  useEffect(() => {
    let isCurrent = true;
    api.analytics.funnelExtended()
      .then((d) => { if (isCurrent) setFunnel(d); })
      .catch(() => {});
    return () => { isCurrent = false; };
  }, [retryKey]);

  if (err) return <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />;
  if (!data) return <SkeletonGrid cols={6} />;

  const total = data.total_leads;
  const hotCount = data.by_segment.A ?? 0;
  const hotPct = total === 0 ? 0 : Math.round((hotCount / total) * 100);
  const aiTotal = data.ai_vs_human.ai + data.ai_vs_human.human;
  const aiPct = aiTotal === 0 ? 0 : Math.round((data.ai_vs_human.ai / aiTotal) * 100);
  const cb = data.channel_breakdown;
  const channelSub = `WA: ${cb.whatsapp} · IG: ${cb.instagram} · FB: ${cb.facebook} · TG: ${cb.telegram}`;

  // Cost per lead and reply speed are range-scoped, unlike the all-time
  // counts beside them. Rendered as "—" rather than 0 when a tenant has no
  // ad spend or no inbound messages in the range: absent is not zero.
  const costPerLead = data.money?.cost_per_lead;
  const costPerLeadValue =
    costPerLead == null ? "—" : "₹" + Math.round(costPerLead).toLocaleString("en-IN");
  const p50 = data.response_times?.p50_seconds;
  const replyTimeValue =
    p50 == null ? "—" : p50 < 60 ? `${Math.round(p50)}s` : `${Math.round(p50 / 60)}m`;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 xl:gap-4">
        <KpiCard label="Total Leads" value={total.toLocaleString()} sub={channelSub} />
        <KpiCard
          label="Hot Leads"
          value={hotCount.toLocaleString()}
          sub={`${hotPct}% of total`}
        />
        <KpiCard
          label="Conversions"
          value={data.funnel.converted.toLocaleString()}
          sub={`${data.converted_today} today`}
        />
        <KpiCard
          label="Unreplied 24h"
          value={data.unreplied_24h.toLocaleString()}
          valueClass={data.unreplied_24h > 0 ? "text-red-600" : "text-emerald-600"}
        />
        <KpiCard label="AI Automation" value={`${aiPct}%`} sub={`${data.ai_vs_human.ai} AI · ${data.ai_vs_human.human} human`} />
        <KpiCard label="Avg Score" value={funnel?.avg_score != null ? funnel.avg_score.toFixed(1) : "—"} sub="lead quality" />
        <KpiCard
          label="Cost per Lead"
          value={costPerLeadValue}
          sub={data.money?.spend ? `₹${Math.round(data.money.spend).toLocaleString("en-IN")} spent in range` : "no ad spend in range"}
        />
        <KpiCard
          label="Reply Time"
          value={replyTimeValue}
          sub={
            data.response_times?.inbound_total
              ? `median · ${data.response_times.answered ?? 0} of ${data.response_times.inbound_total} answered`
              : "no messages in range"
          }
        />
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
        <SectionCard title="New Leads per Day">
          <div role="img" aria-label="New leads per day chart">
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={data.daily_leads} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="leadGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#5b21b6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#5b21b6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
                <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }}
                />
                <Area type="monotone" dataKey="count" stroke="#5b21b6" fill="url(#leadGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Messages per Day">
          <div role="img" aria-label="Messages per day chart">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.daily_messages} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
                <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
                <Bar dataKey="inbound" stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]} name="Inbound" />
                <Bar dataKey="outbound" stackId="a" fill="#10b981" radius={[4, 4, 0, 0]} name="Outbound" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
        <SectionCard title="Conversion Funnel">
          <FunnelSteps funnel={data.funnel} />
        </SectionCard>

        <SectionCard title="Segment Distribution">
          <SegmentBars bySegment={data.by_segment} total={total} />
        </SectionCard>
      </div>

      {/* Hot-lead aging — the one actionable signal kept from the old Pipeline tab */}
      {funnel && funnel.hot_lead_aging.length > 0 && (
        <SectionCard title="Hot Leads (Segment A) — time without conversion">
          <HotLeadAging aging={funnel.hot_lead_aging} />
        </SectionCard>
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

function ChannelsTab({ range }: { range: DateRange }) {
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [data, setData] = useState<MessagingAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    setData(null);
    setErr(null);
    api.analytics
      .messaging(channel, range)
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => { if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { isCurrent = false; };
  }, [channel, range, retryKey]);

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

      {err && <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />}
      {!data && !err && <SkeletonGrid cols={4} />}

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

// ─── Hot-lead aging (used by the Overview tab) ────────────────────────────────

const HOT_AGING_COLORS = ["bg-emerald-500", "bg-amber-400", "bg-orange-500", "bg-red-600"];

function HotLeadAging({ aging }: { aging: FunnelAnalyticsExtended["hot_lead_aging"] }) {
  const max = Math.max(...aging.map((a) => a.count), 1);
  return (
    <div className="space-y-3">
      {aging.map(({ bucket, count }, i) => {
        const pct = Math.round((count / max) * 100);
        return (
          <div key={bucket} className="flex items-center gap-3">
            <span className="font-label text-xs text-on-surface-muted w-14 shrink-0">{bucket}</span>
            <div className="flex-1 bg-surface-mid rounded-full h-4 overflow-hidden">
              <div
                className={`h-4 rounded-full ${HOT_AGING_COLORS[i] ?? "bg-[#a8a29e]"} transition-all`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="font-label text-xs text-on-surface w-8 text-right shrink-0">{count}</span>
          </div>
        );
      })}
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

function InboundTab({ range }: { range: DateRange }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.analytics.inbound>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    setData(null);
    setErr(null);
    api.analytics.inbound(range)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load"));
  }, [range, retryKey]);

  if (err) return <ErrorBox message={err} onRetry={() => setRetryKey((k) => k + 1)} />;
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

const RANGES: { id: DateRange; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "7d", label: "7 Days" },
  { id: "30d", label: "30 Days" },
];

export default function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [range, setRange] = useState<DateRange>("7d");

  return (
    <div className="min-w-0 space-y-5 sm:space-y-6">
      {/* Page header: tabs & date pills inline */}
      <div className="flex min-w-0 flex-col gap-3 border-b border-[#e8e3db] pb-4 lg:flex-row lg:items-center lg:justify-between">
        {/* Tab row */}
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <nav className="flex w-max gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

        {/* Date range pills — the Compare tab owns its own range control */}
        {activeTab !== "compare" && (
          <div className="grid grid-cols-3 gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15 sm:flex sm:w-fit">
            {RANGES.map((r) => (
              <button
                key={r.id}
                onClick={() => setRange(r.id)}
                className={`rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-4 sm:text-sm ${
                  range === r.id
                    ? "bg-surface text-primary shadow-card"
                    : "text-on-surface-muted hover:text-on-surface"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && <OverviewTab range={range} />}
      {activeTab === "compare" && <CompareTab />}
      {activeTab === "channels" && <ChannelsTab range={range} />}
      {activeTab === "inbound" && <InboundTab range={range} />}
      {activeTab === "templates" && <TemplatesTab />}
    </div>
  );
}
