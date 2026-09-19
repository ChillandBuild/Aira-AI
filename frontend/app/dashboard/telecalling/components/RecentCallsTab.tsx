"use client";
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, Loader2, Phone, RefreshCw, User } from "lucide-react";
import { api, type CallLog } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";

const OUTCOME_LABEL: Record<string, string> = {
  converted: "Converted",
  interested: "Interested",
  callback: "Callback",
  not_interested: "Not Interested",
  no_answer: "No Answer",
  do_not_call: "DNC",
  do_not_contact: "DNC",
  unreachable: "Unreachable",
};

const OUTCOME_CHIP: Record<string, string> = {
  converted: "bg-emerald-50 text-emerald-700 border-emerald-200",
  interested: "bg-cyan-50 text-cyan-700 border-cyan-200",
  callback: "bg-amber-50 text-amber-700 border-amber-200",
  not_interested: "bg-[#faf8f5] text-[#78716c] border-[#e8e3db]",
  no_answer: "bg-rose-50 text-rose-700 border-rose-200",
  do_not_call: "bg-red-50 text-red-700 border-red-200",
  do_not_contact: "bg-red-50 text-red-700 border-red-200",
  unreachable: "bg-orange-50 text-orange-700 border-orange-200",
};

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

/** The AI scorecard's score — distinct from `score`, which grades the outcome. */
function aiScore(log: CallLog): number | null {
  const raw = log.evaluation?.overall_score;
  const value = typeof raw === "string" ? Number(raw) : raw;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

interface RecentCallsTabProps {
  /** Whose calls to show; omit for everyone's (admin). */
  callerId?: string | null;
  /** Opens the lead in the detail panel. */
  onSelectLead?: (leadId: string) => void;
}

export default function RecentCallsTab({ callerId, onSelectLead }: RecentCallsTabProps) {
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setLogs(await api.calls.recent(20, callerId ?? undefined));
    } catch (err) {
      console.error("Failed to load recent calls:", err);
    } finally {
      setLoading(false);
    }
  }, [callerId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center py-12">
        <Loader2 size={18} className="animate-spin text-primary" />
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center py-12 text-center">
        <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center text-[#a8a29e] border border-[#f0ece4] mb-3">
          <Phone size={18} />
        </div>
        <p className="font-body text-sm font-semibold text-[#78716c]">No calls yet</p>
        <p className="font-label text-xs text-[#a8a29e] mt-1">Calls appear here as soon as they end.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto pr-1">
      <div className="flex items-center justify-between mb-2">
        <p className="font-label text-[9px] uppercase tracking-widest font-extrabold text-[#a8a29e]">
          Last {logs.length} calls
        </p>
        <button
          onClick={() => void load()}
          className="flex items-center gap-1 font-label text-[9px] font-bold uppercase tracking-wider text-[#a8a29e] hover:text-[#57534e] transition-colors"
        >
          <RefreshCw size={10} /> Refresh
        </button>
      </div>

      <div className="space-y-2">
        {logs.map((log) => {
          const expanded = expandedId === log.id;
          const score = aiScore(log);
          const outcome = log.outcome ?? "";
          return (
            <div key={log.id} className="bg-white border border-[#e8e3db] rounded-2xl shadow-sm overflow-hidden">
              <button
                onClick={() => setExpandedId(expanded ? null : log.id)}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[#faf8f5] transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-body text-xs font-bold text-[#292524] truncate">
                    {log.leads?.name || formatPhone(log.leads?.phone) || "Unknown lead"}
                  </p>
                  <p className="font-label text-[10px] text-[#a8a29e] mt-0.5">
                    {timeAgo(log.created_at)} · {formatDuration(log.duration_seconds)}
                    {log.callers?.name ? ` · ${log.callers.name}` : ""}
                  </p>
                </div>
                {outcome && (
                  <span className={`shrink-0 px-2 py-0.5 rounded-full border font-label text-[9px] font-bold ${OUTCOME_CHIP[outcome] ?? "bg-[#faf8f5] text-[#78716c] border-[#e8e3db]"}`}>
                    {OUTCOME_LABEL[outcome] ?? outcome}
                  </span>
                )}
                {score !== null && (
                  <span className="shrink-0 font-label text-[10px] font-extrabold text-primary">{score}/10</span>
                )}
                <ChevronDown
                  size={13}
                  className={`shrink-0 text-[#a8a29e] transition-transform ${expanded ? "rotate-180" : ""}`}
                />
              </button>

              {expanded && (
                <div className="px-3 pb-3 pt-1 border-t border-[#f0ece4] space-y-2.5">
                  {log.ai_summary?.brief && (
                    <p className="font-body text-[11px] leading-relaxed text-[#57534e]">{log.ai_summary.brief}</p>
                  )}
                  {log.recording_url ? (
                    <audio src={log.recording_url} controls className="w-full h-8" />
                  ) : (
                    <p className="font-label text-[10px] italic text-[#a8a29e]">No recording for this call.</p>
                  )}
                  {log.transcript && (
                    <details className="group">
                      <summary className="font-label text-[9px] uppercase tracking-widest font-extrabold text-[#a8a29e] cursor-pointer hover:text-[#57534e]">
                        Transcript
                      </summary>
                      <p className="mt-1.5 max-h-40 overflow-y-auto font-body text-[11px] leading-relaxed text-[#57534e] whitespace-pre-wrap">
                        {log.transcript}
                      </p>
                    </details>
                  )}
                  {log.evaluation?.coaching_tip && (
                    <p className="font-body text-[11px] leading-relaxed text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-2.5 py-2">
                      <span className="font-bold">Coaching: </span>{log.evaluation.coaching_tip}
                    </p>
                  )}
                  {log.lead_id && onSelectLead && (
                    <button
                      onClick={() => onSelectLead(log.lead_id as string)}
                      className="flex items-center gap-1.5 font-label text-[10px] font-bold text-primary hover:underline"
                    >
                      <User size={11} /> Open lead
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
