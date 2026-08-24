"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, MessageSquare, Search, UserCog, X } from "lucide-react";
import { toast } from "sonner";
import { cn, formatDuration, secondsSince } from "@/lib/utils";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { usePolling } from "@/hooks/usePolling";
import {
  assignHandover,
  channelOf,
  fetchCallers,
  fetchHandovers,
  reopenHandover,
  resolveHandover,
  severityForWait,
  type Caller,
  type Handover,
} from "@/lib/escalations";
import { StatBar, type StatItem } from "@/components/escalations/stat-bar";
import { HistoryTab } from "@/components/escalations/history-tab";
import { ChannelCell, DurationCell, LeadCell, PersonCell, TableEmpty, TableSkeleton, TriggerChip } from "@/components/escalations/atoms";

type Tab = "active" | "history";

/** Severity spine on the first cell. Written as explicit hex because Tailwind
 *  can't resolve a theme colour inside an arbitrary shadow at build time. */
const SPINE = {
  ok: "shadow-[inset_3px_0_0_#059669]",
  warn: "shadow-[inset_3px_0_0_#d97706]",
  bad: "shadow-[inset_3px_0_0_#e11d48]",
} as const;

const DAY = 86_400;

interface EscalationPanelProps {
  onReply: (leadId: string) => void;
  onCountChange: (count: number) => void;
  currentCallerId?: string | null;
  currentCallerName?: string | null;
  canReplyToConversations?: boolean;
}

export function EscalationPanel({
  onReply,
  onCountChange,
  currentCallerId,
  currentCallerName,
  canReplyToConversations = false,
}: EscalationPanelProps) {
  const { role } = useAuthRole();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [tab, setTab] = useState<Tab>(() => (searchParams.get("tab") === "history" ? "history" : "active"));
  const [handovers, setHandovers] = useState<Handover[]>([]);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [loading, setLoading] = useState(true);
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [quickFilter, setQuickFilter] = useState<"all" | "unassigned" | "mine" | "breaching">("all");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const visibleHandovers = useMemo(
    () =>
      role === "owner"
        ? handovers
        : handovers.filter((h) => !h.assigned_to || h.assigned_to === currentCallerId),
    [handovers, role, currentCallerId]
  );

  const filteredHandovers = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return visibleHandovers.filter((h) => {
      if (quickFilter === "unassigned" && h.assigned_to) return false;
      if (quickFilter === "mine" && h.assigned_to !== currentCallerId) return false;
      if (quickFilter === "breaching" && (secondsSince(h.opened_at) ?? 0) < DAY) return false;
      if (!q) return true;
      const ch = channelOf(h.leads);
      return [
        h.leads?.name,
        h.leads?.phone,
        h.leads?.tg_username,
        h.leads?.ig_user_id,
        h.leads?.fb_user_id,
        h.reason,
        ch.label,
      ]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [visibleHandovers, searchQuery, quickFilter, currentCallerId]);

  const load = useCallback(async () => {
    const [hs, cs] = await Promise.all([fetchHandovers(), fetchCallers()]);
    setHandovers(hs);
    setCallers(cs);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, 15000);

  useEffect(() => {
    if (!loading) onCountChange(visibleHandovers.length);
  }, [visibleHandovers.length, loading, onCountChange]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setAssigningId(null);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function switchTab(next: Tab) {
    setTab(next);
    const params = new URLSearchParams(searchParams.toString());
    if (next === "history") params.set("tab", "history");
    else params.delete("tab");
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }

  // ── stats for the KPI row ──
  const stats = useMemo(() => {
    const waits = visibleHandovers
      .map((h) => secondsSince(h.opened_at))
      .filter((s): s is number => s !== null);
    return {
      open: visibleHandovers.length,
      unassigned: visibleHandovers.filter((h) => !h.assigned_to).length,
      mine: visibleHandovers.filter((h) => h.assigned_to === currentCallerId).length,
      breaching: waits.filter((s) => s >= DAY).length,
      longest: waits.length ? Math.max(...waits) : null,
    };
  }, [visibleHandovers, currentCallerId]);

  const activeStats: StatItem[] = useMemo(
    () => [
      {
        label: "Open now",
        value: String(stats.open),
        tone: stats.open === 0 ? "positive" : stats.breaching > 0 ? "critical" : "warning",
        hint: stats.open === 0 ? "Queue is clear" : `${stats.unassigned} waiting for an owner`,
      },
      {
        label: "Longest wait",
        value: formatDuration(stats.longest),
        tone: stats.longest !== null && stats.longest >= DAY ? "critical" : "positive",
        hint: stats.longest !== null && stats.longest >= DAY ? "Past the 24h line" : "Inside the 24h line",
      },
      {
        label: "Breaching 24h",
        value: String(stats.breaching),
        tone: stats.breaching > 0 ? "critical" : "positive",
        hint: stats.open ? `of ${stats.open} open` : "Nothing open",
      },
      {
        label: role === "owner" ? "Unassigned" : "Assigned to me",
        value: String(role === "owner" ? stats.unassigned : stats.mine),
        tone: role === "owner" && stats.unassigned > 0 ? "warning" : "neutral",
        hint: role === "owner" ? "Nobody has picked these up" : "Yours to handle",
      },
    ],
    [stats, role]
  );

  const myName = callers.find((c) => c.id === currentCallerId)?.name ?? currentCallerName ?? "You";

  async function handleResolve(handover: Handover) {
    if (!canReplyToConversations) return;
    const prev = handovers;
    setHandovers((hs) => hs.filter((h) => h.id !== handover.id));
    try {
      await resolveHandover(handover.id);
      toast.success("Escalation resolved", {
        duration: 8000,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await reopenHandover(handover.id);
              toast.success("Reopened — it's back in the queue");
              load();
            } catch {
              toast.error("Couldn't undo — reopen it from History");
            }
          },
        },
      });
    } catch (err) {
      setHandovers(prev);
      toast.error(err instanceof Error ? err.message : "Couldn't resolve");
    }
  }

  async function handleAssign(handoverId: string, callerId: string, callerName: string) {
    setAssigningId(null);
    const prev = handovers;
    setHandovers((hs) =>
      hs.map((h) => (h.id === handoverId ? { ...h, assigned_to: callerId, caller_name: callerName } : h))
    );
    try {
      await assignHandover(handoverId, callerId);
      toast.success(`Assigned to ${callerName}`);
    } catch {
      setHandovers(prev);
      toast.error("Couldn't assign");
    }
  }

  async function handleClaim(handover: Handover) {
    if (!canReplyToConversations) return;
    if (!currentCallerId) {
      toast.error("A telecaller profile is required to pick up an escalation");
      return;
    }
    const prev = handovers;
    setHandovers((hs) =>
      hs.map((h) => (h.id === handover.id ? { ...h, assigned_to: currentCallerId, caller_name: myName } : h))
    );
    try {
      await assignHandover(handover.id, currentCallerId);
      toast.success("Claimed — you're handling this lead");
    } catch {
      setHandovers(prev);
      toast.error("Couldn't claim");
    }
  }

  const readOnlyTitle = canReplyToConversations ? undefined : "You have read-only access to conversations";
  const QUICK_FILTERS = [
    { key: "all", label: "All" },
    { key: "unassigned", label: "Unassigned" },
    { key: "mine", label: "Mine" },
    { key: "breaching", label: "Over 24h" },
  ] as const;

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-background">
      {/* ── header + tabs ── */}
      <div className="flex-shrink-0 px-6 pt-6">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
          <div className="min-w-0">
            <h2 className="font-heading text-[23px] font-bold tracking-[-0.028em] text-ink">Escalations</h2>
            <p className="mt-1 font-body text-[12.5px] font-medium text-ink-secondary">
              Conversations the AI handed to a human.
            </p>
          </div>
          {tab === "active" && !loading && <StatBar items={activeStats} />}
        </div>

        <div className="-mx-6 mt-[18px] flex items-end border-b border-border px-6" role="tablist" aria-label="Escalation views">
          {([
            { key: "active", label: "Active", count: visibleHandovers.length, critical: true },
            { key: "history", label: "History", count: null, critical: false },
          ] as const).map((t, i) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => switchTab(t.key)}
              className={cn(
                "-mb-px flex h-9 items-center gap-[7px] border-b-2 px-1 pb-2.5 font-heading text-[13px] font-bold tracking-[-0.01em] transition-colors",
                i > 0 && "ml-[18px]",
                tab === t.key
                  ? "border-primary text-primary"
                  : "border-transparent text-ink-secondary hover:text-ink"
              )}
            >
              {t.label}
              {t.count !== null && t.count > 0 && (
                <span
                  className={cn(
                    "rounded-full px-[7px] py-[3px] font-mono text-[10px] font-bold leading-none tabular-nums",
                    tab === t.key ? "bg-rose-100 text-danger" : "bg-surface-mid text-ink-secondary"
                  )}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {tab === "history" ? (
        <HistoryTab onOpenChat={onReply} canReply={canReplyToConversations} onReopened={load} />
      ) : (
        <div className="flex flex-1 flex-col overflow-y-auto">
          {/* ── toolbar ── */}
          <div className="flex flex-wrap items-center gap-3 px-6 pb-4">
            <div className="relative h-[34px] min-w-[200px] flex-[0_1_300px]">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search name, phone, reason…"
                aria-label="Search escalations"
                className="h-[34px] w-full rounded-[9px] border border-border bg-surface pl-[33px] pr-8 font-body text-[12.5px] text-ink outline-none transition-shadow placeholder:text-ink-muted focus:border-primary focus:ring-[3px] focus:ring-primary/15"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  aria-label="Clear search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted transition-colors hover:text-ink"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              {QUICK_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setQuickFilter(f.key)}
                  aria-pressed={quickFilter === f.key}
                  className={cn(
                    "inline-flex h-[34px] items-center rounded-full border px-3.5 font-body text-[11.5px] font-semibold transition-colors",
                    quickFilter === f.key
                      ? "border-primary-muted bg-primary-light text-primary"
                      : "border-border bg-surface text-ink-secondary hover:border-ink-muted hover:text-ink"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* ── table ── */}
          {!loading && visibleHandovers.length === 0 ? (
            <TableEmpty
              icon={<CheckCircle2 size={26} className="text-success" />}
              title="All caught up"
              body="No conversations need your attention right now."
            />
          ) : !loading && filteredHandovers.length === 0 ? (
            <TableEmpty
              icon={<Search size={24} className="text-ink-muted" />}
              title="No matches"
              body="No open escalation matches your search or filter."
            />
          ) : (
            <div className="flex-1 overflow-x-auto">
              <table className="w-full min-w-[900px] border-collapse">
                <thead>
                  <tr>
                    {[
                      { label: "Lead", w: "" },
                      { label: "Channel", w: "" },
                      { label: "Why escalated", w: "" },
                      { label: "Waiting", w: "w-[124px]" },
                      { label: "Assigned", w: "w-[160px]" },
                      { label: "Actions", w: "w-[244px]" },
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
                    {filteredHandovers.map((h) => {
                      const waited = secondsSince(h.opened_at);
                      const severity = severityForWait(waited);
                      const isMine = h.assigned_to === currentCallerId;
                      return (
                        <tr key={h.id} className="group border-b border-border-subtle bg-surface transition-colors hover:bg-surface-low">
                          <td className={cn("px-3.5 py-3 pl-6 align-middle", SPINE[severity])}>
                            <LeadCell lead={h.leads} />
                          </td>
                          <td className="px-3.5 py-3 align-middle">
                            <ChannelCell lead={h.leads} />
                          </td>
                          <td className="px-3.5 py-3 align-middle">
                            <TriggerChip reason={h.reason} />
                          </td>
                          <td className="px-3.5 py-3 align-middle">
                            <DurationCell
                              text={formatDuration(waited)}
                              severity={severity}
                              sub={new Date(h.opened_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                            />
                          </td>
                          <td className="px-3.5 py-3 align-middle">
                            <PersonCell name={h.assigned_to ? h.caller_name ?? "Assigned" : null} empty="Unassigned" />
                          </td>
                          <td className="px-3.5 py-3 pr-6 text-right align-middle">
                            <span className="inline-flex items-center justify-end gap-1.5 opacity-50 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                              {role === "owner" || isMine ? (
                                <>
                                  <button
                                    onClick={() => canReplyToConversations && onReply(h.lead_id)}
                                    disabled={!canReplyToConversations}
                                    title={readOnlyTitle}
                                    className="inline-flex h-7 w-[82px] items-center justify-center gap-1.5 rounded-lg border border-primary bg-primary font-label text-[11px] font-bold text-white transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-40"
                                  >
                                    <MessageSquare size={13} /> Reply
                                  </button>
                                  <button
                                    onClick={() => handleResolve(h)}
                                    disabled={!canReplyToConversations}
                                    title={readOnlyTitle}
                                    className="inline-flex h-7 w-[92px] items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-surface font-label text-[11px] font-bold text-success transition-colors hover:border-success hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40"
                                  >
                                    <CheckCircle2 size={13} /> Resolve
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => handleClaim(h)}
                                  disabled={!canReplyToConversations || !currentCallerId}
                                  title={
                                    !canReplyToConversations
                                      ? readOnlyTitle
                                      : !currentCallerId
                                        ? "A telecaller profile is required to pick up an escalation"
                                        : undefined
                                  }
                                  className="inline-flex h-7 w-[182px] items-center justify-center gap-1.5 rounded-lg border border-primary bg-primary font-label text-[11px] font-bold text-white transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                  <MessageSquare size={13} /> Pick up
                                </button>
                              )}

                              {role === "owner" && (
                                <div className="relative" ref={assigningId === h.id ? dropdownRef : null}>
                                  <button
                                    onClick={() => setAssigningId(assigningId === h.id ? null : h.id)}
                                    disabled={!canReplyToConversations}
                                    title={canReplyToConversations ? "Assign to a telecaller" : readOnlyTitle}
                                    aria-label="Assign to a telecaller"
                                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-surface text-ink transition-colors hover:border-ink-muted disabled:cursor-not-allowed disabled:opacity-40"
                                  >
                                    <UserCog size={13} />
                                  </button>
                                  {assigningId === h.id && (
                                    <div className="absolute right-0 top-full z-30 mt-1.5 min-w-[180px] rounded-xl border border-border bg-surface py-1 text-left shadow-card-hover">
                                      <p className="px-3 py-1 font-heading text-[10px] font-semibold uppercase tracking-[0.09em] text-ink-muted">
                                        Assign to
                                      </p>
                                      <div className="my-0.5 border-t border-border-subtle" />
                                      {callers.length === 0 ? (
                                        <p className="px-3 py-2 font-body text-xs text-ink-muted">No active callers</p>
                                      ) : (
                                        callers.map((c) => (
                                          <button
                                            key={c.id}
                                            onClick={() => handleAssign(h.id, c.id, c.name)}
                                            className="w-full px-3 py-2 text-left font-body text-xs text-ink transition-colors hover:bg-primary-light hover:text-primary"
                                          >
                                            {c.name}
                                          </button>
                                        ))
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                )}
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
