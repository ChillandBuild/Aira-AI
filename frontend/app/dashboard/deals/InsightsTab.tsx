"use client";
import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api, API_URL, DealSource, DealStats, getAuthHeaders } from "@/lib/api";
import { formatRupees } from "@/components/deals/money";
import { SourceBadge } from "@/components/deals/SourceBadge";
import { istTodayIso } from "@/lib/utils";

function currentMonth(): string {
  return istTodayIso().slice(0, 7);
}

export function InsightsTab() {
  const [month, setMonth] = useState(currentMonth());
  const [stats, setStats] = useState<DealStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setStats(await api.deals.stats(month));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    load();
  }, [load]);

  async function downloadExport() {
    setDownloading(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}${api.deals.exportPath(month, "xlsx")}`, { headers: auth });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `deals-${month}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(true);
    } finally {
      setDownloading(false);
    }
  }

  if (loading && !stats) {
    return (
      <div className="grid grid-cols-2 gap-4 p-6 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-border-subtle" />
        ))}
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="font-body text-sm text-ink-muted">Could not load insights.</p>
        <button
          type="button"
          onClick={load}
          className="rounded-xl bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!stats) return null;

  const maxDay = Math.max(1, ...stats.by_day.map((d) => d.total_paise));
  const sources = Object.entries(stats.by_source) as [DealSource, { count: number; total_paise: number }][];
  const maxSource = Math.max(1, ...sources.map(([, v]) => v.total_paise));

  const cards = [
    { label: "Won total", value: formatRupees(stats.won_total_paise), sub: `${stats.won_count} deals`, tone: "border-t-emerald-400" },
    { label: "Open pipeline", value: formatRupees(stats.open_total_paise), sub: `${stats.open_count} deals`, tone: "border-t-amber-400" },
    { label: "Lost", value: stats.lost_count, sub: "this month", tone: "border-t-rose-400" },
    { label: "Won deals", value: stats.won_count, sub: "this month", tone: "border-t-teal-400" },
  ];

  return (
    <div className="max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="rounded-xl border border-border px-3 py-2 font-body text-sm text-ink"
        />
      </div>

      {error && (
        <p className="font-body text-xs text-amber-600">Could not refresh just now — showing the last loaded numbers.</p>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className={`rounded-2xl border border-border border-t-4 bg-white p-4 ${c.tone}`}>
            <p className="font-display text-2xl font-bold leading-none text-ink">{c.value}</p>
            <p className="mt-1.5 font-label text-xs font-semibold text-ink">{c.label}</p>
            <p className="font-body text-[11px] text-ink-muted">{c.sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-border bg-white p-4">
          <p className="mb-3 font-label text-xs font-semibold text-ink">Revenue by source</p>
          {sources.length === 0 ? (
            <p className="font-body text-xs text-ink-muted">No won deals yet this month.</p>
          ) : (
            <div className="space-y-2">
              {sources.map(([src, v]) => (
                <div key={src} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <SourceBadge source={src} />
                    <span className="font-body text-xs text-ink">{formatRupees(v.total_paise)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-border-subtle">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.max(4, (v.total_paise / maxSource) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-white p-4">
          <p className="mb-3 font-label text-xs font-semibold text-ink">Won revenue by day</p>
          {stats.by_day.length === 0 ? (
            <p className="font-body text-xs text-ink-muted">No won deals yet this month.</p>
          ) : (
            <div className="flex h-28 items-end gap-1">
              {stats.by_day.map((d) => (
                <div key={d.date} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={`${d.date}: ${formatRupees(d.total_paise)}`}>
                  <div
                    className={`w-full rounded-t-md ${d.total_paise > 0 ? "bg-primary-500" : "bg-border-subtle"}`}
                    style={{ height: `${Math.max(4, (d.total_paise / maxDay) * 96)}px` }}
                  />
                  <span className="font-body text-[9px] text-ink-muted">{d.date.slice(8)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-border bg-white p-4">
          <p className="mb-3 font-label text-xs font-semibold text-ink">Top items</p>
          {stats.top_items.length === 0 ? (
            <p className="font-body text-xs text-ink-muted">Nothing sold yet this month.</p>
          ) : (
            <div className="space-y-2">
              {stats.top_items.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <p className="font-body text-sm text-ink truncate">{item.name} <span className="text-ink-muted">×{item.qty}</span></p>
                  <p className="font-body text-sm font-semibold text-ink">{formatRupees(item.total_paise)}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-white p-4">
          <p className="mb-3 font-label text-xs font-semibold text-ink">Low stock</p>
          {stats.low_stock.length === 0 ? (
            <p className="font-body text-xs text-ink-muted">Nothing running low.</p>
          ) : (
            <div className="space-y-2">
              {stats.low_stock.map((item) => (
                <div key={item.id} className="flex items-center justify-between">
                  <p className="font-body text-sm text-ink truncate">{item.name}</p>
                  <p className="font-body text-xs text-amber-700">
                    {item.stock_quantity} in stock · {item.held_quantity} held
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div>
        <button
          type="button"
          onClick={downloadExport}
          disabled={downloading}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90 disabled:opacity-50"
        >
          <Download size={12} /> {downloading ? "Preparing…" : "Download month for auditor"}
        </button>
        <p className="mt-1.5 font-body text-[11px] text-ink-muted">
          This file uses the business details from Settings → Business details.
        </p>
      </div>
    </div>
  );
}
