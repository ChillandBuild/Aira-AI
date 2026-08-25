"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Info, MessageSquare, RotateCcw, Search } from "lucide-react";
import { toast } from "sonner";
import { cn, formatDateTime, formatDuration } from "@/lib/utils";
import {
  EMPTY_HISTORY_STATS,
  fetchHistory,
  reopenHandover,
  severityForWait,
  type HistoryStats,
  type ResolvedHandover,
} from "@/lib/escalations";

import { ChannelCell, DurationCell, LeadCell, PersonCell, TableEmpty, TableSkeleton, TriggerChip } from "@/components/escalations/atoms";

const PAGE_SIZE = 25;

interface HistoryTabProps {
  onOpenChat: (leadId: string) => void;
  canReply: boolean;
  /** Reopening puts a handover back in the active pool, so the parent has to
   *  refresh its list and the rail badge. */
  onReopened: () => void;
  /** Search and filters live in the shared page header, so they arrive as
   *  props; the raw stats go back up because the header renders both the KPI
   *  cards and the resolver/reason dropdown options from them. */
  search: string;
  resolver: string;
  reason: string;
  onStatsChange: (stats: HistoryStats) => void;
}

export function HistoryTab({ onOpenChat, canReply, onReopened, search, resolver, reason, onStatsChange }: HistoryTabProps) {
  const [rows, setRows] = useState<ResolvedHandover[]>([]);
  const [stats, setStats] = useState<HistoryStats>(EMPTY_HISTORY_STATS);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(handle);
  }, [search]);

  const load = useCallback(async () => {
    try {
      const page = await fetchHistory({
        limit: PAGE_SIZE,
        offset: 0,
        q: debounced || undefined,
        resolver: resolver || undefined,
        reason: reason || undefined,
      });
      setRows(page.data);
      setTotal(page.total);
      setStats(page.stats);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [debounced, resolver, reason]);

  useEffect(() => {
    load();
  }, [load]);

  async function loadMore() {
    if (loadingMore || rows.length >= total) return;
    setLoadingMore(true);
    try {
      const page = await fetchHistory({
        limit: PAGE_SIZE,
        offset: rows.length,
        q: debounced || undefined,
        resolver: resolver || undefined,
        reason: reason || undefined,
      });
      setRows((prev) => {
        const seen = new Set(prev.map((r) => r.id));
        return [...prev, ...page.data.filter((r) => !seen.has(r.id))];
      });
      setTotal(page.total);
    } catch {
      toast.error("Couldn't load more history");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleReopen(row: ResolvedHandover) {
    if (!canReply) return;
    const prev = rows;
    setRows((rs) => rs.filter((r) => r.id !== row.id));
    setTotal((t) => Math.max(0, t - 1));
    try {
      await reopenHandover(row.id);
      toast.success("Reopened — it's back in the active queue");
      onReopened();
    } catch (err) {
      setRows(prev);
      setTotal((t) => t + 1);
      toast.error(err instanceof Error ? err.message : "Couldn't reopen");
    }
  }

  useEffect(() => {
    onStatsChange(stats);
  }, [stats, onStatsChange]);

  const filtered = Boolean(debounced || resolver || reason);
  const hasUnattributed = rows.some((r) => !r.resolved_by_name);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">

      {/* ── list (only this scrolls; filters stay in the header) ── */}
      <div className="flex flex-1 flex-col overflow-y-auto">
      {error ? (
        <TableEmpty
          icon={<Info size={24} className="text-ink-muted" />}
          title="Couldn't load history"
          body="The request didn't come back. It'll retry when you switch tabs."
        />
      ) : !loading && rows.length === 0 ? (
        <TableEmpty
          icon={filtered ? <Search size={24} className="text-ink-muted" /> : <CheckCircle2 size={24} className="text-ink-muted" />}
          title={filtered ? "No matches" : "Nothing resolved yet"}
          body={
            filtered
              ? "No resolved escalation matches those filters."
              : "Once you resolve an escalation it lands here, with who closed it and how long it took."
          }
        />
      ) : (
        <>
          <div className="flex-1 overflow-x-auto">
            <table className="w-full min-w-[1040px] border-collapse">
              <thead>
                <tr>
                  {[
                    { label: "Lead", w: "" },
                    { label: "Channel", w: "" },
                    { label: "Why escalated", w: "" },
                    { label: "Resolved by", w: "w-[196px]" },
                    { label: "Resolved", w: "w-[150px]" },
                    { label: "Time to resolve", w: "w-[120px]" },
                    { label: "Actions", w: "w-[190px]" },
                  ].map((c) => (
                    <th
                      key={c.label}
                      className={cn(
                        "sticky top-0 z-10 whitespace-nowrap border-b border-border bg-surface-low px-3.5 py-2.5 text-center font-heading text-[9.5px] font-semibold uppercase tracking-[0.09em] text-ink-muted first:pl-6 last:pr-6",
                        c.w
                      )}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              {loading ? (
                <TableSkeleton columns={7} />
              ) : (
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="group border-b border-border-subtle bg-surface transition-colors hover:bg-surface-low">
                      <td className="px-3.5 py-3 pl-6 text-center align-middle">
                        <LeadCell lead={row.leads} />
                      </td>
                      <td className="px-3.5 py-3 text-center align-middle">
                        <ChannelCell lead={row.leads} />
                      </td>
                      <td className="px-3.5 py-3 text-center align-middle">
                        <TriggerChip reason={row.reason} />
                      </td>
                      <td className="px-3.5 py-3 text-center align-middle">
                        <PersonCell name={row.resolved_by_name} empty="Not recorded" />
                      </td>
                      <td className="px-3.5 py-3 text-center align-middle">
                        <span className="font-mono text-[11.5px] text-ink-secondary">
                          {row.resolved_at ? formatDateTime(row.resolved_at) : "—"}
                        </span>
                      </td>
                      <td className="px-3.5 py-3 text-center align-middle">
                        <DurationCell
                          text={formatDuration(row.duration_seconds)}
                          severity={severityForWait(row.duration_seconds)}
                        />
                      </td>
                      <td className="px-3.5 py-3 pr-6 text-center align-middle">
                        <span className="inline-flex items-center justify-center gap-1.5 opacity-50 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                          <button
                            onClick={() => onOpenChat(row.lead_id)}
                            className="inline-flex h-7 w-[100px] items-center justify-center gap-1.5 rounded-lg border border-border bg-surface font-label text-[11px] font-bold text-ink transition-colors hover:border-ink-muted"
                          >
                            <MessageSquare size={13} /> Open chat
                          </button>
                          <button
                            onClick={() => handleReopen(row)}
                            disabled={!canReply}
                            title={canReply ? "Put this back in the active queue" : "You have read-only access to conversations"}
                            className="inline-flex h-7 w-[86px] items-center justify-center gap-1.5 rounded-lg border border-border bg-surface font-label text-[11px] font-bold text-ink-secondary transition-colors hover:border-ink-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <RotateCcw size={12} /> Reopen
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
          </div>

          <div className="flex items-center justify-between gap-4 px-6 py-4">
            <p className="font-body text-[11.5px] text-ink-muted">
              Showing {rows.length} of {total}
            </p>
            {rows.length < total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="h-[34px] rounded-lg border border-border bg-surface px-4 font-label text-[11.5px] font-bold text-ink transition-colors hover:border-ink-muted disabled:opacity-50"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>

          {hasUnattributed && (
            <div className="mx-6 mb-6 flex items-start gap-2 rounded-[9px] border border-amber-200 bg-amber-50 px-3.5 py-2.5">
              <Info size={14} className="mt-px flex-shrink-0 text-amber-700" />
              <p className="font-body text-[11.5px] leading-relaxed text-amber-800">
                Escalations resolved before resolver tracking shipped show as <em>Not recorded</em>. Everything
                resolved from now on is attributed.
              </p>
            </div>
          )}
        </>
      )}
      </div>
    </div>
  );
}
