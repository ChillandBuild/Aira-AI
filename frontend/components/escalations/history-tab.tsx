"use client";
import { useCallback, useEffect, useState } from "react";
import { Archive, CheckCircle2, Info, MessageSquare, RotateCcw, Search, Timer, TrendingUp, UserCheck, X } from "lucide-react";
import { toast } from "sonner";
import { cn, formatDateTime, formatDuration } from "@/lib/utils";
import {
  EMPTY_HISTORY_STATS,
  TRIGGERS,
  fetchHistory,
  reopenHandover,
  severityForWait,
  type HistoryStats,
  type ResolvedHandover,
} from "@/lib/escalations";
import { StatCard } from "@/components/escalations/stat-card";
import { ChannelCell, DurationCell, LeadCell, PersonCell, TableEmpty, TableSkeleton, TriggerChip } from "@/components/escalations/atoms";

const PAGE_SIZE = 25;

interface HistoryTabProps {
  onOpenChat: (leadId: string) => void;
  canReply: boolean;
  /** Reopening puts a handover back in the active pool, so the parent has to
   *  refresh its list and the rail badge. */
  onReopened: () => void;
}

export function HistoryTab({ onOpenChat, canReply, onReopened }: HistoryTabProps) {
  const [rows, setRows] = useState<ResolvedHandover[]>([]);
  const [stats, setStats] = useState<HistoryStats>(EMPTY_HISTORY_STATS);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [resolver, setResolver] = useState<string>("");
  const [reason, setReason] = useState<string>("");

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

  const filtered = Boolean(debounced || resolver || reason);
  const hasUnattributed = rows.some((r) => !r.resolved_by_name);

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      {/* ── KPI cards ── */}
      <div className="grid grid-cols-2 gap-3 px-6 py-5 xl:grid-cols-4">
        <StatCard
          icon={Archive}
          label="Resolved all-time"
          value={String(stats.total)}
          detail={stats.total ? "Every handover closed by a human" : "Nothing resolved yet"}
        />
        <StatCard
          icon={Timer}
          label="Median time to resolve"
          value={formatDuration(stats.median_seconds)}
          tone={stats.median_seconds !== null && stats.median_seconds > 86_400 ? "warning" : "positive"}
          detail="From handover to resolution"
        />
        <StatCard
          icon={UserCheck}
          label="Top resolver"
          value={stats.top_resolver ?? "Not recorded"}
          compact
          detail={stats.top_resolver ? `${stats.top_resolver_count} of ${stats.total} resolved` : "No attributed resolutions yet"}
          meter={stats.top_resolver ? { value: stats.top_resolver_count, max: stats.total } : undefined}
        />
        <StatCard
          icon={TrendingUp}
          label="Most common trigger"
          value={stats.top_reason ? (TRIGGERS[stats.top_reason]?.label ?? stats.top_reason) : "—"}
          compact
          detail={stats.top_reason ? "Why the AI hands over most often" : "No triggers recorded yet"}
        />
      </div>

      {/* ── toolbar ── */}
      <div className="flex flex-wrap items-center gap-3 px-6 pb-4">
        <div className="relative h-[34px] min-w-[200px] flex-[0_1_300px]">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or phone…"
            aria-label="Search resolved escalations"
            className="h-[34px] w-full rounded-[9px] border border-border bg-surface pl-[33px] pr-8 font-body text-[12.5px] text-ink outline-none transition-shadow placeholder:text-ink-muted focus:border-primary focus:ring-[3px] focus:ring-primary/15"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted transition-colors hover:text-ink"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            value={resolver}
            onChange={(e) => setResolver(e.target.value)}
            aria-label="Filter by resolver"
            className="h-[34px] cursor-pointer rounded-full border border-border bg-surface px-3.5 font-body text-[11.5px] font-semibold text-ink-secondary outline-none transition-colors hover:border-ink-muted focus:border-primary"
          >
            <option value="">Anyone</option>
            {stats.resolvers.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-label="Filter by reason"
            className="h-[34px] cursor-pointer rounded-full border border-border bg-surface px-3.5 font-body text-[11.5px] font-semibold text-ink-secondary outline-none transition-colors hover:border-ink-muted focus:border-primary"
          >
            <option value="">Any reason</option>
            {stats.reasons.map((r) => (
              <option key={r} value={r}>
                {TRIGGERS[r]?.label ?? r}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── table ── */}
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
            <table className="w-full min-w-[900px] border-collapse">
              <thead>
                <tr>
                  {[
                    { label: "Lead", w: "" },
                    { label: "Why escalated", w: "" },
                    { label: "Resolved by", w: "w-[160px]" },
                    { label: "Resolved", w: "w-[150px]" },
                    { label: "Time to resolve", w: "w-[120px]" },
                    { label: "Actions", w: "w-[190px]" },
                  ].map((c) => (
                    <th
                      key={c.label}
                      className={cn(
                        "sticky top-0 z-10 whitespace-nowrap border-b border-border bg-surface-low px-3.5 py-2.5 text-left font-heading text-[9.5px] font-semibold uppercase tracking-[0.09em] text-ink-muted first:pl-6 last:pr-6 last:text-right",
                        c.w
                      )}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              {loading ? (
                <TableSkeleton columns={6} />
              ) : (
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="group border-b border-border-subtle bg-surface transition-colors hover:bg-surface-low">
                      <td className="px-3.5 py-3 pl-6 align-middle">
                        <LeadCell lead={row.leads} />
                        <span className="mt-1 block">
                          <ChannelCell lead={row.leads} />
                        </span>
                      </td>
                      <td className="px-3.5 py-3 align-middle">
                        <TriggerChip reason={row.reason} />
                      </td>
                      <td className="px-3.5 py-3 align-middle">
                        <PersonCell name={row.resolved_by_name} empty="Not recorded" />
                      </td>
                      <td className="px-3.5 py-3 align-middle">
                        <span className="font-mono text-[11.5px] text-ink-secondary">
                          {row.resolved_at ? formatDateTime(row.resolved_at) : "—"}
                        </span>
                      </td>
                      <td className="px-3.5 py-3 align-middle">
                        <DurationCell
                          text={formatDuration(row.duration_seconds)}
                          severity={severityForWait(row.duration_seconds)}
                        />
                      </td>
                      <td className="px-3.5 py-3 pr-6 text-right align-middle">
                        <span className="inline-flex items-center justify-end gap-1.5 opacity-50 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
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
  );
}
