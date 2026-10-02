"use client";
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, Loader2, Phone, RefreshCw, User } from "lucide-react";
import { api, type CallLog } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { CallAiDetail, CallScorePill, anyProcessing } from "@/components/CallAi";
import { TONE_CHIP, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

const PROCESSING_POLL_MS = 10_000;

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

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      setLogs(await api.calls.recent(20, callerId ?? undefined));
    } catch (err) {
      console.error("Failed to load recent calls:", err);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [callerId]);

  useEffect(() => {
    void load();
  }, [load]);

  // While a recording is being transcribed or scored, refresh quietly so the
  // score and summary appear without the telecaller reloading.
  const processing = anyProcessing(logs);
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => void load(true), PROCESSING_POLL_MS);
    return () => clearInterval(timer);
  }, [processing, load]);

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
          const resultKey = callResultKey(log);
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
                  <p className="font-label text-[10px] text-[#a8a29e] mt-0.5 truncate">
                    by {log.callers?.name || "Admin"}
                  </p>
                </div>
                <ChevronDown
                  size={13}
                  className={`shrink-0 text-[#a8a29e] transition-transform ${expanded ? "rotate-180" : ""}`}
                />
              </button>

              {expanded && (
                <div className="px-3 pb-3 pt-2 border-t border-[#f0ece4] space-y-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-label text-[10px] text-[#a8a29e]">
                      {timeAgo(log.created_at)} · {formatDuration(log.duration_seconds)}
                    </span>
                    {resultKey && (
                      <span className={`px-2 py-0.5 rounded-full border font-label text-[9px] font-bold ${TONE_CHIP[callResultTone(resultKey)]}`}>
                        {callResultLabel(resultKey) ?? resultKey}
                      </span>
                    )}
                    <CallScorePill log={log} />
                  </div>
                  {log.recording_url ? (
                    <audio src={log.recording_url} controls className="w-full h-8" />
                  ) : (
                    <p className="font-label text-[10px] italic text-[#a8a29e]">No recording for this call.</p>
                  )}
                  {log.provider === "telecmi" ? (
                    <CallAiDetail log={log} onChanged={() => void load(true)} />
                  ) : (
                    log.ai_summary?.brief && (
                      <p className="font-body text-[11px] leading-relaxed text-[#57534e]">{log.ai_summary.brief}</p>
                    )
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
