"use client";
import { useMemo, useState } from "react";
import { api, AdPerformanceRow } from "@/lib/api";
import { useAdFilters, useAdPerformance } from "@/hooks/useApi";
import { Download, RefreshCw, ChevronDown, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}
function ratio(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n.toFixed(2)}×`;
}

export function AdPerformanceTab() {
  const [campaignId, setCampaignId] = useState("");
  const [adsetId, setAdsetId] = useState("");
  const [creativeId, setCreativeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [exporting, setExporting] = useState(false);

  const { data: filters } = useAdFilters();
  const params = {
    campaign_id: campaignId || undefined,
    adset_id: adsetId || undefined,
    ad_creative_id: creativeId || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const { data, isValidating, mutate } = useAdPerformance(params);
  const rows: AdPerformanceRow[] = useMemo(() => data?.data ?? [], [data]);

  // Cascading option lists
  const adsetOptions = useMemo(
    () => (filters?.adsets ?? []).filter((a) => !campaignId || a.campaign_id === campaignId),
    [filters, campaignId],
  );
  const creativeOptions = useMemo(
    () => (filters?.creatives ?? []).filter(
      (c) => (!campaignId || c.campaign_id === campaignId) && (!adsetId || c.adset_id === adsetId),
    ),
    [filters, campaignId, adsetId],
  );

  const totals = useMemo(() => {
    const t = { clicks: 0, messages: 0, noMsg: 0, spend: 0, revenue: 0 };
    for (const r of rows) {
      t.clicks += r.inline_link_clicks;
      t.messages += r.messages;
      t.noMsg += r.clicked_no_message;
      t.spend += r.spend;
      t.revenue += r.revenue;
    }
    return t;
  }, [rows]);

  async function handleExport() {
    setExporting(true);
    try {
      await api.inboundLeads.adPerformanceExportCsv(params);
      toast.success("Downloaded: ad_performance.csv");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const selectCls =
    "h-9 w-full cursor-pointer appearance-none rounded-xl border border-surface-mid bg-white px-3 pr-8 font-body text-xs font-semibold text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <div>
      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-2.5">
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Campaign</label>
          <div className="relative">
            <select className={selectCls} value={campaignId}
              onChange={(e) => { setCampaignId(e.target.value); setAdsetId(""); setCreativeId(""); }}>
              <option value="">All Campaigns</option>
              {(filters?.campaigns ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
        </div>
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Ad Set</label>
          <div className="relative">
            <select className={selectCls} value={adsetId}
              onChange={(e) => { setAdsetId(e.target.value); setCreativeId(""); }}>
              <option value="">All Ad Sets</option>
              {adsetOptions.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
        </div>
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Creative</label>
          <div className="relative">
            <select className={selectCls} value={creativeId} onChange={(e) => setCreativeId(e.target.value)}>
              <option value="">All Creatives</option>
              {creativeOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
        </div>
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
        <div className="flex gap-2">
          <button onClick={() => mutate()} disabled={isValidating}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all disabled:opacity-40 shadow-sm">
            <RefreshCw size={12} className={isValidating ? "animate-spin" : ""} /> Refresh
          </button>
          <button onClick={handleExport} disabled={exporting || rows.length === 0}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-xl font-label text-xs font-bold hover:bg-primary/90 transition-all disabled:opacity-40 shadow-sm">
            <Download size={12} /> {exporting ? "Downloading…" : "Download CSV"}
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="card rounded-2xl overflow-hidden">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center mb-3">
              <Megaphone size={24} className="text-violet-400" />
            </div>
            <h3 className="font-bold text-[#44403c] text-base mb-1">No creative data yet</h3>
            <p className="text-sm text-[#a8a29e] max-w-sm leading-relaxed">
              Once your Meta ads start delivering and the daily sync runs, each ad appears here
              with its clicks, messages and cost breakdown.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  {["Creative", "Ad Set", "Clicks", "Messages", "No message", "Qualified", "Hot", "Sales",
                    "Spend", "CPC", "Cost / msg", "Cost / qual", "Cost / hot", "Revenue", "ROAS"].map((h, i) => (
                    <th key={h} className={cn(
                      "px-4 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider whitespace-nowrap",
                      i <= 1 ? "text-left" : "text-right",
                    )}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid/50">
                {rows.map((r) => (
                  <tr key={r.ad_creative_id} className="hover:bg-surface-low/60 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-label text-sm font-semibold text-on-surface">{r.creative_label}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-on-surface-muted">{r.adset_name ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-violet-700">{r.inline_link_clicks.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-on-surface">{r.messages.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.clicked_no_message.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.qualified}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.hot}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-on-surface">{r.sales}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.spend)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cpc)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_message)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_qualified)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_hot)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.revenue)}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-emerald-700">{ratio(r.roas)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-surface-mid bg-surface-low/50 font-bold">
                  <td className="px-4 py-3 text-sm">Total</td>
                  <td className="px-4 py-3"></td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.clicks.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.messages.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.noMsg.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3" colSpan={3}></td>
                  <td className="px-4 py-3 text-right tabular-nums">{money(totals.spend)}</td>
                  <td className="px-4 py-3" colSpan={4}></td>
                  <td className="px-4 py-3 text-right tabular-nums">{money(totals.revenue)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {totals.spend ? ratio(totals.revenue / totals.spend) : "—"}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
