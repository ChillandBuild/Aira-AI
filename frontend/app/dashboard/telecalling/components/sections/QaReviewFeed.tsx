"use client";

import { useCallback, useEffect, useState } from "react";
import { Award, ChevronDown, Eye, Loader2 } from "lucide-react";
import { api, type CallLog } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { CallAiDetail, scoreColor } from "@/components/CallAi";
import { callResultKey, callResultLabel } from "@/lib/call-wrapup";

interface QaReviewFeedProps {
  from: string;
  to: string;
  callerId: string | null;
  callerName?: string | null;
  onViewLead: (leadId: string) => void;
}

/** The period's scored calls, weakest first, so reviews start where coaching matters most. */
export default function QaReviewFeed({ from, to, callerId, callerName, onViewLead }: QaReviewFeedProps) {
  const [rows, setRows] = useState<CallLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(
    async (nextPage: number) => {
      setLoading(true);
      try {
        const res = await api.analytics.qaQueue({ from, to, callerId, page: nextPage });
        setRows((prev) => (nextPage === 1 ? res.data : [...prev, ...res.data]));
        setTotal(res.total);
        setPage(nextPage);
      } catch (err) {
        console.error("Failed to load QA review feed:", err);
      } finally {
        setLoading(false);
      }
    },
    [from, to, callerId],
  );

  useEffect(() => {
    setOpenId(null);
    void load(1);
  }, [load]);

  const scope = callerName ? `${callerName}'s` : "The team's";
  const period = from === to ? from : `${from} to ${to}`;

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-primary mb-1 flex items-center gap-2">
        <Award size={16} className="text-primary-600" /> QA Review Feed
      </h2>
      <p className="font-label text-xs text-on-surface-muted mb-4">
        {scope} scored calls for {period}, lowest score first. Open a call to see why it scored that way.
      </p>

      <div className="space-y-2.5 max-h-[560px] overflow-y-auto pr-1">
        {loading && rows.length === 0 ? (
          <div className="py-12 flex items-center justify-center">
            <Loader2 className="animate-spin text-[#94a3b8]" size={20} />
          </div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center">
            <p className="font-body text-sm font-semibold text-[#475569]">No scored calls in this period</p>
            <p className="font-label text-xs text-[#94a3b8] mt-1">
              Calls of 30 seconds or more with a recording and a marked outcome appear here once scored.
            </p>
          </div>
        ) : (
          rows.map((log) => {
            const open = openId === log.id;
            return (
              <div key={log.id} className="rounded-2xl border border-[#f1f5f9] bg-[#f8fafc] overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : log.id)}
                  className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-white/60 transition-colors"
                >
                  {log.score != null && (
                    <span className={`shrink-0 flex h-10 w-10 items-center justify-center rounded-xl border font-display text-sm font-extrabold ${scoreColor(log.score)}`}>
                      {log.score.toFixed(1)}
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="font-body text-xs font-bold text-[#13284A] truncate">
                      {log.callers?.name || "Telecaller"}
                      <span className="text-[#94a3b8] font-semibold"> → </span>
                      {log.leads?.name || formatPhone(log.leads?.phone) || "Lead"}
                    </p>
                    <p className="font-label text-[10px] text-[#94a3b8] mt-0.5">
                      {timeAgo(log.created_at)}
                      {callResultLabel(callResultKey(log)) ? ` · ${callResultLabel(callResultKey(log))}` : ""}
                    </p>
                  </div>
                  <ChevronDown size={14} className={`shrink-0 text-[#94a3b8] transition-transform ${open ? "rotate-180" : ""}`} />
                </button>
                {open && (
                  <div className="px-3.5 pb-3.5 pt-1 border-t border-[#f1f5f9] space-y-2.5">
                    {log.recording_url ? (
                      <audio src={log.recording_url} controls preload="none" className="w-full h-8" />
                    ) : (
                      <p className="font-label text-[10px] italic text-[#94a3b8]">Recording unavailable.</p>
                    )}
                    <CallAiDetail log={log} />
                    {log.lead_id && (
                      <button
                        type="button"
                        onClick={() => onViewLead(log.lead_id as string)}
                        className="inline-flex items-center gap-1.5 font-label text-[10px] font-bold text-primary hover:underline"
                      >
                        <Eye size={11} /> Open lead
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {rows.length > 0 && rows.length < total && (
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => void load(page + 1)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e2e8f0] bg-white px-3 py-1.5 font-label text-[11px] font-bold text-[#334155] hover:bg-[#f8fafc] disabled:opacity-50"
          >
            {loading && <Loader2 size={12} className="animate-spin" />} Show more ({total - rows.length} left)
          </button>
        </div>
      )}
    </div>
  );
}
