"use client";
import { useCallback, useEffect, useState } from "react";
import { api, DealSource, DealStage, DealSummary } from "@/lib/api";
import { StageBadge } from "@/components/deals/StageBadge";
import { SourceBadge } from "@/components/deals/SourceBadge";
import { formatRupees } from "@/components/deals/money";

const STAGE_OPTIONS: { value: DealStage | ""; label: string }[] = [
  { value: "", label: "All stages" },
  { value: "quoted", label: "Quoted" },
  { value: "awaiting_payment", label: "Awaiting payment" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
];

const SOURCE_OPTIONS: { value: DealSource | ""; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "form", label: "Form" },
  { value: "call", label: "Call" },
  { value: "walk_in", label: "Walk-in" },
  { value: "manual", label: "Manual" },
  { value: "indiamart", label: "IndiaMART" },
  { value: "justdial", label: "JustDial" },
];

export function ListTab({ onOpenDeal, reloadToken }: { onOpenDeal: (id: string) => void; reloadToken: number }) {
  const [stage, setStage] = useState<DealStage | "">("");
  const [source, setSource] = useState<DealSource | "">("");
  const [month, setMonth] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<DealSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);

  const loadFirstPage = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const page = await api.deals.list({
        stage: stage || undefined,
        source: source || undefined,
        month: month || undefined,
        q: query || undefined,
      });
      setRows(page.data);
      setCursor(page.next_cursor);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [stage, source, month, query]);

  useEffect(() => {
    loadFirstPage();
  }, [loadFirstPage, reloadToken]);

  async function loadMore() {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.deals.list({
        stage: stage || undefined,
        source: source || undefined,
        month: month || undefined,
        q: query || undefined,
        cursor,
      });
      setRows((prev) => [...prev, ...page.data]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-4">
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value as DealStage | "")}
          className="rounded-xl border border-border px-3 py-2 font-body text-sm text-ink"
        >
          {STAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as DealSource | "")}
          className="rounded-xl border border-border px-3 py-2 font-body text-sm text-ink"
        >
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="rounded-xl border border-border px-3 py-2 font-body text-sm text-ink"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, phone or deal no."
          className="min-w-[220px] flex-1 rounded-xl border border-border px-3 py-2 font-body text-sm"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-3 p-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-xl bg-border-subtle" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="font-body text-sm text-ink-muted">Could not load deals.</p>
            <button
              type="button"
              onClick={loadFirstPage}
              className="rounded-xl bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90"
            >
              Retry
            </button>
          </div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center font-body text-sm text-ink-muted">No deals match these filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Deal</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Customer</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Items</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Stage</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Source</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Total</th>
                  <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((deal) => (
                  <tr
                    key={deal.id}
                    onClick={() => onOpenDeal(deal.id)}
                    className="cursor-pointer border-b border-border-subtle hover:bg-surface-subtle"
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-label text-sm font-semibold text-ink">{deal.deal_label}</td>
                    <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                      {deal.lead.name || deal.lead.phone || "—"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-ink-muted">{deal.item_summary}</td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <StageBadge stage={deal.stage} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <SourceBadge source={deal.source} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-display text-sm font-bold text-ink">
                      {formatRupees(deal.total_paise)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted">
                      {new Date(deal.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cursor && (
              <div className="p-4 text-center">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="rounded-xl border border-border px-4 py-2 font-label text-xs font-bold text-ink hover:bg-surface-subtle disabled:opacity-50"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
