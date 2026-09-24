"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Eye, Flag, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { api, type CallLog } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { MaskedTranscript, scoreColor } from "@/components/CallAi";

type View = "open" | "resolved";

function talkTime(seconds: number | null): string {
  const total = seconds ?? 0;
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins}m ${String(secs).padStart(2, "0")}s` : `${secs}s`;
}

interface FlaggedCallsProps {
  canResolve: boolean;
  onViewLead: (leadId: string) => void;
}

/** Calls marked No answer on which the AI heard a real conversation. */
export default function FlaggedCalls({ canResolve, onViewLead }: FlaggedCallsProps) {
  const [view, setView] = useState<View>("open");
  const [rows, setRows] = useState<CallLog[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (nextView: View, nextPage: number) => {
    setLoading(true);
    try {
      const res = await api.calls.flagged(nextView, nextPage);
      setRows((prev) => (nextPage === 1 ? res.data : [...prev, ...res.data]));
      setOpenCount(res.open_count);
      setTotal(res.total);
      setPage(nextPage);
    } catch (err) {
      console.error("Failed to load flagged calls:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(view, 1);
  }, [view, load]);

  async function resolve(log: CallLog, action: "confirm" | "dismiss") {
    setBusyId(log.id);
    try {
      await api.calls.resolveFlag(log.id, action);
      toast.success(action === "confirm" ? "Flag confirmed: the call stays scored" : "Flag dismissed: counted as No answer");
      setRows((prev) => prev.filter((r) => r.id !== log.id));
      setOpenCount((n) => Math.max(0, n - 1));
      setTotal((n) => Math.max(0, n - 1));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update the flag");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
        <div>
          <h2 className="font-display text-base font-bold text-primary flex items-center gap-2">
            <Flag size={15} className="text-rose-600" /> Flagged calls
            {openCount > 0 && (
              <span className="inline-flex min-w-5 h-5 items-center justify-center rounded-full bg-rose-600 px-1.5 font-label text-[10px] font-extrabold text-white">
                {openCount}
              </span>
            )}
          </h2>
          <p className="font-label text-xs text-on-surface-muted mt-0.5">
            Marked No answer, but the AI heard the customer speak. Listen to the recording, then decide.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-xl border border-[#e8e3db] bg-[#faf8f5] p-1">
          {(["open", "resolved"] as View[]).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={`px-3 py-1 rounded-lg font-label text-[11px] font-bold transition-colors ${
                view === v ? "bg-white text-[#292524] shadow-sm" : "text-[#a8a29e] hover:text-[#57534e]"
              }`}
            >
              {v === "open" ? "Needs review" : "Resolved"}
            </button>
          ))}
        </div>
      </div>

      {loading && rows.length === 0 ? (
        <div className="py-10 flex items-center justify-center">
          <Loader2 size={18} className="animate-spin text-[#a8a29e]" />
        </div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center">
          <p className="font-body text-sm font-semibold text-[#78716c]">
            {view === "open" ? "Nothing to review" : "No resolved flags yet"}
          </p>
          <p className="font-label text-xs text-[#a8a29e] mt-1">
            {view === "open" ? "Every call marked No answer matched what the AI heard." : "Confirmed and dismissed flags appear here."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {rows.map((log) => (
            <div key={log.id} className="rounded-2xl border border-[#f0ece4] bg-[#faf8f5] p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-body text-xs font-bold text-[#292524] truncate">
                    {log.callers?.name || "Telecaller"}
                    <span className="text-[#a8a29e] font-semibold"> → </span>
                    {log.lead_id ? (
                      <button
                        type="button"
                        onClick={() => onViewLead(log.lead_id as string)}
                        className="inline-flex items-center gap-1 hover:text-primary"
                      >
                        {log.leads?.name || formatPhone(log.leads?.phone) || "Lead"} <Eye size={11} className="text-[#a8a29e]" />
                      </button>
                    ) : (
                      "Unknown lead"
                    )}
                  </p>
                  <p className="font-label text-[10px] text-[#a8a29e] mt-0.5">{timeAgo(log.flagged_at || log.created_at)}</p>
                </div>
                {log.score != null && (
                  <span className={`shrink-0 px-2 py-0.5 rounded-full border font-label text-[10px] font-extrabold ${scoreColor(log.score)}`}>
                    {log.score.toFixed(1)}/10
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5 font-label text-[10px] font-bold">
                <span className="px-2 py-0.5 rounded-full bg-white border border-[#e8e3db] text-[#57534e]">Marked: No answer</span>
                <span className="px-2 py-0.5 rounded-full bg-rose-50 border border-rose-200 text-rose-700">
                  AI heard a {talkTime(log.duration_seconds)} conversation
                </span>
                {log.flag_status === "confirmed" && (
                  <span className="px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-700">Confirmed · outcome 0/3</span>
                )}
                {log.flag_status === "dismissed" && (
                  <span className="px-2 py-0.5 rounded-full bg-white border border-[#e8e3db] text-[#78716c]">Dismissed · not scored</span>
                )}
              </div>

              {log.ai_summary?.brief && (
                <p className="font-body text-[11px] leading-relaxed text-[#44403c]">&ldquo;{log.ai_summary.brief}&rdquo;</p>
              )}

              {log.recording_url ? (
                <audio src={log.recording_url} controls preload="none" className="w-full h-8" />
              ) : (
                <p className="font-label text-[10px] italic text-[#a8a29e]">Recording unavailable.</p>
              )}

              <MaskedTranscript preview={log.transcript_preview} />

              {view === "open" && canResolve && (
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => void resolve(log, "dismiss")}
                    disabled={busyId === log.id}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#e8e3db] bg-white px-3 py-1.5 font-label text-[11px] font-bold text-[#57534e] hover:bg-[#f0ece4] disabled:opacity-50 transition-colors"
                  >
                    <X size={12} /> Dismiss – AI wrong
                  </button>
                  <button
                    type="button"
                    onClick={() => void resolve(log, "confirm")}
                    disabled={busyId === log.id}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 font-label text-[11px] font-bold text-white hover:bg-rose-700 disabled:opacity-50 transition-colors"
                  >
                    {busyId === log.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Confirm flag
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {rows.length > 0 && rows.length < total && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={() => void load(view, page + 1)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e8e3db] bg-white px-3 py-1.5 font-label text-[11px] font-bold text-[#57534e] hover:bg-[#faf8f5] disabled:opacity-50"
          >
            {loading && <Loader2 size={12} className="animate-spin" />} Show more
          </button>
        </div>
      )}
    </div>
  );
}
