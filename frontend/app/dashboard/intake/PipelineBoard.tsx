"use client";
import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api, CatalogQuote, IntakeBoard, IntakeBoardColumn, IntakeBoardSession, IntakeStatus } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";

const COLUMN_ORDER: IntakeStatus[] = ["awaiting_payment", "paid", "resolved", "cancelled"];

const COLUMN_TONE: Record<IntakeStatus, string> = {
  awaiting_payment: "border-t-amber-400",
  paid: "border-t-emerald-400",
  resolved: "border-t-slate-300",
  cancelled: "border-t-rose-300",
};

function formatRupees(paise: number): string {
  return `₹${Math.round(paise / 100).toLocaleString("en-IN")}`;
}

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function SessionCard({ session }: { session: IntakeBoardSession }) {
  const amountPaise = session.total_amount_paise ?? session.amount_paise ?? 0;
  return (
    <div className="rounded-xl border border-border bg-white p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-label text-xs font-semibold text-ink truncate">
          {session.leads?.name || session.leads?.phone || "Unknown lead"}
        </p>
        <p className="font-display text-xs font-bold text-ink shrink-0">{formatRupees(amountPaise)}</p>
      </div>
      {session.package_name && (
        <p className="font-body text-[11px] text-ink-muted truncate">{session.package_name}</p>
      )}
      <div className="flex items-center justify-between">
        <p className="font-body text-[10px] text-ink-muted">
          {session.paid_at ? `Paid ${formatDate(session.paid_at)}` : formatDate(session.created_at)}
        </p>
        {session.payment_link && session.status === "awaiting_payment" && (
          <a
            href={session.payment_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-label text-[10px] font-bold text-ink-muted hover:text-ink"
          >
            <ExternalLink size={10} /> Link
          </a>
        )}
      </div>
    </div>
  );
}

function BoardColumn({ status, column }: { status: IntakeStatus; column: IntakeBoardColumn }) {
  return (
    <div className={`flex-1 min-w-[240px] rounded-2xl border border-border border-t-4 bg-surface-subtle ${COLUMN_TONE[status]}`}>
      <div className="p-3 border-b border-border">
        <div className="flex items-center justify-between">
          <p className="font-label text-xs font-bold text-ink">{column.label}</p>
          <p className="font-body text-[11px] text-ink-muted">{column.count}</p>
        </div>
        <p className="font-display text-lg font-bold text-ink mt-0.5">{formatRupees(column.total_paise)}</p>
      </div>
      <div className="p-2 space-y-2 max-h-[calc(100vh-320px)] overflow-y-auto">
        {column.sessions.length === 0 && (
          <p className="font-body text-[11px] text-ink-muted text-center py-6">Nothing here</p>
        )}
        {column.sessions.map((session) => (
          <SessionCard key={session.id} session={session} />
        ))}
        {column.has_more && (
          <p className="font-body text-[10px] text-ink-muted text-center py-1">
            + more not shown — use the table view to see all
          </p>
        )}
      </div>
    </div>
  );
}

function CatalogQuoteCard({ quote }: { quote: CatalogQuote }) {
  return (
    <div className="rounded-xl border border-border bg-white p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-label text-xs font-semibold text-ink truncate">
          {quote.leads?.name || quote.leads?.phone || "Unknown lead"}
        </p>
        <p className="font-display text-xs font-bold text-ink shrink-0">
          {formatRupees(quote.amount_paise)}
          {quote.amount_is_estimate && <span className="text-ink-muted font-normal">*</span>}
        </p>
      </div>
      <p className="font-body text-[11px] text-ink-muted truncate">{quote.item_name}</p>
      <div className="flex items-center justify-between">
        <p className="font-body text-[10px] text-ink-muted">{formatDate(quote.created_at)}</p>
        <span
          className={`font-label text-[9px] font-bold uppercase tracking-wide ${
            quote.source === "manual" ? "text-emerald-600" : "text-ink-muted"
          }`}
        >
          {quote.source === "manual" ? "Entered by staff" : "AI quote"}
        </span>
      </div>
    </div>
  );
}

function CatalogQuotesSection({ data }: { data: IntakeBoard["catalog_quotes"] }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface-subtle p-3">
      <div className="flex items-center justify-between mb-1">
        <div>
          <p className="font-label text-xs font-bold text-ink">{data.label}</p>
          <p className="font-body text-[10px] text-ink-muted">
            Quoted in chat or entered by staff — not a payment stage, shown for visibility only
          </p>
        </div>
        <div className="text-right">
          <p className="font-body text-[11px] text-ink-muted">{data.count}</p>
          <p className="font-display text-sm font-bold text-ink">{formatRupees(data.total_paise)}</p>
        </div>
      </div>
      {data.quotes.length > 0 && (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {data.quotes.map((q) => (
            <CatalogQuoteCard key={q.id} quote={q} />
          ))}
        </div>
      )}
      {data.quotes.some((q) => q.amount_is_estimate) && (
        <p className="font-body text-[10px] text-ink-muted mt-2">* estimated — the AI recommended this item, not confirmed as bought</p>
      )}
    </div>
  );
}

export function PipelineBoard() {
  const [board, setBoard] = useState<IntakeBoard | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setBoard(await api.intake.board());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, 30000);

  if (!board) {
    return (
      <div className="p-6 flex gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex-1 h-64 rounded-2xl bg-border-subtle animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      {error && (
        <p className="font-body text-xs text-amber-600">
          Could not refresh just now — showing the last loaded numbers.
        </p>
      )}
      <div className="flex gap-4 overflow-x-auto pb-2">
        {COLUMN_ORDER.map((status) => (
          <BoardColumn key={status} status={status} column={board.columns[status]} />
        ))}
      </div>
      {board.catalog_quotes.count > 0 && <CatalogQuotesSection data={board.catalog_quotes} />}
    </div>
  );
}
