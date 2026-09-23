"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, RefreshCw, WifiOff } from "lucide-react";
import { api, type CallLog, type PendingWrapupSummary } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { pendingCallLabel } from "../../lib/feedbackLabels";

const SYNC_STALE_MS = 2 * 60 * 60 * 1000;
const WORKDAY_START_HOUR = 9;
const WORKDAY_END_HOUR = 20;
const POLL_MS = 30_000;

function syncWarning(row: PendingWrapupSummary): string | null {
  if (!row.has_sync_token) return "Aira Sync not set up";
  const hour = new Date().getHours();
  if (hour < WORKDAY_START_HOUR || hour >= WORKDAY_END_HOUR) return null;
  if (!row.last_sync_at) return "Aira Sync never connected";
  return Date.now() - new Date(row.last_sync_at).getTime() > SYNC_STALE_MS ? "Aira Sync inactive" : null;
}

/** Owner-only: who owes call feedback, who's not syncing, and a dismiss escape hatch. */
export default function FeedbackOversight() {
  const [rows, setRows] = useState<PendingWrapupSummary[]>([]);
  const [pending, setPending] = useState<CallLog[]>([]);
  const [openCaller, setOpenCaller] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [summary, calls] = await Promise.all([
        api.calls.pendingWrapupsSummary(),
        api.calls.getPendingWrapups(),
      ]);
      setRows(summary);
      setPending(calls);
    } catch {
      // Owner-only panel; a failed refresh just keeps the last view.
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  async function dismiss(log: CallLog) {
    const reason = window.prompt("Why does this call not need feedback? (e.g. wrong number, personal call)");
    if (!reason || reason.trim().length < 3) return;
    setBusyId(log.id);
    try {
      await api.calls.dismissFeedback(log.id, reason.trim());
      toast.success("Call cleared from the pending list");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not dismiss");
    } finally {
      setBusyId(null);
    }
  }

  const visible = rows.filter((r) => r.pending_count > 0 || syncWarning(r));
  if (visible.length === 0) return null;

  return (
    <section aria-labelledby="feedback-oversight-title" className="rounded-3xl border border-[#e8e3db] bg-[#faf8f5] p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <AlertCircle size={16} className="text-amber-600" />
        <h3 id="feedback-oversight-title" className="font-display text-base font-extrabold text-[#1c1917]">
          Call feedback &amp; sync
        </h3>
        <button onClick={load} aria-label="Refresh" className="ml-auto text-[#a8a29e] hover:text-[#44403c]">
          <RefreshCw size={14} />
        </button>
      </div>
      <ul className="space-y-2">
        {visible.map((row) => {
          const warning = syncWarning(row);
          const expanded = openCaller === row.caller_id;
          const calls = pending.filter((p) => p.caller_id === row.caller_id);
          return (
            <li key={row.caller_id} className="rounded-2xl border border-[#f0ece4] bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-body text-sm font-bold text-[#292524]">{row.name || "Telecaller"}</span>
                {row.pending_count > 0 && (
                  <button
                    onClick={() => setOpenCaller(expanded ? null : row.caller_id)}
                    aria-expanded={expanded}
                    className="rounded-full bg-amber-50 px-2.5 py-0.5 font-label text-xs font-bold text-amber-700 hover:bg-amber-100"
                  >
                    {row.pending_count} awaiting feedback
                  </button>
                )}
                {warning && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 font-label text-xs font-bold text-red-700">
                    <WifiOff size={11} /> {warning}
                    {row.last_sync_at ? ` · last ${timeAgo(row.last_sync_at)}` : ""}
                  </span>
                )}
              </div>
              {expanded && (
                <ul className="mt-3 space-y-2">
                  {calls.map((log) => (
                    <li key={log.id} className="flex items-center justify-between gap-3 rounded-xl bg-[#faf8f5] px-3 py-2">
                      <div className="min-w-0">
                        <p className="truncate font-body text-xs font-bold text-[#292524]">
                          {log.leads?.name || "Unnamed lead"} ({formatPhone(log.leads?.phone || "")})
                        </p>
                        <p className="font-label text-[11px] text-[#78716c]">
                          {pendingCallLabel(log)} · {new Date(log.created_at).toLocaleString()}
                        </p>
                      </div>
                      <button
                        onClick={() => dismiss(log)}
                        disabled={busyId === log.id}
                        className="shrink-0 rounded-lg border border-[#e8e3db] px-3 py-1 font-label text-xs font-bold text-[#44403c] hover:bg-white disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
