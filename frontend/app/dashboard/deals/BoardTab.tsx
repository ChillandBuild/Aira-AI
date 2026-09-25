"use client";
import { useCallback, useEffect, useState } from "react";
import { api, DealBoard, DealStage, DealSummary } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { SourceBadge } from "@/components/deals/SourceBadge";
import { formatRupees } from "@/components/deals/money";
import { timeAgo } from "@/lib/utils";

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

function DealCard({ deal, onOpen }: { deal: DealSummary; onOpen: () => void }) {
  const when = deal.won_at || deal.lost_at || deal.created_at;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-xl border border-border bg-white p-3 text-left space-y-1.5 transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-label text-xs font-semibold text-ink truncate">
          {deal.lead.name || deal.lead.phone || "Unknown customer"}
        </p>
        <p className="font-display text-sm font-bold text-ink shrink-0">{formatRupees(deal.total_paise)}</p>
      </div>
      <p className="font-body text-[11px] text-ink-muted truncate">{deal.deal_label}</p>
      <p className="font-body text-[11px] text-ink-muted truncate">{deal.item_summary}</p>
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <SourceBadge source={deal.source} />
        <span className="font-body text-[10px] text-ink-muted shrink-0">{timeAgo(when)}</span>
      </div>
    </button>
  );
}

function BoardColumn({
  stage,
  column,
  onOpenDeal,
}: {
  stage: DealStage;
  column: DealBoard["columns"][DealStage];
  onOpenDeal: (id: string) => void;
}) {
  return (
    <div className={`flex-1 min-w-[260px] rounded-2xl border border-border border-t-4 bg-surface-subtle ${COLUMN_TONE[stage]}`}>
      <div className="border-b border-border p-3">
        <div className="flex items-center justify-between">
          <p className="font-label text-xs font-bold text-ink">{COLUMN_LABEL[stage]}</p>
          <p className="font-body text-[11px] text-ink-muted">{column.count}</p>
        </div>
        <p className="mt-0.5 font-display text-lg font-bold text-ink">{formatRupees(column.total_paise)}</p>
        {(stage === "won" || stage === "lost") && (
          <p className="font-body text-[10px] text-ink-muted">last 30 days</p>
        )}
      </div>
      <div className="max-h-[calc(100vh-360px)] space-y-2 overflow-y-auto p-2">
        {column.deals.length === 0 && (
          <p className="py-6 text-center font-body text-[11px] text-ink-muted">Nothing here</p>
        )}
        {column.deals.map((deal) => (
          <DealCard key={deal.id} deal={deal} onOpen={() => onOpenDeal(deal.id)} />
        ))}
        {column.has_more && (
          <p className="py-1 text-center font-body text-[10px] text-ink-muted">
            + more not shown — use the List tab to see all
          </p>
        )}
      </div>
    </div>
  );
}

export function BoardTab({ onOpenDeal, reloadToken }: { onOpenDeal: (id: string) => void; reloadToken: number }) {
  const [board, setBoard] = useState<DealBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.deals.board();
      setBoard(data);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, reloadToken]);
  usePolling(load, 30000);

  if (loading) {
    return (
      <div className="flex gap-4 p-6">
        {COLUMN_ORDER.map((stage) => (
          <div key={stage} className="h-64 flex-1 animate-pulse rounded-2xl bg-border-subtle" />
        ))}
      </div>
    );
  }

  if (error && !board) {
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

  if (!board) return null;

  return (
    <div className="space-y-3 p-6">
      {error && (
        <p className="font-body text-xs text-amber-600">Could not refresh just now — showing the last loaded numbers.</p>
      )}
      <div className="flex gap-4 overflow-x-auto pb-2">
        {COLUMN_ORDER.map((stage) => (
          <BoardColumn key={stage} stage={stage} column={board.columns[stage]} onOpenDeal={onOpenDeal} />
        ))}
      </div>
    </div>
  );
}
