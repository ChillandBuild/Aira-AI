"use client";
import { useCallback, useEffect, useState } from "react";
import { api, DealFilters, DealStage, DealSummary, DealSummaryStats } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { SourceBadge } from "@/components/deals/SourceBadge";
import { formatRupees } from "@/components/deals/money";
import { timeAgo } from "@/lib/utils";
import { getDealTags } from "@/lib/deal-tags";
import { shortRupees } from "@/lib/deal-filters";

const COLUMN_ORDER: DealStage[] = ["quoted", "awaiting_payment", "won", "lost"];

const COLUMN_LABEL: Record<DealStage, string> = {
  quoted: "Quoted",
  awaiting_payment: "Awaiting payment",
  won: "Won",
  lost: "Lost",
};

const COLUMN_TONE: Record<DealStage, string> = {
  quoted: "border-t-slate-300",
  awaiting_payment: "border-t-amber-400",
  won: "border-t-emerald-400",
  lost: "border-t-rose-300",
};

const BRAND_COLORS = ["#038285", "#0A1528", "#6366f1", "#b45309", "#be123c", "#047857"];

function getColorForLead(leadId: string): string {
  let hash = 0;
  for (let i = 0; i < leadId.length; i++) {
    hash = ((hash << 5) - hash) + leadId.charCodeAt(i);
    hash = hash & hash;
  }
  return BRAND_COLORS[Math.abs(hash) % BRAND_COLORS.length];
}

function Avatar({ name, phone, leadId }: { name?: string | null; phone?: string | null; leadId: string }) {
  // Two-letter initials
  let initials = "?";
  if (name) {
    const words = name.trim().split(/\s+/);
    initials = words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    if (initials.length === 1) initials = initials[0];
  } else if (phone) {
    initials = phone.substring(0, 2).toUpperCase();
  }
  const color = getColorForLead(leadId);
  return (
    <div
      style={{ backgroundColor: color }}
      className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white shrink-0"
    >
      {initials}
    </div>
  );
}

function DealCard({ deal, onOpen }: { deal: DealSummary; onOpen: () => void }) {
  const when = deal.won_at || deal.lost_at || deal.created_at;
  const tags = getDealTags(deal);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-xl border border-border bg-white p-3 text-left space-y-1.5 transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Avatar name={deal.lead.name} phone={deal.lead.phone} leadId={deal.lead.id} />
          <p className="font-label text-xs font-semibold text-ink truncate">
            {deal.lead.name || deal.lead.phone || "Unknown"}
          </p>
        </div>
        <p className="font-display text-sm font-bold text-ink shrink-0">{formatRupees(deal.total_paise)}</p>
      </div>
      <p className="font-body text-[11px] text-ink-muted truncate">{deal.deal_label}</p>
      <p className="font-body text-[11px] text-ink-muted truncate">{deal.item_summary}</p>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {tags.map((tag) => (
            <span
              key={tag.key}
              className={`inline-flex items-center rounded-full border px-2 py-0.5 font-label text-[10px] font-bold whitespace-nowrap ${
                tag.tone === "muted"
                  ? "bg-slate-50 text-slate-600 border-slate-200"
                  : tag.tone === "warning"
                  ? "bg-amber-50 text-amber-700 border-amber-200"
                  : "bg-rose-50 text-rose-600 border-rose-200"
              }`}
            >
              {tag.label}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <SourceBadge source={deal.source} />
        <span className="font-body text-[10px] text-ink-muted shrink-0">{timeAgo(when)}</span>
      </div>
    </button>
  );
}

function BoardColumn({
  stage,
  deals,
  count,
  total,
  onOpenDeal,
}: {
  stage: DealStage;
  deals: DealSummary[];
  count: number;
  total: number;
  onOpenDeal: (id: string) => void;
}) {
  const showMore = deals.length < count;
  return (
    <div className={`flex-1 min-w-[260px] rounded-2xl border border-border border-t-4 bg-surface-subtle ${COLUMN_TONE[stage]}`}>
      <div className="border-b border-border p-3">
        <div className="flex items-center justify-between">
          <p className="font-label text-xs font-bold text-ink">{COLUMN_LABEL[stage]}</p>
          <p className="font-body text-[11px] text-ink-muted">{count}</p>
        </div>
        <p className="mt-0.5 font-display text-lg font-bold text-ink">{shortRupees(total)}</p>
      </div>
      <div className="max-h-[calc(100vh-360px)] space-y-2 overflow-y-auto p-2">
        {deals.length === 0 && (
          <p className="py-6 text-center font-body text-[11px] text-ink-muted">Nothing here</p>
        )}
        {deals.map((deal) => (
          <DealCard key={deal.id} deal={deal} onOpen={() => onOpenDeal(deal.id)} />
        ))}
        {showMore && (
          <p className="py-1 text-center font-body text-[10px] text-ink-muted">
            Showing {deals.length} of {count} — switch to Table to see all
          </p>
        )}
      </div>
    </div>
  );
}

interface ColumnData {
  deals: DealSummary[];
  count: number;
  total: number;
}

export function BoardTab({
  filters,
  summary,
  onOpenDeal,
  reloadToken,
}: {
  filters: DealFilters & { view?: string };
  summary: DealSummaryStats | null;
  onOpenDeal: (id: string) => void;
  reloadToken: number;
}) {
  const [columns, setColumns] = useState<Record<DealStage, ColumnData>>({
    quoted: { deals: [], count: 0, total: 0 },
    awaiting_payment: { deals: [], count: 0, total: 0 },
    won: { deals: [], count: 0, total: 0 },
    lost: { deals: [], count: 0, total: 0 },
  });
  const [loading, setLoading] = useState(true);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);

      const requests = COLUMN_ORDER.map((stage) =>
        api.deals.list(
          { ...filters, stage },
          { limit: 100, sort: "created_at", dir: "desc" }
        )
      );

      const results = await Promise.all(requests);

      const newColumns: Record<DealStage, ColumnData> = {
        quoted: { deals: [], count: 0, total: 0 },
        awaiting_payment: { deals: [], count: 0, total: 0 },
        won: { deals: [], count: 0, total: 0 },
        lost: { deals: [], count: 0, total: 0 },
      };

      results.forEach((result, idx) => {
        const stage = COLUMN_ORDER[idx];
        newColumns[stage] = {
          deals: result.data,
          count: result.total,
          total: result.data.reduce((sum, d) => sum + d.total_paise, 0),
        };
      });

      setColumns(newColumns);
      setLoadedOnce(true);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load, reloadToken]);

  usePolling(load, 30000);

  if (loading && !loadedOnce) {
    return (
      <div className="flex gap-4 p-6">
        {COLUMN_ORDER.map((stage) => (
          <div key={stage} className="h-64 flex-1 animate-pulse rounded-2xl bg-border-subtle" />
        ))}
      </div>
    );
  }

  if (error && !loadedOnce) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="font-body text-sm text-ink-muted">Could not load the board.</p>
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

  return (
    <div className="space-y-3 p-6">
      {error && (
        <p className="font-body text-xs text-amber-600">Could not refresh just now — showing the last loaded numbers.</p>
      )}
      <div className="flex gap-4 overflow-x-auto pb-2">
        {COLUMN_ORDER.map((stage) => (
          <BoardColumn
            key={stage}
            stage={stage}
            deals={columns[stage].deals}
            // The summary covers every matching deal; the loaded cards stop at 100.
            count={summary?.stages[stage].count ?? columns[stage].count}
            total={summary?.stages[stage].total_paise ?? columns[stage].total}
            onOpenDeal={onOpenDeal}
          />
        ))}
      </div>
    </div>
  );
}
