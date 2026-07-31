"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  Columns3,
  Copy,
  Download,
  Filter,
  KeyRound,
  Loader2,
  type LucideIcon,
  Megaphone,
  MessageCircle,
  MessageSquareOff,
  MousePointerClick,
  Percent,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api, AdPerformanceRow, AdTrackingCodeResponse } from "@/lib/api";
import { useAdFilters, useAdPerformance } from "@/hooks/useApi";
import { cn } from "@/lib/utils";

type MetricKey =
  | "campaign_status"
  | "budget"
  | "impressions"
  | "reach"
  | "frequency"
  | "inline_link_clicks"
  | "clicks_all"
  | "messages"
  | "meta_conversations"
  | "conversation_rate"
  | "meta_conversation_rate"
  | "attribution_gap"
  | "clicked_no_message"
  | "no_message_rate"
  | "spend"
  | "cpc"
  | "cost_per_message"
  | "ctr"
  | "cpm"
  | "hot"
  | "hot_rate"
  | "cost_per_hot";

const METRICS: { key: MetricKey; label: string; defaultVisible: boolean; help: string }[] = [
  { key: "campaign_status", label: "Delivery", defaultVisible: true, help: "Current campaign delivery status from Meta" },
  { key: "budget", label: "Budget", defaultVisible: false, help: "Daily or lifetime budget from the campaign or ad set in Meta" },
  { key: "impressions", label: "Impressions", defaultVisible: true, help: "Times the ad was shown" },
  { key: "reach", label: "Reach", defaultVisible: true, help: "Sum of daily Meta reach; people may repeat across days" },
  { key: "frequency", label: "Frequency", defaultVisible: false, help: "Impressions divided by summed daily reach" },
  { key: "inline_link_clicks", label: "WhatsApp clicks", defaultVisible: true, help: "Link clicks on Click-to-WhatsApp ads" },
  { key: "clicks_all", label: "Clicks (all)", defaultVisible: false, help: "All interactions Meta classifies as clicks" },
  { key: "messages", label: "Messages sent (Aira confirmed)", defaultVisible: true, help: "Unique people confirmed for this ad; repeat messages from the same person and ad count once" },
  { key: "meta_conversations", label: "Meta-reported conversations", defaultVisible: false, help: "Meta's advertising-system count; optional and intended only for tracking comparison" },
  { key: "conversation_rate", label: "Message rate", defaultVisible: true, help: "Aira-confirmed messages divided by WhatsApp clicks" },
  { key: "meta_conversation_rate", label: "Meta-reported message rate", defaultVisible: false, help: "Meta-reported conversations divided by WhatsApp clicks" },
  { key: "attribution_gap", label: "Tracking difference", defaultVisible: false, help: "Aira-confirmed messages minus Meta-reported conversations" },
  { key: "clicked_no_message", label: "No message", defaultVisible: true, help: "WhatsApp clicks not matched to a unique Aira lead for this ad" },
  { key: "no_message_rate", label: "No-message rate", defaultVisible: false, help: "No-message clicks divided by WhatsApp clicks" },
  { key: "spend", label: "Spend", defaultVisible: true, help: "Amount spent in the selected period" },
  { key: "cpc", label: "CPC", defaultVisible: true, help: "Spend divided by WhatsApp clicks" },
  { key: "cost_per_message", label: "Cost / sent message", defaultVisible: true, help: "Spend divided by Aira-confirmed messages" },
  { key: "ctr", label: "CTR", defaultVisible: false, help: "Click-through rate: WhatsApp clicks divided by impressions" },
  { key: "cpm", label: "CPM", defaultVisible: false, help: "Cost per mille: spend per 1,000 impressions" },
  { key: "hot", label: "Hot", defaultVisible: false, help: "Aira leads currently in the Hot segment" },
  { key: "hot_rate", label: "Hot lead rate", defaultVisible: false, help: "Hot leads divided by Aira-confirmed messages" },
  { key: "cost_per_hot", label: "Cost / hot lead", defaultVisible: false, help: "Spend divided by Hot leads" },
];

const DEFAULT_METRICS = new Set(METRICS.filter((metric) => metric.defaultVisible).map((metric) => metric.key));

function localDate(daysBack = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysBack);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return "₹" + Math.round(value).toLocaleString("en-IN");
}

function count(value: number | null | undefined) {
  return Math.round(value ?? 0).toLocaleString("en-IN");
}

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function decimal(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(2);
}

function budgetLabel(row: AdPerformanceRow) {
  const suffix = row.budget_level === "ad_set"
    ? " · Ad set"
    : row.budget_level === "campaign"
      ? " · Campaign"
      : "";
  if (row.daily_budget != null) return `${money(row.daily_budget)}/day${suffix}`;
  if (row.lifetime_budget != null) return `${money(row.lifetime_budget)} lifetime${suffix}`;
  return "—";
}

function signedCount(value: number) {
  if (!value) return "0";
  return `${value > 0 ? "+" : ""}${Math.round(value).toLocaleString("en-IN")}`;
}

function PerformanceKpiCard({
  label,
  value,
  description,
  icon: Icon,
  gradient,
}: {
  label: string;
  value: string;
  description: string;
  icon: LucideIcon;
  gradient: string;
}) {
  return (
    <div className="group flex items-center gap-4 rounded-2xl border border-[#e8e3db]/80 bg-white p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white transition-transform group-hover:scale-110", gradient)}>
        <Icon size={19} />
      </span>
      <span className="min-w-0">
        <span className="block font-display text-2xl font-bold leading-none tabular-nums text-[#1c1917]">{value}</span>
        <span className="mt-0.5 block font-label text-xs font-medium text-[#a8a29e]">{label}</span>
        <span className="mt-1 block truncate font-body text-[9px] leading-none text-stone-400" title={description}>
          {description}
        </span>
      </span>
    </div>
  );
}

function statusLabel(status: string | null | undefined) {
  return (status || "UNKNOWN").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  const normalized = (status || "").toUpperCase();
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-label text-[10px] font-bold",
      normalized === "ACTIVE"
        ? "bg-emerald-50 text-emerald-700"
        : normalized === "PAUSED"
          ? "bg-amber-50 text-amber-700"
          : normalized.includes("DISAPPROVED") || normalized.includes("ERROR")
            ? "bg-red-50 text-red-700"
            : "bg-stone-100 text-stone-600",
    )}>
      <span className={cn(
        "h-1.5 w-1.5 rounded-full",
        normalized === "ACTIVE"
          ? "bg-emerald-500"
          : normalized === "PAUSED"
            ? "bg-amber-500"
            : normalized.includes("DISAPPROVED") || normalized.includes("ERROR")
              ? "bg-red-500"
              : "bg-stone-400",
      )} />
      {statusLabel(status)}
    </span>
  );
}

function aggregateRows(rows: AdPerformanceRow[]): AdPerformanceRow {
  const total = rows.reduce((acc, row) => {
    acc.impressions += row.impressions;
    acc.reach += row.reach;
    acc.inline_link_clicks += row.inline_link_clicks;
    acc.clicks_all += row.clicks_all;
    acc.messages += row.messages;
    acc.meta_conversations += row.meta_conversations;
    acc.clicked_no_message += row.clicked_no_message;
    acc.hot += row.hot;
    acc.spend += row.spend;
    return acc;
  }, {
    impressions: 0,
    reach: 0,
    inline_link_clicks: 0,
    clicks_all: 0,
    messages: 0,
    meta_conversations: 0,
    clicked_no_message: 0,
    hot: 0,
    spend: 0,
  });

  return {
    ad_creative_id: "total",
    creative_label: "Total",
    meta_ad_id: "",
    meta_ad_account_id: "",
    adset_id: null,
    adset_name: null,
    campaign_id: null,
    campaign_name: "Total",
    campaign_status: null,
    daily_budget: null,
    lifetime_budget: null,
    budget_level: null,
    ...total,
    frequency: total.reach ? total.impressions / total.reach : null,
    conversation_rate: total.inline_link_clicks ? (total.messages / total.inline_link_clicks) * 100 : null,
    meta_conversation_rate: total.inline_link_clicks ? (total.meta_conversations / total.inline_link_clicks) * 100 : null,
    attribution_gap: total.messages - total.meta_conversations,
    no_message_rate: total.inline_link_clicks ? (total.clicked_no_message / total.inline_link_clicks) * 100 : null,
    hot_rate: total.messages ? (total.hot / total.messages) * 100 : null,
    ctr: total.impressions ? (total.inline_link_clicks / total.impressions) * 100 : null,
    cpm: total.impressions ? (total.spend / total.impressions) * 1000 : null,
    cpc: total.inline_link_clicks ? total.spend / total.inline_link_clicks : null,
    cost_per_message: total.messages ? total.spend / total.messages : null,
    cost_per_hot: total.hot ? total.spend / total.hot : null,
  };
}

function metricValue(metric: MetricKey, row: AdPerformanceRow) {
  switch (metric) {
    case "campaign_status":
      return <StatusBadge status={row.campaign_status} />;
    case "budget":
      return budgetLabel(row);
    case "impressions":
    case "reach":
    case "inline_link_clicks":
    case "clicks_all":
    case "messages":
    case "meta_conversations":
    case "clicked_no_message":
    case "hot":
      return count(row[metric]);
    case "attribution_gap":
      return signedCount(row.attribution_gap);
    case "conversation_rate":
    case "meta_conversation_rate":
    case "no_message_rate":
    case "hot_rate":
    case "ctr":
      return percent(row[metric]);
    case "spend":
    case "cpc":
    case "cost_per_message":
    case "cpm":
    case "cost_per_hot":
      return money(row[metric]);
    case "frequency":
      return decimal(row.frequency);
  }
}

export function AdPerformanceTab() {
  const [campaignId, setCampaignId] = useState("");
  const [adsetId, setAdsetId] = useState("");
  const [creativeId, setCreativeId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => localDate(29));
  const [dateTo, setDateTo] = useState(() => localDate());
  const [exporting, setExporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [showTrackingModal, setShowTrackingModal] = useState(false);
  const [trackingCreativeId, setTrackingCreativeId] = useState("");
  const [trackingMessage, setTrackingMessage] = useState("Hi, I'm interested in this service.");
  const [trackingResult, setTrackingResult] = useState<AdTrackingCodeResponse | null>(null);
  const [generatingTrackingCode, setGeneratingTrackingCode] = useState(false);
  const [copiedTrackingMessage, setCopiedTrackingMessage] = useState(false);
  const [showReportingNotice, setShowReportingNotice] = useState(true);
  const [visibleMetrics, setVisibleMetrics] = useState<Set<MetricKey>>(() => new Set(DEFAULT_METRICS));

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setShowReportingNotice(false), 10_000);
    return () => window.clearTimeout(timeoutId);
  }, []);

  const { data: filters, mutate: mutateFilters } = useAdFilters();
  const params = {
    campaign_id: campaignId || undefined,
    adset_id: adsetId || undefined,
    ad_creative_id: creativeId || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const { data, isValidating, mutate } = useAdPerformance(params);
  const rows = useMemo(() => data?.data ?? [], [data]);
  const totals = useMemo(() => aggregateRows(rows), [rows]);
  const selectedMetrics = useMemo(
    () => METRICS.filter((metric) => visibleMetrics.has(metric.key)),
    [visibleMetrics],
  );

  const adsetOptions = useMemo(
    () => (filters?.adsets ?? []).filter((adset) => !campaignId || adset.campaign_id === campaignId),
    [filters, campaignId],
  );
  const creativeOptions = useMemo(
    () => (filters?.creatives ?? []).filter(
      (creative) => (!campaignId || creative.campaign_id === campaignId) && (!adsetId || creative.adset_id === adsetId),
    ),
    [filters, campaignId, adsetId],
  );
  const activeDimensionFilters = Number(Boolean(campaignId)) + Number(Boolean(adsetId)) + Number(Boolean(creativeId));
  const campaignNames = useMemo(
    () => new Map((filters?.campaigns ?? []).map((campaign) => [campaign.id, campaign.name])),
    [filters],
  );
  const adsetNames = useMemo(
    () => new Map((filters?.adsets ?? []).map((adset) => [adset.id, adset.name])),
    [filters],
  );

  function toggleMetric(key: MetricKey) {
    setVisibleMetrics((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function clearFilters() {
    setCampaignId("");
    setAdsetId("");
    setCreativeId("");
    setDateFrom(localDate(29));
    setDateTo(localDate());
  }

  async function handleSyncNow() {
    setSyncing(true);
    try {
      const result = await api.inboundLeads.adSyncNow();
      if (!result.ok) {
        toast.error(result.error ?? "Sync failed — no details returned");
        return;
      }
      if (result.written > 0) {
        toast.success(`Synced ${result.written} Click-to-WhatsApp row${result.written === 1 ? "" : "s"}`);
      } else if (result.rows_fetched > 0) {
        toast.info("Meta returned ads, but none were single-destination Click-to-WhatsApp ads.");
      } else {
        toast.info("Meta returned no ad data for this account and period.");
      }
      await Promise.all([mutate(), mutateFilters()]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await api.inboundLeads.adPerformanceExportCsv(params);
      toast.success("Downloaded: ad_performance.csv");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  function openTrackingModal() {
    setTrackingCreativeId(creativeId || creativeOptions[0]?.id || filters?.creatives?.[0]?.id || "");
    setTrackingResult(null);
    setCopiedTrackingMessage(false);
    setShowTrackingModal(true);
  }

  async function handleGenerateTrackingCode() {
    if (!trackingCreativeId) {
      toast.error("Select a creative first");
      return;
    }
    setGeneratingTrackingCode(true);
    try {
      const result = await api.inboundLeads.generateAdTrackingCode({
        ad_creative_id: trackingCreativeId,
        message: trackingMessage,
      });
      setTrackingResult(result);
      await mutateFilters();
      toast.success("Tracking ID is ready");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not generate tracking ID");
    } finally {
      setGeneratingTrackingCode(false);
    }
  }

  async function handleCopyTrackingMessage() {
    if (!trackingResult) return;
    try {
      await navigator.clipboard.writeText(trackingResult.prefilled_message);
      setCopiedTrackingMessage(true);
      toast.success("Pre-filled message copied");
      window.setTimeout(() => setCopiedTrackingMessage(false), 2_000);
    } catch {
      toast.error("Could not copy the message");
    }
  }

  const selectClass =
    "h-9 w-full cursor-pointer appearance-none rounded-xl border border-surface-mid bg-white px-3 pr-8 font-body text-xs font-semibold text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div>
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
              <PerformanceKpiCard
                label="WhatsApp Clicks"
                value={count(totals.inline_link_clicks)}
                description="Clicked the ad and opened WhatsApp"
                icon={MousePointerClick}
                gradient="bg-gradient-to-br from-violet-500 to-primary"
              />
              <PerformanceKpiCard
                label="Messages Sent"
                value={count(totals.messages)}
                description="Clicked and sent the WhatsApp message"
                icon={MessageCircle}
                gradient="bg-gradient-to-br from-blue-500 to-cyan-600"
              />
              <PerformanceKpiCard
                label="No Message"
                value={count(totals.clicked_no_message)}
                description="Clicked but did not send the message"
                icon={MessageSquareOff}
                gradient="bg-gradient-to-br from-amber-500 to-orange-500"
              />
              <PerformanceKpiCard
                label="Message Rate"
                value={percent(totals.conversation_rate)}
                description="Messages sent out of WhatsApp clicks"
                icon={Percent}
                gradient="bg-gradient-to-br from-emerald-500 to-teal-600"
              />
        </div>

        <div className="grid h-fit grid-cols-2 gap-2 self-start p-1">
          <button type="button" onClick={() => mutate()} disabled={isValidating}
            className="flex items-center justify-center gap-2 rounded-xl border border-surface-mid bg-white px-3 py-2 font-label text-xs font-bold text-on-surface shadow-sm transition-all hover:border-violet-300 hover:text-violet-700 disabled:opacity-40">
            <RefreshCw size={12} className={isValidating ? "animate-spin" : ""} /> Refresh
          </button>
          <button type="button" onClick={handleSyncNow} disabled={syncing}
            title="Pull the latest Click-to-WhatsApp performance from Meta"
            className="flex items-center justify-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 font-label text-xs font-bold text-amber-700 shadow-sm transition-all hover:bg-amber-100 disabled:opacity-40">
            <Zap size={12} className={syncing ? "animate-pulse" : ""} /> {syncing ? "Syncing…" : "Sync now"}
          </button>

          <button type="button" onClick={() => setShowFilters((visible) => !visible)}
            aria-expanded={showFilters} aria-controls="ad-performance-filters"
            className={cn(
              "flex items-center justify-center gap-2 rounded-xl border px-3 py-2 font-label text-xs font-bold shadow-sm transition-all",
              showFilters || activeDimensionFilters > 0
                ? "border-violet-200 bg-violet-50 text-violet-700"
                : "border-surface-mid bg-white text-on-surface hover:border-violet-300 hover:text-violet-700",
            )}>
            <Filter size={12} /> Filters
            {activeDimensionFilters > 0 && (
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-violet-600 text-[9px] text-white">
                {activeDimensionFilters}
              </span>
            )}
          </button>

          <div className="relative">
            <button type="button" onClick={() => setShowColumns((visible) => !visible)}
              aria-expanded={showColumns} aria-haspopup="dialog"
              className="flex h-full w-full items-center justify-center gap-2 rounded-xl border border-indigo-200 bg-white px-3 py-2 font-label text-xs font-bold text-indigo-700 shadow-sm transition-all hover:bg-indigo-50">
              <Columns3 size={13} /> Columns
              <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px]">{selectedMetrics.length}</span>
            </button>
            {showColumns && (
              <div role="dialog" aria-label="Customize ad performance columns"
                className="absolute right-0 top-11 z-30 w-[320px] rounded-2xl border border-[#e8e3db] bg-white p-3 shadow-xl">
                <div className="mb-2 flex items-center justify-between border-b border-[#eee9e1] px-1 pb-2">
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal size={13} className="text-indigo-600" />
                    <span className="font-label text-xs font-bold text-[#292524]">Customize metrics</span>
                  </div>
                  <button type="button" onClick={() => setVisibleMetrics(new Set(DEFAULT_METRICS))}
                    className="flex items-center gap-1 font-label text-[10px] font-bold text-indigo-600 hover:text-indigo-800">
                    <RotateCcw size={10} /> Reset
                  </button>
                </div>
                <div className="max-h-[380px] space-y-1 overflow-y-auto pr-1">
                  {METRICS.map((metric) => (
                    <label key={metric.key} className="flex cursor-pointer items-start gap-2 rounded-xl px-2 py-2 hover:bg-stone-50">
                      <input type="checkbox" checked={visibleMetrics.has(metric.key)} onChange={() => toggleMetric(metric.key)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-stone-300 accent-indigo-600" />
                      <span>
                        <span className="block font-label text-[11px] font-bold text-stone-700">{metric.label}</span>
                        <span className="block font-body text-[10px] leading-4 text-stone-400">{metric.help}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button type="button" onClick={openTrackingModal} disabled={(filters?.creatives?.length ?? 0) === 0}
            title="Generate a fallback ID for a Meta ad's pre-filled WhatsApp message"
            className="flex items-center justify-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 font-label text-xs font-bold text-violet-700 shadow-sm transition-all hover:bg-violet-100 disabled:opacity-40">
            <KeyRound size={12} /> Generate ID
          </button>

          <button type="button" onClick={handleExport} disabled={exporting || rows.length === 0}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-40">
            <Download size={12} /> {exporting ? "Downloading…" : "Download CSV"}
          </button>
        </div>
      </div>

      {showFilters && (
        <div id="ad-performance-filters" className="mb-4 rounded-2xl border border-surface-mid bg-surface-low/50 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="font-label text-xs font-bold text-on-surface">Filter Ad Performance</p>
              <p className="font-body text-[10px] text-on-surface-muted">Date, campaign, ad set, and creative only</p>
            </div>
            <button type="button" onClick={clearFilters}
              className="flex items-center gap-1 font-label text-[10px] font-bold text-violet-700 hover:text-violet-900">
              <X size={11} /> Clear
            </button>
          </div>
          <div className="grid grid-cols-2 items-end gap-2.5 md:grid-cols-3 xl:grid-cols-[145px_145px_160px_160px_160px]">
            <div>
              <label htmlFor="ad-performance-from" className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">From</label>
              <input id="ad-performance-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)}
                className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
            </div>
            <div>
              <label htmlFor="ad-performance-to" className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">To</label>
              <input id="ad-performance-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)}
                className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
            </div>
            <div>
              <label htmlFor="ad-performance-campaign" className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Campaign</label>
              <div className="relative">
                <select id="ad-performance-campaign" className={selectClass} value={campaignId}
                  onChange={(event) => { setCampaignId(event.target.value); setAdsetId(""); setCreativeId(""); }}>
                  <option value="">All campaigns</option>
                  {(filters?.campaigns ?? []).map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
                </select>
                <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e]" />
              </div>
            </div>
            <div>
              <label htmlFor="ad-performance-adset" className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Ad set</label>
              <div className="relative">
                <select id="ad-performance-adset" className={selectClass} value={adsetId}
                  onChange={(event) => { setAdsetId(event.target.value); setCreativeId(""); }}>
                  <option value="">All ad sets</option>
                  {adsetOptions.map((adset) => <option key={adset.id} value={adset.id}>{adset.name}</option>)}
                </select>
                <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e]" />
              </div>
            </div>
            <div>
              <label htmlFor="ad-performance-creative" className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Creative</label>
              <div className="relative">
                <select id="ad-performance-creative" className={selectClass} value={creativeId} onChange={(event) => setCreativeId(event.target.value)}>
                  <option value="">All creatives</option>
                  {creativeOptions.map((creative) => <option key={creative.id} value={creative.id}>{creative.name}</option>)}
                </select>
                <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e]" />
              </div>
            </div>
          </div>
        </div>
      )}

      {showReportingNotice && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-indigo-100 bg-indigo-50/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600">
              <Megaphone size={15} />
            </span>
            <div>
              <p className="font-label text-xs font-bold text-indigo-950">Click-to-WhatsApp reporting</p>
              <p className="font-body text-[11px] text-indigo-700">
                Current account {filters?.account_id ?? "not connected"} · Website, app, form, Messenger, and Instagram DM ads are excluded.
              </p>
              <p className="font-body text-[10px] text-indigo-600">
                This applies only to Ad Performance; the Leads tab still includes WhatsApp, Instagram, Facebook, and Telegram leads.
              </p>
            </div>
          </div>
          <span className="rounded-full border border-indigo-200 bg-white px-3 py-1 font-label text-[10px] font-bold text-indigo-700">
            {dateFrom} — {dateTo}
          </span>
        </div>
      )}

      <div className="card overflow-hidden rounded-2xl">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-20 text-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-50">
              <Megaphone size={24} className="text-violet-400" />
            </div>
            <h3 className="mb-1 text-base font-bold text-[#44403c]">No Click-to-WhatsApp data for this account</h3>
            <p className="max-w-md text-sm leading-relaxed text-[#a8a29e]">
              Validate the Meta Ads card in Settings, then run Sync now. Ads from previously connected accounts stay hidden.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1180px]">
              <thead>
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  {["Campaign", "Ad set", "Creative"].map((heading) => (
                    <th key={heading} className="whitespace-nowrap px-4 py-3 text-left font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">{heading}</th>
                  ))}
                  {selectedMetrics.map((metric) => (
                    <th key={metric.key} title={metric.help}
                      className={cn(
                        "whitespace-nowrap px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted",
                        metric.key === "campaign_status" ? "text-left" : "text-right",
                      )}>
                      {metric.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid/50">
                {rows.map((row) => (
                  <tr key={row.ad_creative_id} className="transition-colors hover:bg-surface-low/60">
                    <td className="px-4 py-3 font-label text-xs font-semibold text-on-surface">{row.campaign_name}</td>
                    <td className="px-4 py-3 text-xs text-on-surface-muted">{row.adset_name ?? "—"}</td>
                    <td className="px-4 py-3 font-label text-xs font-semibold text-on-surface">{row.creative_label}</td>
                    {selectedMetrics.map((metric) => (
                      <td key={metric.key} className={cn(
                        "whitespace-nowrap px-4 py-3 text-xs tabular-nums",
                        metric.key === "campaign_status" ? "text-left" : "text-right",
                        metric.key === "messages" && "font-bold text-on-surface",
                        metric.key === "inline_link_clicks" && "font-semibold text-violet-700",
                        metric.key === "hot" && "font-semibold text-rose-600",
                      )}>
                        {metricValue(metric.key, row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-surface-mid bg-surface-low/50 font-bold">
                  <td className="px-4 py-3 text-sm">Total</td>
                  <td />
                  <td />
                  {selectedMetrics.map((metric) => (
                    <td key={metric.key} className={cn(
                      "whitespace-nowrap px-4 py-3 text-xs tabular-nums",
                      metric.key === "campaign_status" ? "text-left" : "text-right",
                    )}>
                      {metric.key === "campaign_status" ? "—" : metricValue(metric.key, totals)}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {showTrackingModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="tracking-id-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/40 p-4 backdrop-blur-[2px]"
          onClick={() => setShowTrackingModal(false)}
        >
          <div
            className="w-full max-w-lg rounded-3xl border border-white/60 bg-white p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-violet-100 text-violet-700">
                  <KeyRound size={18} />
                </span>
                <div>
                  <h2 id="tracking-id-title" className="font-display text-lg font-bold text-on-surface">Generate tracking ID</h2>
                  <p className="mt-0.5 font-body text-xs leading-5 text-on-surface-muted">
                    Meta Ad ID is used first. This code is the fallback when Meta does not send it.
                  </p>
                </div>
              </div>
              <button type="button" onClick={() => setShowTrackingModal(false)}
                className="rounded-xl p-2 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700"
                aria-label="Close tracking ID dialog">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="tracking-creative" className="mb-1.5 block font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
                  Meta ad creative
                </label>
                <div className="relative">
                  <select
                    id="tracking-creative"
                    className={selectClass}
                    value={trackingCreativeId}
                    onChange={(event) => {
                      setTrackingCreativeId(event.target.value);
                      setTrackingResult(null);
                      setCopiedTrackingMessage(false);
                    }}
                  >
                    <option value="">Select a creative</option>
                    {(filters?.creatives ?? []).map((creative) => {
                      const campaign = creative.campaign_id ? campaignNames.get(creative.campaign_id) : null;
                      const adset = creative.adset_id ? adsetNames.get(creative.adset_id) : null;
                      const context = [campaign, adset].filter(Boolean).join(" · ");
                      return (
                        <option key={creative.id} value={creative.id}>
                          {creative.name}{context ? ` — ${context}` : ""}
                        </option>
                      );
                    })}
                  </select>
                  <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e]" />
                </div>
              </div>

              <div>
                <label htmlFor="tracking-message" className="mb-1.5 block font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">
                  WhatsApp pre-filled message
                </label>
                <textarea
                  id="tracking-message"
                  rows={3}
                  maxLength={500}
                  value={trackingMessage}
                  onChange={(event) => {
                    setTrackingMessage(event.target.value);
                    setTrackingResult(null);
                  }}
                  className="w-full resize-none rounded-2xl border border-surface-mid bg-white px-3 py-2.5 font-body text-sm text-on-surface outline-none transition focus:border-violet-300 focus:ring-2 focus:ring-violet-100"
                />
              </div>

              <button
                type="button"
                onClick={handleGenerateTrackingCode}
                disabled={!trackingCreativeId || !trackingMessage.trim() || generatingTrackingCode}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 font-label text-sm font-bold text-white transition hover:bg-primary/90 disabled:opacity-40"
              >
                {generatingTrackingCode ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
                {generatingTrackingCode ? "Generating…" : "Generate ID"}
              </button>

              {trackingResult && (
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-label text-[10px] font-bold uppercase tracking-wider text-emerald-700">Tracking ID</p>
                      <p className="mt-0.5 font-mono text-base font-bold text-emerald-950">[AIRA:{trackingResult.code}]</p>
                    </div>
                    <button type="button" onClick={handleCopyTrackingMessage}
                      className="flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-white px-3 py-2 font-label text-xs font-bold text-emerald-700 hover:bg-emerald-50">
                      {copiedTrackingMessage ? <Check size={13} /> : <Copy size={13} />}
                      {copiedTrackingMessage ? "Copied" : "Copy message"}
                    </button>
                  </div>
                  <pre className="whitespace-pre-wrap rounded-xl bg-white px-3 py-2.5 font-body text-xs leading-5 text-stone-700">
                    {trackingResult.prefilled_message}
                  </pre>
                  <p className="mt-2 font-body text-[10px] leading-4 text-emerald-800">
                    Paste this exact text into this ad’s WhatsApp pre-filled message in Meta Ads Manager.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
